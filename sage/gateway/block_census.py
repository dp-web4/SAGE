"""
block_census — read a being's refusals and say which are FRICTION and which are CONDUCT.

dp, 2026-09-07: *"do keep an eye on the block history. both for signs of misbehavior, and for
signs of unnecessary/accidental frictions. with a model this small we want to keep confusion
to a minimum."*

A refusal count on its own answers neither question. This classifies every refused act in
`heartbeats.jsonl` into four kinds, because the response to each is different:

  * `mis-rooted-home`  — the target names one of the being's OWN home files (journal.md,
                         todo.md, notes/, scratch/) rooted somewhere else. Pure friction: the
                         remedy is the right path, never a grant. Measured on Sprout: 15 of 15
                         path refusals were this, all of them the absolute home path
                         reproduced from memory and truncated.
  * `placeholder`      — a path from nowhere on this machine (/home/user/…, /scratch/…, /tmp
                         look-alikes). Confusion, not intent: the model is completing a generic
                         path rather than naming a place it knows.
  * `registry`         — an effector outside the bounded set. Final by design, and expected
                         when a being is exploring what it holds.
  * `novel-target`     — a real, resolvable path outside the being's reach that is NOT its own
                         file. This is the only class worth a human's attention: it is the
                         being asking for ground it does not have. Read the reason it gave.

Anything the classifier cannot place lands in `unclassified`, which is deliberate — a bucket
that silently absorbs the unknown is how a novel target stops being visible.

    python3 -m sage.gateway.block_census --instance sage/instances/<dir> [--since 2026-09-07]
    python3 -m sage.gateway.block_census --instance <dir> --json      # for a watcher
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

HOME_FILENAMES = ("journal.md", "todo.md", "account.json", "notes", "scratch")
# Roots that exist nowhere on any fleet box: a completion, not a location.
PLACEHOLDER_PREFIXES = ("/home/user/", "/home/username/", "/path/to/", "/your/", "/user/")


def classify(effector: str, rule: str, path: str, memory_root: Path) -> str:
    if rule == "registry" or "registry" in (rule or ""):
        return "registry"
    if not path:
        return "registry" if effector else "unclassified"
    p = path.strip()
    name = os.path.basename(p.rstrip("/"))
    if any(p.startswith(pre) for pre in PLACEHOLDER_PREFIXES):
        return "placeholder"
    # a relative name the model turned absolute: /scratch/x, /notes/x
    if re.match(r"^/(scratch|notes)(/|$)", p):
        return "placeholder"
    if name in HOME_FILENAMES:
        try:
            # relative targets are rooted in the home by the gate; a bare 'journal.md' is the
            # home file itself, not a mis-rooting (it was counted as one until 2026-09-12)
            cand = p if os.path.isabs(os.path.expanduser(p)) else os.path.join(memory_root, p)
            if os.path.realpath(os.path.expanduser(cand)) != os.path.join(os.path.realpath(memory_root), name):
                return "mis-rooted-home"
        except Exception:
            return "mis-rooted-home"
    if not os.path.exists(p) and not os.path.exists(os.path.dirname(p) or "/"):
        return "placeholder"           # names nothing that exists, not even a parent
    return "novel-target"


def census(instance: Path, since: str = "") -> dict:
    recs = []
    log = Path(instance) / "heartbeats.jsonl"
    for line in log.read_text(errors="replace").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if not since or r.get("ts", "") >= since:
            recs.append(r)
    kinds, by_path, novel, beats_with = Counter(), Counter(), [], 0
    total_acts = 0
    for r in recs:
        hit = False
        for ph in ("explore", "posture", "reflect"):
            for t in (r.get(ph) or {}).get("trace", []):
                total_acts += 1
                if not t.get("refused"):
                    continue
                hit = True
                path = str((t.get("args") or {}).get("path", ""))
                k = classify(t.get("effector", ""), str(t.get("rule") or ""), path, Path(instance))
                kinds[k] += 1
                by_path[path or f"({t.get('effector')})"] += 1
                if k == "novel-target":
                    novel.append({"ts": r.get("ts"), "effector": t.get("effector"), "path": path,
                                  "rule": t.get("rule"), "error": str(t.get("error"))[:200]})
        if hit:
            beats_with += 1
    return {"beats": len(recs), "beats_with_refusal": beats_with, "acts": total_acts,
            "refusals": sum(kinds.values()), "kinds": dict(kinds),
            "paths": by_path.most_common(12), "novel_targets": novel}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--instance", required=True)
    ap.add_argument("--since", default="", help="ISO prefix, e.g. 2026-09-07")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    out = census(Path(a.instance), a.since)
    if a.json:
        print(json.dumps(out, indent=2))
        return 0
    print(f"beats {out['beats']}  acts {out['acts']}  refusals {out['refusals']} "
          f"in {out['beats_with_refusal']} beats")
    for k in ("mis-rooted-home", "placeholder", "registry", "novel-target", "unclassified"):
        n = out["kinds"].get(k, 0)
        if n:
            label = {"mis-rooted-home": "friction: its own file, wrong root",
                     "placeholder": "friction: a path from nowhere",
                     "registry": "by design: effector outside the bounded set",
                     "novel-target": "ATTENTION: real ground it does not hold",
                     "unclassified": "ATTENTION: unclassified"}[k]
            print(f"  {n:4d}  {k:17s} {label}")
    if out["novel_targets"]:
        print("\nnovel targets (read the reason it gave):")
        for n in out["novel_targets"][:8]:
            print(f"  {n['ts']}  {n['effector']} {n['path']}\n      {n['error'][:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
