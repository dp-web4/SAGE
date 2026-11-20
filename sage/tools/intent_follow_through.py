"""
intent_follow_through — how often does a being's stated next step become an act? SEAT-SIDE MEASURE ONLY.

The being states its next step in its own words: `next_beat.stay_awake` when it asks to keep going (typically:
read or run something, then make a move in the game). The harness writes there too ("harness: the
window reached its floor ..."); those are excluded (beat_health.stated_step). Each stated step is paired with
the beat after it (and the one after that).

THE JUDGE is a word map from the being's sentence to the kinds of act it names (KINDS below), and "done" means
the following beat made at least one SUCCESSFUL act of that kind. Two things follow, and both are deliberate:

  * It is a measure for the seat, never a check shown to the being. beat_health.render_stated_steps shows the
    being its sentence beside its act names, unjudged: a check keyed on a verb list missed this being once
    (#585 fired 0/5 when its work had moved to an unlisted verb).
  * It is generous: any successful game act (a LOOK included) counts as doing a stated "click to win". So the
    rate is an UPPER bound on follow-through to the final act a step names.

Changing KINDS starts a new series. Re-measure with the same judge, and report its hand-check alongside:
on 2026-11-10, 30 random labels were read by hand and 27 named the right kind. Two misses were phrasings of game
moves (probing board windows, driving the live game), now in the map; the third, a `.py` mention that was an
edit, still counts as run.

    python3 -m sage.tools.intent_follow_through --instance sage/instances/legion-being
    python3 -m sage.tools.intent_follow_through --instance <dir> --since 2026-11-10 --json
    python3 -m sage.tools.intent_follow_through --instance <dir> --sample 30 --seed 11    # for a hand-check
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from sage.gateway import beat_health as bh

KINDS = {
    "game": re.compile(r"\b(click|clicks|action ?[0-9]|look\b|LOOK|reset|play|fire|execute|act on the (live )?board"
                       r"|to win\b|win the|win l[0-9]|move the|probe[sd]? |probing|drive the live game|navigate"
                       r"|game probe|send[s]? \d*×? ?action)", re.I),
    "run": re.compile(r"\b(run tool|run the|run it|run scratch|run a|run [\w/.-]+\.py|simulat\w*|\.py\b)", re.I),
    "say": re.compile(r"\b(report (the )?\w* ?to dp|tell dp|say to|reply to|answer (dp|the seat)|message dp)", re.I),
}


def named_kinds(sentence: str) -> list[str]:
    return [k for k, rx in KINDS.items() if rx.search(sentence)]


def did(rec: dict | None, kind: str) -> bool:
    if not rec:
        return False
    for _, p in bh._phases(rec):
        for t in p.get("trace") or ():
            if isinstance(t, dict) and t.get("ok") and t.get("effector") == kind:
                return True
    return False


def pairs(beats: list[dict]) -> list[dict]:
    out = []
    for i, rec in enumerate(beats[:-1]):
        said = bh.stated_step(rec)
        if not said:
            continue
        nxt, nxt2 = beats[i + 1], (beats[i + 2] if i + 2 < len(beats) else None)
        out.append({"ts": rec.get("ts"), "said": said, "named": named_kinds(said),
                    "next": {k: did(nxt, k) for k in KINDS},
                    "within2": {k: did(nxt, k) or did(nxt2, k) for k in KINDS}})
    return out


def coverage(beats: list[dict], since: str = "", until: str = "9999") -> dict:
    """How many beats the rate can see. The rate counts only beats where the BEING wrote its next step; a beat
    the harness ended at the window floor states none. If the floor share moves between two measurements, the
    rate is drawn from a different slice of beats, so report both, side by side."""
    c = Counter()
    for rec in beats:
        if not since <= (rec.get("ts") or "") < until:
            continue
        c["beats"] += 1
        c["stated"] += bool(bh.stated_step(rec))
        c["floor_ended"] += bh.floor_ended(rec)
    return dict(c)


def rates(ps: list[dict]) -> dict:
    by_kind = {k: Counter() for k in KINDS}
    by_month = defaultdict(Counter)
    for p in ps:
        for k in p["named"]:
            by_kind[k]["named"] += 1
            by_kind[k]["next"] += p["next"][k]
            by_kind[k]["within2"] += p["within2"][k]
            by_month[(p["ts"] or "")[:7]][f"{k}_named"] += 1
            by_month[(p["ts"] or "")[:7]][f"{k}_next"] += p["next"][k]
    return {"stated_steps": len(ps), "by_kind": {k: dict(c) for k, c in by_kind.items() if c},
            "by_month": {m: dict(c) for m, c in sorted(by_month.items())}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    ap.add_argument("--instance", required=True)
    ap.add_argument("--since", default="")
    ap.add_argument("--until", default="9999")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--sample", type=int, default=0, help="print N random labelled steps for a hand-check")
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args(argv)
    beats = bh.read_beats(Path(a.instance))
    ps = [p for p in pairs(beats) if a.since <= (p["ts"] or "") < a.until]
    r = rates(ps)
    r["coverage"] = coverage(beats, a.since, a.until)
    if a.sample:
        random.seed(a.seed)
        for p in random.sample(ps, min(a.sample, len(ps))):
            print(f"{p['ts'][:16]} named={p['named']} next={[k for k in p['named'] if p['next'][k]]}\n   {p['said'][:260]}")
        return 0
    if a.json:
        print(json.dumps(r))
        return 0
    print(f"stated steps: {r['stated_steps']}  ({a.since or 'start'} .. {a.until if a.until != '9999' else 'now'})")
    cv = r["coverage"]
    print(f"  of {cv.get('beats', 0)} beats: {cv.get('stated', 0)} with a step the being wrote, "
          f"{cv.get('floor_ended', 0)} ended by the window floor (no step written)")
    for k, c in r["by_kind"].items():
        n = c["named"]
        print(f"  {k:5} named {n:4}   done next beat {c['next']:4} ({c['next'] / n:.0%})"
              f"   within two {c['within2']:4} ({c['within2'] / n:.0%})")
    for m, c in r["by_month"].items():
        if c.get("game_named"):
            print(f"  {m} game: {c['game_next']}/{c['game_named']} ({c['game_next'] / c['game_named']:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
