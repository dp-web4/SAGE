"""
window_census — read a being's generates and say whether the CONTEXT WINDOW bound them.

The S5 question is "does experience change anything", read as UPTAKE over the heartbeat→raising
channel. That number is only about the being if the channel was not quietly eating its room to
answer. cbp-claude, 2026-09-12, reviewing this PRD: a one-line `num_ctx` in the model config has
a measured 0 → 9 effect on ACTS on the other seat (Legion beat 46, the 27B heretic at the 8192
harness floor), and the 2B variant declares no `num_ctx` at all. So a rung-6 reading taken while
the window binds is ambiguous between "experience changes nothing" and "the channel ate the
window", and the difference is not visible in any count the panel already keeps.

It is visible in the record, though, and has been all along: every beat carries `num_ctx`, and
every generate carries `prompt_eval_count`, `eval_count`, `num_predict` and `done_reason`. This
turns those four fields into the covariate, per generate, so the S5 read can be taken WITH the
window pinned and declared rather than assumed away.

Four classes, because the response to each differs:

  * `saturated`       — prompt_eval + eval reaches `num_ctx`. The window bound this generate.
                        This is the class that matters and it is NOT the same as `length`:
                        measured on Sprout, 19 generates saturated and only 18 stopped on
                        `length` — one (2026-09-07T01:11:12Z, prompt 8114 + eval 78 = 8192)
                        reported `done_reason: stop` with 78 tokens of room. Counting length
                        stops undercounts the bound generates, which is why this is its own
                        class and why the gate below keys on saturation.
  * `length`          — `done_reason: length`. The generate ran out of budget, window or not.
  * `budget_starved`  — headroom (`num_ctx - prompt_eval`) is smaller than the `num_predict`
                        the variant declares. Nothing was necessarily truncated; the declared
                        budget simply could not have applied. On Sprout before S5 cut 1 this
                        was 97% of generates: a `num_predict_think` of 6000 against a median
                        6002-token prompt in an 8192 window is a fiction on paper.
  * `clear`           — the window was not a factor.

`--gate` is the pre-registered falsifier for the S5 read: exit 1 if ANY generate in the range
saturated. Sprout's ruling on cbp-claude's finding 1 is to pin 8192 and carry this covariate
rather than move `num_ctx` before a pre-registered read; the gate is what makes that ruling
falsifiable instead of a hope. If it trips, the read is void and the remedy is the declared one
(give the `2b` variant its own `num_ctx`, re-baseline, read again).

    python3 -m sage.gateway.window_census --instance sage/instances/<dir>
    python3 -m sage.gateway.window_census --instance <dir> --since 2026-09-08
    python3 -m sage.gateway.window_census --instance <dir> --last 30
    python3 -m sage.gateway.window_census --instance <dir> --gate     # S5 falsifier
    python3 -m sage.gateway.window_census --instance <dir> --json     # for a watcher
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

# The phases of a beat that call the model, in the order a beat runs them. This tuple is now only
# a DISPLAY order and a cross-check: sections are discovered by shape (below), because hard-coding
# the set made the census silently blind to a phase the record might grow. cbp-claude raised this
# 2026-09-12 against a record that carries `"schema": "heartbeat/v2"` for exactly that reason
# (Legion's amendment 4: "a version says so instead of making it infer from key presence").
#
# Their alternative — read `schema` and fail on an unknown version — is the wrong half of their own
# argument HERE, and measured: 33 of Sprout's 349 beats predate the field and carry no `schema` at
# all, so a fail-on-unknown-version gate rejects the historical range it is supposed to read.
# Shape discovery needs no version and cannot go stale, so that is the half taken.
# "account" is a canonical phase as of 2026-09-12: the S1 account turn now records counters
# (heartbeat.py), and it is the beat's largest generate. Shape discovery would find it anyway;
# naming it here only fixes its position in the output. "raising" is the session channel
# (--sessions), the channel UPTAKE is actually pre-registered on.
PHASES = ("posture", "explore", "reflect", "account", "raising")


def generating_sections(beat: dict) -> list[str]:
    """Sections of a beat that carry generates, discovered by SHAPE rather than by name.

    A new generating phase is therefore counted the day it appears instead of being dropped
    silently — which, before this, would have let `--gate` pass a range it could not see.
    """
    found = [k for k, v in beat.items()
             if isinstance(v, dict) and isinstance(v.get("generates"), list)]
    # canonical phases first, in beat order, then anything new, so output stays stable
    return [p for p in PHASES if p in found] + sorted(set(found) - set(PHASES))

# prompt_eval + eval can land a token or two short of num_ctx and still be the window's doing.
SATURATION_SLACK = 8


def read_generates(beats: list[dict], coverage: dict | None = None) -> list[dict]:
    """One row per generate, carrying the beat context the row is judged against.

    A generate with no `prompt_eval_count` is skipped rather than defaulted: the counters were
    added mid-life (2026-09-05), and a zero there would read as a free window.

    Skipping is now COUNTED into `coverage`, because a skip is invisible in every number below it
    and `--gate` is a falsifier. cbp-claude, 2026-09-12: fail-closed on an empty range but not on a
    90%-dropped range applies the instinct one line short of where it belongs. A range that lost
    rows is not a cleared window, it is a partial measurement, and the gate now says so.

    Two things that are NOT skips, kept separate because the response to each differs:
      * a beat that generated nothing at all (`gate_only` beats: the record states the reason in
        the beat itself). Sprout has 33 of these in 349 — the gap cbp-claude read as silent drops.
        Measured, the true skip count over the whole record is 1 generate in 1243.
      * a section with an empty `generates` list — a phase reached but not run.
    """
    cov = coverage if coverage is not None else {}
    cov.setdefault("beats_scanned", 0)
    cov.setdefault("beats_with_generates", 0)
    cov.setdefault("beats_without_generates", 0)
    cov.setdefault("generates_seen", 0)
    cov.setdefault("skipped", 0)
    cov.setdefault("skipped_no_prompt_eval", 0)
    cov.setdefault("skipped_no_num_ctx", 0)
    cov.setdefault("sections", [])

    seen_sections: set[str] = set(cov["sections"])
    rows: list[dict] = []
    for ordinal, beat in enumerate(beats):
        num_ctx = beat.get("num_ctx")
        cov["beats_scanned"] += 1
        beat_gens = 0
        for phase in generating_sections(beat):
            seen_sections.add(phase)
            section = beat.get(phase) or {}
            for gen in section.get("generates") or []:
                beat_gens += 1
                cov["generates_seen"] += 1
                prompt = gen.get("prompt_eval_count")
                if prompt is None:
                    cov["skipped"] += 1
                    cov["skipped_no_prompt_eval"] += 1
                    continue
                if not num_ctx:
                    cov["skipped"] += 1
                    cov["skipped_no_num_ctx"] += 1
                    continue
                evaluated = gen.get("eval_count") or 0
                rows.append({
                    "beat": ordinal,     # not ts: two beats can share a timestamp
                    "ts": beat.get("ts"),
                    "phase": phase,
                    "num_ctx": num_ctx,
                    "prompt_eval_count": prompt,
                    "eval_count": evaluated,
                    "headroom": num_ctx - prompt,
                    # Room the reply actually had to fit in. `headroom` ranks by prompt length;
                    # what binds is per-generate slack, and the two disagree: Sprout's tightest
                    # generate at a +660 JOIN is beat 16 (headroom 2245), comfortably above the
                    # published headroom.min of 1388 (cbp-claude, 2026-09-12).
                    "slack": num_ctx - prompt - evaluated,
                    "num_predict": gen.get("num_predict"),
                    "done_reason": gen.get("done_reason"),
                    "retried": gen.get("retried", 0),
                    "classes": classify(num_ctx, prompt, evaluated, gen),
                })
        if beat_gens:
            cov["beats_with_generates"] += 1
        else:
            cov["beats_without_generates"] += 1
    cov["sections"] = sorted(seen_sections)
    return rows


def classify(num_ctx: int, prompt: int, evaluated: int, gen: dict) -> list[str]:
    """Classes are NOT exclusive. A saturated generate is usually also length-stopped and
    budget-starved, and collapsing them to one label is how the `stop`-at-8192 case hid."""
    out = []
    if prompt + evaluated >= num_ctx - SATURATION_SLACK:
        out.append("saturated")
    if gen.get("done_reason") == "length":
        out.append("length")
    declared = gen.get("num_predict")
    if declared and (num_ctx - prompt) < declared:
        out.append("budget_starved")
    return out or ["clear"]


def census(rows: list[dict], coverage: dict | None = None) -> dict:
    if not rows:
        out = {"generates": 0}
        if coverage:
            out["coverage"] = dict(coverage)
        return out
    counts: Counter = Counter()
    for row in rows:
        for cls in row["classes"]:
            counts[cls] += 1
    prompts = [r["prompt_eval_count"] for r in rows]
    headroom = [r["headroom"] for r in rows]
    slack = [r["slack"] for r in rows]
    binding = min(rows, key=lambda r: r["slack"])
    windows = sorted({r["num_ctx"] for r in rows})
    return {
        "generates": len(rows),
        "beats": len({r["beat"] for r in rows}),
        "num_ctx": windows[0] if len(windows) == 1 else windows,
        "prompt_tokens": {
            "median": int(statistics.median(prompts)),
            "max": max(prompts),
        },
        "headroom": {
            "median": int(statistics.median(headroom)),
            "min": min(headroom),
        },
        # One more order statistic, no new field: which generate is actually closest to the
        # wall, and where it is. `headroom.min` answers a different question and names a
        # different generate.
        "slack": {
            "median": int(statistics.median(slack)),
            "min": binding["slack"],
            "binding": {"beat": binding["beat"], "ts": binding["ts"], "phase": binding["phase"]},
        },
        "saturated": counts["saturated"],
        "length": counts["length"],
        "budget_starved": counts["budget_starved"],
        "budget_starved_pct": round(100 * counts["budget_starved"] / len(rows), 1),
        "clear": counts["clear"],
        # The whole point of the split: these two differ, and the difference is the finding.
        "saturated_not_length": sum(
            1 for r in rows if "saturated" in r["classes"] and "length" not in r["classes"]
        ),
        # Coverage is part of the verdict, not a footnote: every number above is computed over
        # `generates` and says nothing about what did not reach it.
        "coverage": dict(coverage) if coverage else None,
    }


def export_counters(rows: list[dict], dest: Path, summary: dict) -> int:
    """Write the census's INPUT as committable evidence, counters only.

    `.gitignore` excludes `sage/instances/*/heartbeats.jsonl` (being-voice text, and a privacy
    question), so no third seat could reproduce snapshot 4a's table — cbp-claude tried and could
    not. §8's rule is that a milestone is met when the snapshot quotes instrument output; for a
    pre-registered FALSIFIER that is not enough, because a falsifier's whole function is to be
    checkable by someone who does not trust the claimant.

    These seven fields are the only ones the census reads. They carry no being-authored text, so
    committing them raises no disclosure question under §6 — and they make the gate replayable:
        python3 -m sage.gateway.window_census --counters <file> --gate
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    # `beat` is carried alongside cbp-claude's seven counters because beat identity is not
    # recoverable from `ts`: two beats can share a timestamp (that is why rows key on an ordinal
    # and not on ts). Without it a replay reads one beat per generate — measured, 125 instead of
    # 30 — which would make the replayed `beats` count quietly wrong while every other field agreed.
    fields = ("beat", "ts", "phase", "num_ctx", "prompt_eval_count", "eval_count",
              "num_predict", "done_reason")
    with dest.open("w") as fh:
        # A header line naming the derivation, so the file says what it is and what it omits.
        fh.write(json.dumps({
            "kind": "window_census/counters/v1",
            "fields": list(fields),
            "generates": summary.get("generates"),
            "coverage": summary.get("coverage"),
            "note": "counters only; no being-authored text. Derived from heartbeats.jsonl "
                    "(gitignored) so the census and its gate are reproducible off this file.",
        }, sort_keys=True) + "\n")
        for row in rows:
            fh.write(json.dumps({k: row.get(k) for k in fields}, sort_keys=True) + "\n")
    return len(rows)


def load_counters(path: Path) -> list[dict]:
    """Re-read an exported counters file into census rows — the third-seat replay path."""
    rows: list[dict] = []
    for ordinal, line in enumerate(path.read_text().splitlines()):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("kind", "").startswith("window_census/counters"):
            continue        # header
        prompt, num_ctx = rec.get("prompt_eval_count"), rec.get("num_ctx")
        if prompt is None or not num_ctx:
            continue
        evaluated = rec.get("eval_count") or 0
        rows.append({
            "beat": rec.get("beat", ordinal), "ts": rec.get("ts"), "phase": rec.get("phase"),
            "num_ctx": num_ctx, "prompt_eval_count": prompt, "eval_count": evaluated,
            "headroom": num_ctx - prompt, "slack": num_ctx - prompt - evaluated,
            "num_predict": rec.get("num_predict"),
            "done_reason": rec.get("done_reason"), "retried": 0,
            "classes": classify(num_ctx, prompt, evaluated, rec),
        })
    return rows


def load_beats(instance: Path, since: str | None, last: int | None) -> list[dict]:
    record = instance / "heartbeats.jsonl"
    if not record.exists():
        print(f"[window-census] no record at {record}", file=sys.stderr)
        return []
    beats = []
    for line in record.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            beats.append(json.loads(line))
        except json.JSONDecodeError:
            # A torn last line is the live timer mid-write, not a corrupt record.
            continue
    if since:
        beats = [b for b in beats if (b.get("ts") or "") >= since]
    if last:
        beats = beats[-last:]
    return beats


def join_probe(rows: list[dict], added: int) -> dict:
    """What a JOIN of `added` prompt tokens would do to the replies that actually landed.

    The test is `num_ctx - (prompt + added) < eval`, NOT `headroom - added < 0`. Headroom is
    room FOR the response, so comparing post-JOIN room against zero asks whether the prompt
    still fits and silently drops the requirement that the reply fit beside it (cbp-claude,
    2026-09-12). Reported per phase because a JOIN is prepended to one turn, not to all of
    them: on an act-first instance the session->beat block reaches `posture` only, and a
    phase-pooled rate is diluted by the phases it never enters.
    """
    out: dict = {"added_prompt_tokens": added, "generates": len(rows), "truncated": 0, "phases": {}}
    worst = None
    for r in rows:
        deficit = r["num_ctx"] - (r["prompt_eval_count"] + added) - r["eval_count"]
        ph = out["phases"].setdefault(r["phase"], {"generates": 0, "truncated": 0})
        ph["generates"] += 1
        if deficit < 0:
            out["truncated"] += 1
            ph["truncated"] += 1
        if worst is None or deficit < worst[0]:
            worst = (deficit, r)
    if worst is not None:
        out["worst"] = {"deficit": worst[0], "beat": worst[1]["beat"], "ts": worst[1]["ts"],
                        "phase": worst[1]["phase"], "headroom": worst[1]["headroom"]}
    return out


def load_sessions(instance: Path, since: str | None, last: int | None) -> list[dict]:
    """Raising-session records, shaped like beats so one reader serves both channels.

    This is the channel UPTAKE is pre-registered on -- PRD_ONE_BEING_ONE_EXPERIENCE §2:
    "computed on the heartbeat->raising channel" -- and until 2026-09-12 it recorded no window
    counters at all, so `--gate` certified the beat channel next to it while the read happened
    here (cbp-claude). Sessions written before the `window` block simply have no rows; the gate
    fails closed on an empty range, which is the correct verdict for an unmeasured channel.

    `generates_attempted` is honoured by padding: a turn whose generate did not land becomes a
    counter-less row, i.e. a COUNTED skip, rather than vanishing from the denominator.
    """
    sessions = sorted((instance / "sessions").glob("session_*.json"))
    out: list[dict] = []
    for f in sessions:
        try:
            rec = json.loads(f.read_text(errors="replace"))
        except json.JSONDecodeError:
            continue
        win = rec.get("window")
        if not isinstance(win, dict):
            continue
        gens = list(win.get("generates") or [])
        missing = max(0, int(win.get("generates_attempted") or len(gens)) - len(gens))
        gens += [{} for _ in range(missing)]
        out.append({"ts": rec.get("end") or rec.get("start"),
                    "session": rec.get("session"),
                    "num_ctx": win.get("num_ctx"),
                    "raising": {"generates": gens}})
    out.sort(key=lambda r: (r.get("session") or 0))
    if since:
        out = [r for r in out if (r.get("ts") or "") >= since]
    if last:
        out = out[-last:]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--instance", type=Path)
    ap.add_argument("--counters", type=Path,
                    help="read an exported counters file instead of the instance record "
                         "(lets a third seat replay the gate from committed evidence)")
    ap.add_argument("--since", help="ISO date/timestamp; beats at or after it")
    ap.add_argument("--last", type=int, help="only the last N beats")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--export-counters", type=Path,
                    help="write a counters-only derivation (committable evidence; no being text)")
    ap.add_argument("--gate", action="store_true",
                    help="exit 1 if any generate saturated the window (the S5 falsifier)")
    ap.add_argument("--sessions", action="store_true",
                    help="census the RAISING channel (sessions/session_*.json) instead of the "
                         "beats -- this is the channel UPTAKE is pre-registered on")
    ap.add_argument("--join", type=int, metavar="N",
                    help="what-if: report the generates whose landed reply would no longer fit "
                         "if the prompt grew by N tokens (per phase)")
    args = ap.parse_args()

    if not args.counters and not args.instance:
        print("[window-census] need --instance or --counters", file=sys.stderr)
        return 2

    coverage: dict = {}
    if args.counters:
        rows = load_counters(args.counters)
        # A replay measures exactly the rows the export carried; it cannot re-derive what the
        # original run dropped, so it reports the export's own coverage rather than inventing one.
        head = json.loads(args.counters.read_text().splitlines()[0] or "{}")
        coverage = head.get("coverage") or {}
    else:
        loader = load_sessions if args.sessions else load_beats
        rows = read_generates(loader(args.instance, args.since, args.last), coverage)
    summary = census(rows, coverage)
    if args.join is not None and rows:
        summary["join_probe"] = join_probe(rows, args.join)

    if args.export_counters:
        written = export_counters(rows, args.export_counters, summary)
        print(f"[window-census] wrote {written} counter rows to {args.export_counters}",
              file=sys.stderr)

    if args.json:
        # sort_keys so a snapshot blob and its third-seat replay diff to nothing when they agree
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif not summary["generates"]:
        print("[window-census] no generates with counters in range")
    else:
        print(f"window census — {summary['generates']} generates over {summary['beats']} beats, "
              f"num_ctx {summary['num_ctx']}")
        print(f"  prompt tokens   median {summary['prompt_tokens']['median']}  "
              f"max {summary['prompt_tokens']['max']}")
        print(f"  headroom        median {summary['headroom']['median']}  "
              f"min {summary['headroom']['min']}")
        sl = summary["slack"]
        print(f"  slack           median {sl['median']}  min {sl['min']} "
              f"(binds at beat {sl['binding']['beat']} {sl['binding']['ts']} "
              f"{sl['binding']['phase']})")
        print(f"  saturated       {summary['saturated']}"
              f"   (of which not length-stopped: {summary['saturated_not_length']})")
        print(f"  length stops    {summary['length']}")
        print(f"  budget starved  {summary['budget_starved']} "
              f"({summary['budget_starved_pct']}%)")
        cov = summary.get("coverage") or {}
        print(f"  coverage        {cov.get('generates_seen', 0) - cov.get('skipped', 0)}"
              f"/{cov.get('generates_seen', 0)} generates counted, "
              f"{cov.get('skipped', 0)} skipped; "
              f"{cov.get('beats_without_generates', 0)} of "
              f"{cov.get('beats_scanned', 0)} beats generated nothing")
        print(f"  sections read   {', '.join(cov.get('sections') or []) or '(none)'}")
        jp = summary.get("join_probe")
        if jp:
            per = "  ".join(f"{k} {v['truncated']}/{v['generates']}"
                            for k, v in sorted(jp["phases"].items()))
            print(f"  join +{jp['added_prompt_tokens']:<10} {jp['truncated']}/{jp['generates']} "
                  f"replies no longer fit   [{per}]")
            w = jp.get("worst") or {}
            print(f"                  worst deficit {w.get('deficit')} at beat {w.get('beat')} "
                  f"{w.get('ts')} {w.get('phase')} (headroom {w.get('headroom')})")

    if args.gate:
        # Fail closed (PRD §2): an empty range is not a clear window, it is no evidence. A gate
        # that passes when it measured nothing is the failure mode it exists to prevent.
        if not summary["generates"]:
            print("[window-census] GATE FAIL: no generates with counters in range; "
                  "absence of evidence is not a cleared window", file=sys.stderr)
            return 1
        # Same argument as the empty range, one line apart (cbp-claude, 2026-09-12): a range that
        # dropped rows was not measured, and a gate that cannot see a generate cannot clear it.
        skipped = (summary.get("coverage") or {}).get("skipped", 0)
        if skipped:
            print(f"[window-census] GATE FAIL: {skipped} generate(s) in range carry no usable "
                  f"counters and were not measured; a partial measurement is not a cleared window",
                  file=sys.stderr)
            return 1
        if summary.get("saturated"):
            print(f"[window-census] GATE FAIL: {summary['saturated']} generate(s) saturated "
                  f"num_ctx {summary['num_ctx']}; a rung-6 read over this range is confounded",
                  file=sys.stderr)
            return 1
        print("[window-census] gate clear: the window bound no generate in this range",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
