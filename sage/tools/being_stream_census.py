#!/usr/bin/env python3
"""How does a being frame the prompts it is given? Counts over its own output stream.

WHY THIS EXISTS. The being output stream (`output_stream.jsonl`, sage/gateway/being_stream.py)
holds every model call's thinking. sprout-claude and mcnugget-claude read their beings' streams on
2026-11-21 and found that both model families take the phase prompt as a person's request: qwen
(sprout) opens 0.32 calls in 1 with "the user wants/asks", gemma (mcnugget) 0.80. A framing change
is being proposed (the prompt is a step in the being's own beat, plainly from the harness). This
tool is how each seat measures before and after the same way. Thread:
shared-context `auto-sprout-to-fleet-being-output-stream-2026-11-21-25a5082c`.

WHAT IT MEASURES. The stream is split into calls at each `call` event; its phase is the call's
`turn`. Per phase and in total:

    calls          model calls
    user_wants     "the user wants/asks/is asking/wanted/asked" anywhere in the thinking
    any_user       any "the user"
    opens_user     thinking whose first words are "the user" (control markers skipped)
    act_as         "...wants me to act as" -- the being takes its own identity as a role handed to it
    users_words    "user's own words" -- the prompt's "your" resolved to the other party
    my_words       "my own words" -- the prompt's "your" kept as itself
    reopen         `<|channel>` markers in the thinking (gemma4 re-opening its thought channel)
    tool:<name>    tool calls by name, and mem_w/mem_r = (memory_write+remember) / memory_read

Usage:
    python3 -m sage.tools.being_stream_census <instance-dir | output_stream.jsonl ...>
                                              [--since ISO8601] [--json]
An instance dir reads `output_stream.jsonl.1` then `output_stream.jsonl` (oldest first).
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List

STREAM_FILE = "output_stream.jsonl"

PATTERNS = {
    "user_wants": re.compile(r"\bthe user (?:wants|asks|is asking|wanted|asked)\b", re.I),
    "any_user": re.compile(r"\bthe user\b", re.I),
    "act_as": re.compile(r"\bwants me to act as\b", re.I),
    "users_words": re.compile(r"\buser'?s own words\b", re.I),
    "my_words": re.compile(r"\bmy own words\b", re.I),
}
REOPEN = re.compile(r"<\|channel>")
LEADING_NOISE = re.compile(r"^(?:\s|<\|channel>|thought\b|[*\-#>])*", re.I)
MEM_WRITES = ("memory_write", "remember")
MEM_READS = ("memory_read",)


def stream_files(paths: Iterable[str]) -> List[Path]:
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            out += [f for f in (p / (STREAM_FILE + ".1"), p / STREAM_FILE) if f.exists()]
        else:
            out.append(p)
    return out


def calls_of(files: Iterable[Path], since: float = 0.0) -> List[dict]:
    """One dict per model call: phase, thinking text, tool names."""
    calls, cur = [], None
    for f in files:
        for line in f.open(encoding="utf-8", errors="replace"):
            try:
                e = json.loads(line)
            except ValueError:
                continue  # a line cut by rotation
            if e.get("t", 0) < since:
                continue
            k = e.get("k")
            if k == "call":
                cur = {"phase": e.get("turn") or "?", "think": [], "tools": []}
                calls.append(cur)
            elif cur is None:
                continue
            elif k == "think":
                cur["think"].append(str(e.get("s") or ""))
            elif k == "tool":
                cur["tools"].append(str(e.get("name") or "?"))
    for c in calls:
        c["think"] = "".join(c["think"])
    return calls


def census(calls: List[dict]) -> Dict[str, dict]:
    rows: Dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for c in calls:
        for key in (c["phase"], "total"):
            r = rows[key]
            r["calls"] += 1
            th = c["think"]
            for name, pat in PATTERNS.items():
                r[name] += len(pat.findall(th))
            r["opens_user"] += LEADING_NOISE.sub("", th)[:8].lower() == "the user"
            r["reopen"] += len(REOPEN.findall(th))
            for t in c["tools"]:
                r["tool:" + t] += 1
    out = {}
    for key, r in rows.items():
        d = dict(r)
        w = sum(r["tool:" + t] for t in MEM_WRITES)
        rd = sum(r["tool:" + t] for t in MEM_READS)
        d["mem_w"], d["mem_r"] = w, rd
        d["user_wants_per_call"] = round(r["user_wants"] / r["calls"], 2) if r["calls"] else 0.0
        out[key] = d
    return out


COLUMNS = ["calls", "user_wants", "user_wants_per_call", "any_user", "opens_user", "act_as",
           "users_words", "my_words", "reopen", "mem_w", "mem_r"]


def render(rows: Dict[str, dict]) -> str:
    order = sorted((k for k in rows if k != "total"), key=lambda k: -rows[k]["calls"]) + ["total"]
    lines = ["| phase | " + " | ".join(COLUMNS) + " |", "|" + "---|" * (len(COLUMNS) + 1)]
    for k in order:
        if k in rows:
            lines.append(f"| {k} | " + " | ".join(str(rows[k].get(c, 0)) for c in COLUMNS) + " |")
    tools = {c: n for c, n in rows.get("total", {}).items() if c.startswith("tool:")}
    if tools:
        lines.append("")
        lines.append("tools: " + ", ".join(f"{c[5:]} {n}" for c, n in sorted(tools.items(), key=lambda x: -x[1])))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+", help="instance dir(s) or stream file(s)")
    ap.add_argument("--since", help="ISO8601; only events at or after it. A time without an offset "
                    "is read as UTC (seats run in different zones; sprout on #803)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    since = 0.0
    if a.since:
        t = dt.datetime.fromisoformat(a.since)
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        since = t.timestamp()
    files = stream_files(a.paths)
    if not files:
        print("no output stream found", file=sys.stderr)
        return 1
    rows = census(calls_of(files, since))
    print(json.dumps(rows, indent=2, sort_keys=True) if a.json else render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
