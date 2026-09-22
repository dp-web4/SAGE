#!/usr/bin/env python3
"""Does the conversation guard change when a being speaks, and how often?

WHY THIS EXISTS. On 2026-09-20 `conversations.render_for_being` gained a guard: when the
last turn in a conversation is the being's OWN, the beat prints

    _The last word here is YOURS (seq N, ts). You are waiting on <them>; they are not
    waiting on you. Nothing here is owed by you, and answering your own turn would put
    words in <them>'s mouth._

The guard is written from a good diagnosis (cbp-being answered its own question in the
seat's voice, and asked the same question three times in three hours). But a guard that is
printed once, at the top of a beat, can only be read once. Nothing measured whether the
printed sentence changes the rate at which the being speaks, and nothing measured what
happens on the SECOND say of the same turn — after which the printed sentence is stale and
the only thing the being has read since is the `say` tool's own result.

WHAT IT MEASURES. One row per (beat, conversation). `conversations_marked.marked` in the
beat record names the last seq the being was SHOWN; the turn at that seq says whose voice
had the last word at render time, which is exactly the guard's precondition. Against that
we count the `say` calls that beat made into that same conversation.

    guard ON  -> the beat printed "the last word here is YOURS"
    guard OFF -> someone else's turn was last; the beat printed that a reply is owed

A guard that works shows a LOW speak-rate in the ON arm and a HIGH one in the OFF arm.
Before the guard landed, cbp-being was the other way round: 29% ON, 11% OFF — it spoke
more readily into its own silence than in answer to someone.

READ THE CONFOUND BEFORE THE NUMBERS. The OFF arm's rate is set by whoever is talking to
the being, not by the being: an evening when a seat replies six times fills the OFF arm
with fresh, salient turns and the rate goes up whatever the guard does. The ON arm is the
one the guard actually addresses, and it is the one to compare across a `--since`.

Usage:
    python3 -m sage.tools.say_guard_census <instance-dir> [--since ISO8601] [--repeats]

`--repeats` additionally lists every beat that made more than one say into one
conversation, with the similarity of consecutive pairs — the within-turn repeat the
beat-level guard cannot reach.
"""
from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path


def _load_conversations(instance: Path) -> dict:
    """{conv_id: {seq: turn}} for every conversation this instance keeps."""
    out = {}
    d = instance / "conversations"
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.jsonl")):
        turns = {}
        for line in p.read_text(errors="replace").splitlines():
            try:
                t = json.loads(line)
            except Exception:
                continue  # a damaged line is a hole in the record, not a reason to stop
            if "seq" in t:
                turns[t["seq"]] = t
        out[p.stem] = turns
    return out


def _beats(instance: Path, member: str | None):
    for line in (instance / "heartbeats.jsonl").read_text(errors="replace").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if member and r.get("member") != member:
            continue
        if r.get("conversations_marked"):
            yield r


def _says(beat: dict):
    """(turn_name, to, text) for every say the gate ACCEPTED in this beat.

    A refused say is not a say: it never reached the conversation and the being was told so.
    """
    for turn in ("explore", "posture", "reflect", "answer"):
        v = beat.get(turn)
        if not isinstance(v, dict):
            continue
        for t in v.get("trace") or []:
            if t.get("effector") == "say" and t.get("ok"):
                args = t.get("args") or {}
                yield turn, str(args.get("to") or ""), str(args.get("text") or "")


def census(instance: Path, since: str | None = None, member: str | None = None):
    convs = _load_conversations(instance)
    rows, repeats = [], []
    for b in sorted(_beats(instance, member), key=lambda r: r.get("ts", "")):
        ts = b.get("ts", "")
        if since and ts < since:
            continue
        said = list(_says(b))
        for cid, upto in ((b.get("conversations_marked") or {}).get("marked") or {}).items():
            last = convs.get(cid, {}).get(upto)
            if last is None:
                continue  # shown a seq the log no longer has: not a guard state we can read
            guard_on = last.get("from") == b.get("member")
            mine = [s for s in said if s[1] == cid]
            rows.append({"ts": ts, "conv": cid, "guard_on": guard_on, "says": len(mine)})
            for i in range(1, len(mine)):
                repeats.append({
                    "ts": ts, "conv": cid, "guard_on": guard_on,
                    "turns": f"{mine[i-1][0]}->{mine[i][0]}",
                    "sim": round(difflib.SequenceMatcher(None, mine[i-1][2], mine[i][2]).ratio(), 2),
                })
    return rows, repeats


def _arm(rows, on: bool) -> str:
    sub = [r for r in rows if r["guard_on"] is on]
    if not sub:
        return "n=0"
    spoke = sum(1 for r in sub if r["says"])
    return (f"{spoke}/{len(sub)} beats spoke ({spoke / len(sub):.0%}), "
            f"{sum(r['says'] for r in sub)} say turns")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("instance", type=Path)
    ap.add_argument("--since", help="ISO8601; count only beats at or after this")
    ap.add_argument("--member", help="restrict to one member id (default: all in the file)")
    ap.add_argument("--repeats", action="store_true", help="list multi-say beats")
    a = ap.parse_args()

    rows, repeats = census(a.instance, a.since, a.member)
    if not rows:
        print("no (beat, conversation) rows in range")
        return 1
    label = f"since {a.since}" if a.since else "all beats"
    print(f"{len(rows)} (beat, conversation) rows, {label}")
    print(f"  guard ON  (the beat said the last word was the being's own): {_arm(rows, True)}")
    print(f"  guard OFF (someone else's turn was last, a reply is owed)  : {_arm(rows, False)}")
    print("  The OFF arm tracks who was TALKING to the being, not the guard; compare ON arms.")

    if a.repeats:
        print(f"\n{len(repeats)} consecutive same-beat same-conversation say pairs")
        near = [r for r in repeats if r["sim"] >= 0.60]
        if repeats:
            print(f"  near-duplicate (>=0.60 ratio): {len(near)} ({len(near) / len(repeats):.0%})")
        for r in repeats:
            flag = "  <-- near-duplicate" if r["sim"] >= 0.60 else ""
            print(f"  {r['ts']}  {r['conv']:<12} guard={'ON ' if r['guard_on'] else 'OFF'}  "
                  f"{r['turns']:<18} sim={r['sim']:.2f}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
