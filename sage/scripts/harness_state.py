#!/usr/bin/env python3
"""Is the code the beings run reviewed main? One command, one exit code.

Every heartbeat records `harness` (head, dirty digest, on_main, state) and prints a
LIVE TREE line to stderr when the state is not clean. This reads the same fact without
waiting for a beat, and shows what each being's LAST beat actually ran — which can differ
from the tree now if someone edited it since.

    python3 -m sage.scripts.harness_state [--workspace DIR] [--json]

Exit 0 when the live tree is clean (at a commit reachable from origin/main, no source
edits outside sage/instances); 1 when dirty, unmerged or unreadable. Does not fetch.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sage.gateway.heartbeat import harness_alarm, harness_revision


def last_beats(workspace: Path) -> dict:
    out = {}
    for hb in sorted((workspace / "sage" / "instances").glob("*/heartbeats.jsonl")):
        try:
            with hb.open("rb") as f:
                f.seek(0, 2); f.seek(max(0, f.tell() - 262144))
                tail = f.read().decode(errors="replace").splitlines()
        except OSError:
            continue
        for line in reversed(tail):
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            h = rec.get("harness")
            if isinstance(h, dict):
                out[hb.parent.name] = {"ts": rec.get("ts"), "identity": h.get("identity") or h.get("short"),
                                       "state": h.get("state") or ("dirty" if h.get("dirty") else "unrecorded")}
                break
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    ws = Path(a.workspace)
    rev = harness_revision(str(ws))
    beats = last_beats(ws)
    if a.json:
        print(json.dumps({"live": rev, "last_beats": beats}, indent=2))
    else:
        print(harness_alarm(rev) or f"LIVE TREE CLEAN: {rev.get('identity')} on {rev.get('branch')}, "
                                    f"reachable from {rev.get('main_ref')}")
        for name, b in beats.items():
            print(f"  {name}: last beat {b['ts']} ran {b['identity']} ({b['state']})")
    return 0 if rev.get("state") == "clean" else 1


if __name__ == "__main__":
    sys.exit(main())
