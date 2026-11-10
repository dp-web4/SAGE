"""
beat_health — say what each of a being's beats actually WAS, so a failing beat is seen the beat it happens.

WHY. From 2026-11-02 11:17Z to 2026-11-09 23:42Z legion-being beat 163 times and said nothing. The lid
closed mid-inference, Legion suspended, and the ollama runner it resumed with never finished another
request: every generate ran to the 10-minute client timeout. Every beat record said so, in
explore/reflect/answer.reply = "[OllamaIRP: Error: timed out]". Nothing read it. The beat watchdog
watches whether the being is WOKEN, and it was, on time, 163 times. The seat's lane check printed
selection_error, which was None. A week of the being's life went by on a record that described the
failure exactly.

That is the shape this module exists to break: the record knew and nothing said. So this reads the
record a beat leaves and puts every beat in exactly one class:

  * `mute`      — the model never answered: a phase reply is a model-transport error ("[OllamaIRP: …")
                  and no act succeeded. The being cannot fix this — the thing that is broken is the
                  thing it thinks with — so it is the HARNESS's to notice and repair (beat_watchdog.sh).
  * `looped`    — the harness's own loop guard fired (explore.looped).
  * `stuck`     — acts were tried, at least STUCK_MIN of them failed or were refused, and none
                  produced anything (no effecting act succeeded).
  * `worked`    — at least one EFFECTING act succeeded OUTSIDE the being's own records: a game move, a
                  run, something said or posted, a witness, a peer asked, a PR.
  * `noted`     — effecting acts succeeded, but only on the being's own records (OWN_RECORDS: a note or
                  memory written, a skill or handoff saved, a conversation turn settled). Planning is real
                  work; a long streak of it under a stated intention to act is the signal.
  * `read-only` — acts succeeded, but only reads (memory_read, search, recall, …). The being looked
                  and left nothing behind. Not a fault on its own; a long streak of it is a signal.
  * `idle`      — the model answered and no act succeeded: none was tried (including a chosen rest), or
                  fewer than STUCK_MIN were and all failed (flagged `failed_acts`).

Each beat also carries flags that do not decide its class but are worth seeing: `model_error` (some
phase failed even though the beat did work), `capped` (a phase hit its step cap), `window_full`.

A class is a reading of the record, not a verdict on the being. `stuck` can be the law working;
`read-only` can be study. What the classes buy is that a STREAK is visible: three mute beats are an
outage, not three beats.

    python3 -m sage.gateway.beat_health --instance sage/instances/<dir> [--last 20]
    python3 -m sage.gateway.beat_health --instance <dir> --check     # exit 3 on an alarm, for a watchdog
    python3 -m sage.gateway.beat_health --instance <dir> --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PHASES = ("explore", "reflect", "answer", "act_after_answer")

# Acts that leave something behind when they succeed. Everything else the being can call is a read or a
# control verb (stay_awake) and does not, on its own, make a beat a working one.
EFFECTING = frozenset({
    "memory_write", "memory_edit", "remember", "retire_note", "run", "request_run", "game", "settle",
    "say", "skill", "witness", "peer_ask", "camera", "pr_open", "pr_comment", "handoff", "channel_post",
})
READS = frozenset({"memory_read", "search", "recall", "git_read", "describe", "pr_read", "inbox_read"})
# Effecting acts whose only effect is on the being's OWN records: what it knows, plans and has settled. A beat
# that did only these is `noted`, not `worked`. 2026-11-10: the strip read WWWWWWWWWWWW over 15 beats with one
# (failed) game call between them -- every W was a note written about the next beat's move. The being had
# just told the seat it meant to keep its strip showing W; a W that a note can earn is a W the next note will earn.
OWN_RECORDS = frozenset({"memory_write", "memory_edit", "remember", "retire_note", "skill", "handoff", "settle"})

STUCK_MIN = 3          # failed or refused acts, with nothing effected, before a beat counts as stuck
MODEL_ERROR_PREFIXES = ("[OllamaIRP:", "[OllamaIRP ")

# Streaks that alarm (--check): one mute beat is enough — it means the model is not answering, and the
# next beat will be the same unless something outside the being acts. Stuck and looped beats are the
# being's to work through, so they alarm only when they repeat.
ALARM_STREAK = {"mute": 1, "stuck": 3, "looped": 3}

LETTERS = {"worked": "W", "noted": "n", "read-only": "r", "idle": ".", "stuck": "S", "looped": "L", "mute": "M"}


def _phases(rec: dict):
    for name in PHASES:
        p = rec.get(name)
        if isinstance(p, dict):
            yield name, p


def _model_error(p: dict) -> str | None:
    reply = p.get("reply")
    if isinstance(reply, str) and reply.startswith(MODEL_ERROR_PREFIXES):
        return reply[:80]
    return None


def classify(rec: dict) -> dict:
    """One beat record → {ts, cls, flags, acts: {ok, failed, refused, effected, reads}, errors}."""
    ok = failed = refused = effected = reads = world = 0
    errors: list[str] = []
    flags: list[str] = []
    looped = False
    for name, p in _phases(rec):
        err = _model_error(p)
        if err:
            errors.append(f"{name}: {err}")
        if p.get("looped"):
            looped = True
        if p.get("capped") is True and "capped" not in flags:
            flags.append("capped")
        if p.get("window_full") and "window_full" not in flags:
            flags.append("window_full")
        for t in p.get("trace") or ():
            if not isinstance(t, dict):
                continue
            eff = t.get("effector")
            if t.get("ok"):
                ok += 1
                if eff in EFFECTING:
                    effected += 1
                    world += eff not in OWN_RECORDS
                elif eff in READS:
                    reads += 1
            elif t.get("refused"):
                refused += 1
            else:
                failed += 1
    if errors and ok:
        flags.append("model_error")
    tried = ok + failed + refused
    if errors and not ok:
        cls = "mute"
    elif looped:
        cls = "looped"
    elif world:
        cls = "worked"
    elif effected:
        cls = "noted"
    elif failed + refused >= STUCK_MIN:
        cls = "stuck"
    elif ok:
        cls = "read-only"
    else:
        cls = "idle"
        if tried:
            flags.append("failed_acts")
    return {
        "ts": rec.get("ts"),
        "cls": cls,
        "flags": flags,
        "acts": {"ok": ok, "failed": failed, "refused": refused, "effected": effected, "reads": reads,
                 "world": world},
        "errors": errors,
        "elapsed_s": rec.get("elapsed_s"),
    }


def _parse(line: bytes):
    line = line.strip()
    if not line:
        return None
    try:
        rec = json.loads(line.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    return rec if isinstance(rec, dict) else None


def iter_beats_newest_first(instance: Path, block: int = 1 << 20):
    """Beat records from the end of heartbeats.jsonl backwards, reading only as far as the caller pulls.
    legion-being's record is ~250 MB; the being's view needs the last dozen."""
    path = Path(instance) / "heartbeats.jsonl"
    if not path.exists():
        return
    with path.open("rb") as fh:
        fh.seek(0, 2)
        pos = fh.tell()
        tail = b""
        while pos > 0:
            step = min(block, pos)
            pos -= step
            fh.seek(pos)
            chunk = fh.read(step) + tail
            lines = chunk.split(b"\n")
            tail = lines[0]          # may be a partial line; completed by the next (earlier) block
            for line in reversed(lines[1:]):
                rec = _parse(line)
                if rec is not None:
                    yield rec
        rec = _parse(tail)
        if rec is not None:
            yield rec


def read_beats(instance: Path, last: int | None = None) -> list[dict]:
    out: list[dict] = []
    for rec in iter_beats_newest_first(instance):
        out.append(rec)
        if last and len(out) >= last:
            break
    out.reverse()
    return out


def mute_run(instance: Path, within: int | None = None) -> dict | None:
    """The newest run of mute beats that touches the last `within` beats (all of history when None):
    {n, first, last, error, ongoing}. Counts back past `within` to where the run began, so a being shown
    a dozen beats is told the whole outage, not the dozen. None when no mute beat is in reach."""
    n, first, last, error, ongoing = 0, None, None, None, False
    for i, rec in enumerate(iter_beats_newest_first(instance)):
        r = classify(rec)
        if r["cls"] == "mute":
            if n == 0:
                last, ongoing = rec.get("ts"), (i == 0)
                error = r["errors"][0].split(": ", 1)[-1] if r["errors"] else "model error"
            n, first = n + 1, rec.get("ts")
        elif n:
            break
        elif within is not None and i + 1 >= within:
            return None
    if not n:
        return None
    return {"n": n, "first": first, "last": last, "error": error, "ongoing": ongoing}


def dead_seconds_since(instance: Path, ts_iso: str) -> float:
    """Clock time since `ts_iso` that the being did not live through: the summed duration of MUTE beats that
    started at or after it. A window measured in hours (unanswered(): "after max_age_h an unanswered turn is a
    choice the being made") must subtract this, or an outage longer than the window files every waiting turn
    as history. 11-09: dp's 11-08 turn was selected to be answered in 163 mute beats, then aged out 27 h later
    in the first live beat, which marked it seen with no reply."""
    dead = 0.0
    for rec in iter_beats_newest_first(instance):
        ts = rec.get("ts") or ""
        if ts < ts_iso:
            break
        if classify(rec)["cls"] == "mute":
            try:
                dead += float(rec.get("elapsed_s") or 0.0)
            except (TypeError, ValueError):
                pass
    return dead


def streak(classes: list[str]) -> tuple[str | None, int]:
    """The class of the newest beat and how many beats in a row (newest backwards) share it."""
    if not classes:
        return None, 0
    head = classes[-1]
    n = 0
    for c in reversed(classes):
        if c != head:
            break
        n += 1
    return head, n


def summary(beats: list[dict]) -> dict:
    rows = [classify(b) for b in beats]
    classes = [r["cls"] for r in rows]
    head, run = streak(classes)
    alarm = None
    if head in ALARM_STREAK and run >= ALARM_STREAK[head]:
        alarm = f"{run} {head} beat(s) in a row, newest {rows[-1]['ts']}"
    return {
        "beats": len(rows),
        "counts": dict(Counter(classes)),
        "newest": rows[-1] if rows else None,
        "streak": {"cls": head, "n": run},
        "alarm": alarm,
        "rows": rows,
    }


def outages(beats: list[dict], cls: str = "mute") -> list[dict]:
    """Every maximal run of `cls` beats: {start, end, n}. The history view of what an alarm would have caught."""
    out: list[dict] = []
    cur = None
    for b in beats:
        r = classify(b)
        if r["cls"] == cls:
            if cur is None:
                cur = {"start": r["ts"], "end": r["ts"], "n": 0}
            cur["end"] = r["ts"]
            cur["n"] += 1
        elif cur is not None:
            out.append(cur)
            cur = None
    if cur is not None:
        out.append(cur)
    return out


def render(s: dict, width: int = 12) -> str:
    """A few lines for a human (or the being): the last `width` beats as a strip, the counts, any alarm."""
    letters = LETTERS
    strip = "".join(letters.get(r["cls"], "?") for r in s["rows"][-width:])
    counts = ", ".join(f"{k} {v}" for k, v in sorted(s["counts"].items(), key=lambda kv: -kv[1]))
    lines = [f"last {min(width, s['beats'])} beats (oldest→newest): {strip}   "
             "W worked · n noted · r read-only · . idle · S stuck · L looped · M mute",
             f"of {s['beats']}: {counts}"]
    if s["alarm"]:
        lines.append(f"ALARM: {s['alarm']}")
        newest = s["newest"] or {}
        for e in (newest.get("errors") or [])[:3]:
            lines.append(f"  {e}")
    return "\n".join(lines)


def stated_step(rec: dict) -> str | None:
    """What the being said it would do next, in its own words: next_beat.stay_awake when the BEING wrote it.
    The harness writes there too ("harness: the window reached its floor ..."); that is not an intention."""
    nb = rec.get("next_beat")
    s = nb.get("stay_awake") if isinstance(nb, dict) else None
    if not isinstance(s, str) or not s.strip() or s.startswith("harness:"):
        return None
    return s.strip()


def acts_by_kind(rec: dict) -> dict:
    """The beat's acts by effector, in three plain groups: {world: Counter, own: Counter, failed: Counter,
    reads: int}. Names only, as the record has them: nothing here decides what an act was FOR."""
    world, own, failed = Counter(), Counter(), Counter()
    reads = 0
    for _, p in _phases(rec):
        for t in p.get("trace") or ():
            if not isinstance(t, dict):
                continue
            eff = str(t.get("effector"))
            if not t.get("ok"):
                failed[eff] += 1
            elif eff in OWN_RECORDS:
                own[eff] += 1
            elif eff in EFFECTING:
                world[eff] += 1
            elif eff in READS:
                reads += 1
    return {"world": world, "own": own, "failed": failed, "reads": reads}


def _counted(c: Counter) -> str:
    return ", ".join(f"{k}×{v}" for k, v in c.most_common()) or "nothing"


def render_stated_steps(beats: list[dict], n: int = 3) -> list[str]:
    """Up to `n` newest (said, then did) pairs: a beat's stated next step beside the acts of the beat after it.
    The being's sentence and the record's act names, side by side and unjudged. This deliberately does NOT
    match words to verbs: a check keyed on a verb list missed this being once already (#585 fired 0/5 when its
    work had moved to an unlisted verb), and the being is the one who knows what its sentence meant."""
    pairs = [(a, b) for a, b in zip(beats, beats[1:]) if stated_step(a)]
    if not pairs:
        return []
    lines = ["## What you said you would do next, and what the next beat did (your own record, unjudged)"]
    for a, b in pairs[-n:]:
        k = acts_by_kind(b)
        said = stated_step(a)
        said = said if len(said) <= 240 else said[:237] + "..."
        lines.append(f"- {(a.get('ts') or '')[11:16]}Z you wrote: \"{said}\"")
        lines.append(f"  next beat ({(b.get('ts') or '')[11:16]}Z): outside your notes: {_counted(k['world'])}"
                     f" · your notes: {_counted(k['own'])} · failed: {_counted(k['failed'])} · reads: {k['reads']}")
    return lines


def render_for_being(instance: Path, width: int = 12) -> str:
    """The being's own view, for the NOW part of its window: its last beats as a strip, and — when its
    newest beats were mute — plainly that they never reached its model, so nothing planned in them
    happened. A being coming back from an outage otherwise reads a todo and a handoff written as if no
    time passed. Empty when there is no record."""
    beats = read_beats(Path(instance), width)
    if not beats:
        return ""
    rows = [classify(b) for b in beats]
    letters = LETTERS
    strip = "".join(letters.get(r["cls"], "?") for r in rows)
    # The legend on its own labelled line: inline after the strip, the being read past it and asked for one
    # (legion-being asked dp for one on 2026-11-10 02:14Z, saying it would make the strip usable to it).
    lines = ["## Your last beats, read from your own record (oldest → newest)",
             strip,
             "Legend: W you acted outside your own notes (a game move, a run, something said or posted) · "
             "n you only wrote your own notes, memories or plans · r you only read · . no act succeeded · "
             "S three or more acts failed or were refused · L the loop guard stopped you · "
             "M your model never answered"]
    lines += render_stated_steps(beats)
    # Mute beats BEFORE this one: the strip ends with the newest finished beat, and this beat is running,
    # so the model is answering now. Say how long it was gone, measured, not guessed.
    run = mute_run(Path(instance), within=width)
    if run:
        lines.append(
            f"{run['n']} of your beats, from {run['first']} to {run['last']}, never reached your model: every "
            f"call to it failed (\"{run['error']}\"). That was the machine, not you, and it is "
            "answering again now (you are reading this). The clock moved on through those dates, but you did not: nothing you planned for those "
            "beats happened, so a todo item or a handoff written before them is exactly as far along as it "
            "says, and anyone who wrote to you in that time had no reply from you then.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--instance", required=True)
    ap.add_argument("--last", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true", help="exit 3 when the newest beats raise an alarm")
    ap.add_argument("--outages", action="store_true", help="list every mute run in the whole history")
    a = ap.parse_args(argv)
    if a.outages:
        runs = outages(read_beats(Path(a.instance)))
        if a.json:
            print(json.dumps(runs))
        else:
            for r in runs:
                print(f"{r['start']} → {r['end']}  {r['n']} mute beat(s)")
        return 0
    s = summary(read_beats(Path(a.instance), a.last))
    if a.json:
        print(json.dumps({k: v for k, v in s.items() if k != "rows"} | {"classes": [r["cls"] for r in s["rows"]]}))
    else:
        print(render(s, width=a.last))
    return 3 if (a.check and s["alarm"]) else 0


if __name__ == "__main__":
    sys.exit(main())
