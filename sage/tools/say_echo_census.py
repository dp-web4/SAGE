#!/usr/bin/env python3
"""Can a being's turn be entirely unoriginal and still pass the echo guard?

WHY THIS EXISTS. `conversations.echo_of` (installed at the `say` effector, 2026-09-19) refuses
a turn whose 5-gram shingles are >=75% contained in ONE recent turn by the other party. It was
built from a measured case: the being sent dp's own answer back to dp, 91% verbatim.

On 2026-09-21 01:16Z it let this through (cbp-claude seq 2887):

    "You're right - the mechanism as I've written it is too generic. You may answer with say,
     or leave it. Both are allowed."

Every character of that turn is a verbatim copy of the last 119 characters of the pending block
the reflect prompt had just printed to it:

    - the first sentence is the tail of the other party's turn, truncated at PENDING_CHARS=700
      (the cut lands mid-quote, and the being reproduces the cut);
    - the second is `heartbeat.pending_and_say_line`'s own closing instruction, a PROMPT
      CONSTANT, added 2026-09-17 by the fix that let the answering turn see what it answers.

Two verbatim sources, no original words, and it passed — because containment is scored against
each source SEPARATELY and neither holds enough of it, and because one of the two sources is the
prompt, which a guard that reads only conversation turns structurally cannot see.

WHAT IT MEASURES. One row per `say` turn by the being. Against the same lookback the guard uses:

    guard   = max containment in any ONE recent turn by the other party   (what echo_of scores)
    union   = containment in the UNION of those turns AND the prompt constants
    lifted  = longest verbatim substring shared with any prompt constant (>=MIN_VERBATIM chars)

The blind class is `union >= ECHO_CONTAINED and guard < ECHO_CONTAINED`: a turn with nothing of
its own that no per-source test can reach. Prompt constants are pulled from the live source by
`ast`, so this re-measures rather than quoting a number.

Usage:
    python3 -m sage.tools.say_echo_census <instance-dir> [--conv cbp-claude] [--since ISO8601]
                                          [--list] [--member cbp-being]
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sage.gateway.conversations import (ECHO_CONTAINED, ECHO_GRAM,  # noqa: E402
                                        ECHO_MIN_GRAMS, _shingles)

# A prompt constant has to be long enough that sharing it verbatim is not coincidence. 30 chars
# is ~5 words; the shortest real leak measured so far is 56.
MIN_VERBATIM = 30
LOOKBACK = 4          # echo_of's default
PENDING_CHARS = 700   # heartbeat's truncation of the pending turn


def prompt_constants(*sources: Path) -> list[str]:
    """Every string literal the gateway can hand the being — prompt text and tool-result text —
    split into lines, long enough to be a sentence. Read from source by `ast` so this cannot go
    stale against it.

    DOCSTRINGS ARE EXCLUDED, and that exclusion is the whole reason this function is careful.
    With them in, this census reported 12 turns "lifting a prompt constant verbatim" and 9 of
    them were the being's own false claim -- "the hestia policy daemon has been unreachable for
    ~21 hours" -- matching the docstring in conversations.py that DOCUMENTS that claim. The
    instrument had ingested the write-up of the defect it was measuring and scored the defect as
    its own cause. A docstring is never shown to the being; a module that explains a being's
    error will always contain that error."""
    out = []
    for src in sources:
        tree = ast.parse(src.read_text())
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                body = getattr(node, "body", None) or []
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    docstrings.add(id(body[0].value))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings):
                for line in node.value.split("\n"):
                    line = line.strip()
                    if len(line) >= MIN_VERBATIM:
                        out.append(line)
    return sorted(set(out), key=len, reverse=True)


def longest_verbatim(text: str, corpus: list[str]) -> tuple[int, str]:
    """Longest substring of `text` that appears verbatim in any corpus entry."""
    best = ""
    for i in range(len(text)):
        if len(text) - i <= len(best):
            break
        for j in range(i + len(best) + 1, len(text) + 1):
            span = text[i:j]
            if any(span in c for c in corpus):
                best = span
            else:
                break
    return len(best), best


def containment(g: set, other: str) -> float:
    return len(g & _shingles(other)) / len(g) if g else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("instance", type=Path)
    ap.add_argument("--conv", default=None, help="one conversation id (default: all)")
    ap.add_argument("--member", default=None, help="the being's id (default: instance dir's)")
    ap.add_argument("--since", default=None)
    ap.add_argument("--list", action="store_true", help="print every blind-class turn")
    a = ap.parse_args()

    repo = Path(__file__).resolve().parents[2]
    consts = prompt_constants(repo / "sage/gateway/heartbeat.py",
                              repo / "sage/gateway/conversations.py")
    const_grams = set()
    for c in consts:
        const_grams |= _shingles(c)

    conv_dir = a.instance / "conversations"
    files = ([conv_dir / f"{a.conv}.jsonl"] if a.conv
             else sorted(p for p in conv_dir.glob("*.jsonl")))

    tot = short = guard_hit = blind = lifted_n = 0
    rows = []
    for f in files:
        turns = [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
        member = a.member
        if member is None:
            froms = {t.get("from") for t in turns}
            member = next((x for x in froms if x and x.endswith("-being")), None)
        for i, t in enumerate(turns):
            if t.get("from") != member or t.get("via") != "say":
                continue
            if a.since and (t.get("ts") or "") < a.since:
                continue
            text = (t.get("text") or "").strip()
            g = _shingles(text)
            tot += 1
            if len(g) < ECHO_MIN_GRAMS:
                short += 1          # guard declines to score these at all
                continue
            others = [x for x in turns[max(0, i - LOOKBACK * 3):i]
                      if x.get("from") != member][-LOOKBACK:]
            guard = max([containment(g, x.get("text") or "") for x in others] or [0.0])
            src_grams = set()
            for x in others:
                src_grams |= _shingles(x.get("text") or "")
                # what the pending block actually shows: flattened, cut at PENDING_CHARS
                src_grams |= _shingles(" ".join(str(x.get("text") or "").split())[:PENDING_CHARS])
            union = len(g & (src_grams | const_grams)) / len(g)
            n, span = longest_verbatim(text, consts)
            if n >= MIN_VERBATIM:
                lifted_n += 1
            if guard >= ECHO_CONTAINED:
                guard_hit += 1
            elif union >= ECHO_CONTAINED:
                blind += 1
                rows.append((f.stem, t.get("seq"), t.get("ts"), guard, union, n, span, text))

    print(f"instance {a.instance.name}   say turns scored: {tot}"
          f"   (too short to score: {short})")
    print(f"prompt constants read from source: {len(consts)}"
          f"   bar: {ECHO_CONTAINED} containment of {ECHO_GRAM}-grams")
    print()
    print(f"  guard would refuse (one source >= bar)      {guard_hit:5d}")
    print(f"  BLIND CLASS (union >= bar, no single source){blind:5d}")
    print(f"  turns lifting >={MIN_VERBATIM} chars verbatim from a prompt constant "
          f"{lifted_n:5d}")
    if a.list:
        for stem, seq, ts, guard, union, n, span, text in rows:
            print()
            print(f"--- {stem} seq {seq}  {ts}   guard={guard:.2f}  union={union:.2f}"
                  f"  verbatim-from-prompt={n}")
            print(f"    said: {text[:300]}")
            if n >= MIN_VERBATIM:
                print(f"    lifted: {span[:200]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
