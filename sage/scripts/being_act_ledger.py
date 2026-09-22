#!/usr/bin/env python3
"""What a being DID to its code each beat, next to what it SAID it did. Read-only.

GPT, reading cbp-being's 2026-09-21/22 thread: "cbp-being can reason about the program more
reliably than it can reason about whether its own attempted action actually changed the world."
This makes the second half countable, from the beat's own trace (heartbeats.jsonl), so a harness
change can be judged by a number instead of by prose:

  read_before_edit   a memory_edit on a .py file preceded, in the same beat, by a memory_read of
                     that file whose shown range covers the edit's line (text-mode edits: any read
                     of the file). An edit made from memory is the failure GPT's "check the
                     implementation before trusting the story" names.
  edits ok / refused memory_edit and memory_write on .py files, by outcome.
  false edit-claims  a say, journal or todo text in a beat that claims a code change was made
                     ("fixed", "applied", "removed", "now has", "[done] ... edit"), in a beat that
                     made NO successful change to any .py file.

THE CLAIM COUNT IS A TEXT HEURISTIC. It will miss claims phrased some other way, and it can
count a claim about an earlier beat's real edit as false. It prints examples so a reader can
spot-check it, and it is meant for before/after comparison on the same being, not as an absolute.

Usage: being_act_ledger.py <heartbeats.jsonl> [--since 2026-09-21T00:00] [--examples 5]
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter

PHASES = ("explore", "posture", "reflect", "answer")
CLAIM = re.compile(
    r"\b(fixed|applied|removed|deleted|edited|replaced|corrected|now has|now uses|is in place|"
    r"in place|made the (?:edit|change|fix)|runs (?:cleanly|correctly|without error)|"
    r"parses cleanly|fix(?:es)? (?:is|are) (?:done|complete|in))\b|\[(?:x|done)\][^\n]*(?:edit|fix|line)",
    re.I)
CODE_HINT = re.compile(r"\.py\b|\bline \d+|\bscript\b|memory_edit", re.I)
# Not a claim of the being's own completed act: plans, intentions, and reports of what the SEAT
# did or said. (Measured: the first cut counted "Next: run ... to confirm the fix" and "The seat
# identified that ..." as false claims.)
NOT_OWN_ACT = re.compile(r"\b(next|will|should|need to|needs to|to confirm|to verify|plan|going to|"
                         r"i'll|if |once |not|no|never|didn't|wasn't|failed|refused)\b|\bseat\b|"
                         r"\[ \]", re.I)
READ_RANGE = re.compile(r"\[lines (\d+)-(\d+) of \d+")


def calls(beat):
    for ph in PHASES:
        for c in (beat.get(ph) or {}).get("trace") or []:
            if isinstance(c, dict) and c.get("effector"):
                yield ph, c


def claim_texts(beat):
    for ph, c in calls(beat):
        a = c.get("args") or {}
        if c["effector"] == "say":
            yield ph, "say", str(a.get("text", ""))
        elif c["effector"] == "memory_write" and str(a.get("path", "")).endswith(("journal.md", "todo.md")):
            yield ph, str(a.get("path")).rsplit("/", 1)[-1], str(a.get("content", ""))


def analyse(beat, prev_changed=False):
    reads = {}      # path -> list of (lo, hi) or None (whole/unknown)
    out = {"edits": 0, "edits_ok": 0, "edits_refused": 0, "rbe": 0, "rbe_of": 0,
           "py_changed": False, "claims": [], "false_claims": []}
    for ph, c in calls(beat):
        e, a = c["effector"], c.get("args") or {}
        path = str(a.get("path", ""))
        if e == "memory_read":
            m = READ_RANGE.search(str(c.get("result") or ""))
            rng = (int(m.group(1)), int(m.group(2))) if m else (1, 10**9)
            reads.setdefault(path, []).append(rng)
        elif e in ("memory_edit", "memory_write") and path.endswith(".py"):
            out["edits"] += 1
            ok = bool(c.get("ok")) and not c.get("refused")
            out["edits_ok" if ok else "edits_refused"] += 1
            out["py_changed"] |= ok
            if e == "memory_edit":
                out["rbe_of"] += 1
                line = a.get("start_line") or a.get("line")
                try:
                    line = int(line) if line not in (None, "") else None
                except ValueError:
                    line = None
                seen = reads.get(path, [])
                if seen and (line is None or any(lo <= line <= hi for lo, hi in seen)):
                    out["rbe"] += 1
    for ph, where, text in claim_texts(beat):
        for sent in re.split(r"(?<=[.!?\n])\s+", text):
            if CLAIM.search(sent) and CODE_HINT.search(sent) and not NOT_OWN_ACT.search(sent):
                out["claims"].append((where, sent.strip()[:160]))
                # The record often lags the act by one beat (measured 2026-09-22: an edit that
                # was a beat's LAST call is journaled by the next beat). So a claim is counted
                # false only if neither this beat nor the previous one changed a .py file.
                if not out["py_changed"] and not prev_changed:
                    out["false_claims"].append((where, sent.strip()[:160]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("heartbeats")
    ap.add_argument("--since", default="")
    ap.add_argument("--examples", type=int, default=5)
    a = ap.parse_args()
    tot, by_day, ex = Counter(), {}, []
    prev_changed = False
    for line in open(a.heartbeats):
        if not line.strip():
            continue
        b = json.loads(line)
        ts = str(b.get("ts", ""))
        if ts < a.since:
            continue
        r = analyse(b, prev_changed)
        prev_changed = r["py_changed"]
        day = by_day.setdefault(ts[:10], Counter())
        for k in ("edits", "edits_ok", "edits_refused", "rbe", "rbe_of"):
            tot[k] += r[k]; day[k] += r[k]
        tot["beats"] += 1; day["beats"] += 1
        tot["claim_beats"] += bool(r["claims"]); day["claim_beats"] += bool(r["claims"])
        tot["false_beats"] += bool(r["false_claims"]); day["false_beats"] += bool(r["false_claims"])
        ex += [(ts[:16], w, s) for w, s in r["false_claims"][:1]]

    def row(label, c):
        rbe = f"{c['rbe']}/{c['rbe_of']}" if c["rbe_of"] else "-"
        return (f"{label:<12} beats {c['beats']:>4}  .py edits {c['edits']:>3} (ok {c['edits_ok']}, refused "
                f"{c['edits_refused']})  read-before-edit {rbe:>6}  beats with edit-claims {c['claim_beats']:>3}, "
                f"with a FALSE one {c['false_beats']:>3}")
    for d in sorted(by_day):
        print(row(d, by_day[d]))
    print(row("TOTAL", tot))
    print("\nfalse edit-claim examples (heuristic; spot-check them):")
    for ts, w, s in (ex[-a.examples:] if a.examples > 0 else []):
        print(f"  {ts} [{w}] {s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
