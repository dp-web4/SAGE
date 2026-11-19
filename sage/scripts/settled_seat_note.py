#!/usr/bin/env python3
"""Put a seat's later word beside one of the being's settled entries (being_settled.seat_note).

For a seat, after it has TOLD the being, in their conversation, that a settled entry does not hold. The note
points at that turn: who sent it, its seq, and one sentence. Every beat then shows it after the entry, until
the being settles that entry again or reopens it. The entry itself is never changed: which holds is the being's.

  python3 sage/scripts/settled_seat_note.py --instance <home> --entry s163 --by sprout-claude --seq 2906 \\
      "There is no sprout account on this machine; the seat runs as dp."

--conv names the conversation when it is not the seat's own (default: --by). Refused, with nothing written,
unless the entry exists and seq is the seat's own turn, sent after the entry was settled.
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sage.gateway import being_settled  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--instance", default=os.environ.get("SAGE_INSTANCE"), help="the being's home (or SAGE_INSTANCE)")
    ap.add_argument("--entry", required=True, help="settled entry id, e.g. s163")
    ap.add_argument("--by", default=os.environ.get("SAGE_SEAT"), help="the seat (or SAGE_SEAT)")
    ap.add_argument("--seq", required=True, type=int, help="the seat's turn that disagrees")
    ap.add_argument("--conv", default=None, help="conversation id (default: --by)")
    ap.add_argument("says", help=f"one sentence, at most {being_settled.SEAT_NOTE_MAX_CHARS} characters")
    a = ap.parse_args(argv)
    if not a.instance or not a.by:
        ap.error("--instance and --by are needed (or SAGE_INSTANCE and SAGE_SEAT)")
    try:
        note = being_settled.seat_note(a.instance, a.entry, a.by, a.seq, a.says, conv_id=a.conv)
    except ValueError as e:
        print(f"not written: {e}", file=sys.stderr)
        return 2
    print(json.dumps(note, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
