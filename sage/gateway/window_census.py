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

# The phases of a beat that call the model. A phase absent from a record is not an error:
# older beats predate the split, and a beat that never reached a phase never generated.
PHASES = ("posture", "explore", "reflect")

# prompt_eval + eval can land a token or two short of num_ctx and still be the window's doing.
SATURATION_SLACK = 8


def read_generates(beats: list[dict]) -> list[dict]:
    """One row per generate, carrying the beat context the row is judged against.

    A generate with no `prompt_eval_count` is skipped rather than defaulted: the counters were
    added mid-life (2026-09-05), and a zero there would read as a free window.
    """
    rows: list[dict] = []
    for ordinal, beat in enumerate(beats):
        num_ctx = beat.get("num_ctx")
        for phase in PHASES:
            section = beat.get(phase) or {}
            for gen in section.get("generates") or []:
                prompt = gen.get("prompt_eval_count")
                if prompt is None or not num_ctx:
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
                    "num_predict": gen.get("num_predict"),
                    "done_reason": gen.get("done_reason"),
                    "retried": gen.get("retried", 0),
                    "classes": classify(num_ctx, prompt, evaluated, gen),
                })
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


def census(rows: list[dict]) -> dict:
    if not rows:
        return {"generates": 0}
    counts: Counter = Counter()
    for row in rows:
        for cls in row["classes"]:
            counts[cls] += 1
    prompts = [r["prompt_eval_count"] for r in rows]
    headroom = [r["headroom"] for r in rows]
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
        "saturated": counts["saturated"],
        "length": counts["length"],
        "budget_starved": counts["budget_starved"],
        "budget_starved_pct": round(100 * counts["budget_starved"] / len(rows), 1),
        "clear": counts["clear"],
        # The whole point of the split: these two differ, and the difference is the finding.
        "saturated_not_length": sum(
            1 for r in rows if "saturated" in r["classes"] and "length" not in r["classes"]
        ),
    }


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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--instance", required=True, type=Path)
    ap.add_argument("--since", help="ISO date/timestamp; beats at or after it")
    ap.add_argument("--last", type=int, help="only the last N beats")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--gate", action="store_true",
                    help="exit 1 if any generate saturated the window (the S5 falsifier)")
    args = ap.parse_args()

    beats = load_beats(args.instance, args.since, args.last)
    rows = read_generates(beats)
    summary = census(rows)

    if args.json:
        print(json.dumps(summary, indent=2))
    elif not summary["generates"]:
        print("[window-census] no generates with counters in range")
    else:
        print(f"window census — {summary['generates']} generates over {summary['beats']} beats, "
              f"num_ctx {summary['num_ctx']}")
        print(f"  prompt tokens   median {summary['prompt_tokens']['median']}  "
              f"max {summary['prompt_tokens']['max']}")
        print(f"  headroom        median {summary['headroom']['median']}  "
              f"min {summary['headroom']['min']}")
        print(f"  saturated       {summary['saturated']}"
              f"   (of which not length-stopped: {summary['saturated_not_length']})")
        print(f"  length stops    {summary['length']}")
        print(f"  budget starved  {summary['budget_starved']} "
              f"({summary['budget_starved_pct']}%)")

    if args.gate:
        # Fail closed (PRD §2): an empty range is not a clear window, it is no evidence. A gate
        # that passes when it measured nothing is the failure mode it exists to prevent.
        if not summary["generates"]:
            print("[window-census] GATE FAIL: no generates with counters in range; "
                  "absence of evidence is not a cleared window", file=sys.stderr)
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
