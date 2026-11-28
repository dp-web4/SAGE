#!/usr/bin/env python3
"""Measure local friction in a being's recorded beats (octopus exploration, A0/B0/C0).

Reads a being's daily heartbeat logs (heartbeat/v2, `<day>.jsonl.gz`, one beat per line; each
phase value is a Python repr carrying a `trace` of acts). Calls no model and touches no live
being: it reads files only.

Prints:
  1. survey: acts, model steps and prompt tokens; per-effector refused/failed rates
  2. A0: steps spent going back to a target whose act just failed, and what follows a failed
     memory_edit
  3. trend: weekly rates of three friction classes (per 100 acts)
  4. B0: how predictable the next act is from the previous one (frequency baseline), and how
     often that baseline is confident

Usage: beat_friction.py <heartbeats dir> [--split-frac 0.8]
"""
from __future__ import annotations

import argparse
import ast
import collections
import datetime
import gzip
import json
import pathlib
import re

PHASES = ("explore", "posture", "reflect", "answer", "act_after_answer")


class _Opaque(ast.NodeTransformer):
    """Bare names, calls and arithmetic in a repr become None, so literal_eval accepts it."""

    def _none(self, node):
        return ast.copy_location(ast.Constant(None), node)

    visit_Name = visit_Call = visit_BinOp = _none


def lit(s):
    if s in (None, "None", ""):
        return None
    if not isinstance(s, str):
        return s
    try:
        return ast.literal_eval(s)
    except Exception:
        try:
            return ast.literal_eval(_Opaque().visit(ast.parse(s, mode="eval")))
        except Exception:
            return None


def beats(root):
    for f in sorted(pathlib.Path(root).glob("*.jsonl.gz")):
        with gzip.open(f, "rt", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.strip():
                    try:
                        yield f.name[:10], json.loads(line)
                    except json.JSONDecodeError:
                        pass


def phases(beat):
    for ph in PHASES:
        v = lit(beat.get(ph))
        if isinstance(v, dict):
            gens = [g for g in (v.get("generates") or []) if isinstance(g, dict)]
            acts = [a for a in (v.get("trace") or []) if isinstance(a, dict) and a.get("effector")]
            yield acts, len(gens), sum(g.get("prompt_eval_count") or 0 for g in gens)


def status(a):
    return "refused" if a.get("refused") else ("failed" if a.get("ok") is False else "ok")


def text(a):
    return str(a.get("error") or a.get("note") or a.get("result") or "")


def target(a):
    args = a.get("args")
    if isinstance(args, dict):
        for k in ("path", "file", "script", "to", "query", "pattern", "url"):
            if args.get(k):
                return str(args[k])[:120]
    return None


def week(day):
    d = datetime.date.fromisoformat(day)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("beats")
    ap.add_argument("--split-frac", type=float, default=0.8)
    o = ap.parse_args()

    eff, bad = collections.Counter(), collections.Counter()
    n_beats, elapsed, steps, toks, days = 0, 0.0, 0, 0, set()
    extra, extra_by = 0, collections.Counter()
    after_edit_fail = collections.Counter()
    weeks = collections.defaultdict(collections.Counter)
    seqs = []
    for day, b in beats(o.beats):
        n_beats += 1
        days.add(day)
        try:
            elapsed += float(b.get("elapsed_s") or 0)
        except ValueError:
            pass
        for acts, g, t in phases(b):
            steps += g
            toks += t
            w = weeks[week(day)]
            for a in acts:
                e, s = a["effector"], status(a)
                eff[e] += 1
                bad[(e, s)] += 1
                w["acts"] += 1
                if e == "memory_edit" and s != "ok" and "is not in" in text(a):
                    w["edit_mismatch"] += 1
                if e == "search" and s != "ok":
                    w["search_refused"] += 1
                if e == "peer_ask" and s != "ok" and "already in a conversation" in text(a):
                    w["peer_wrong_door"] += 1
            # A0: what follows EVERY failed memory_edit (chain starts and retries alike).
            for i, a in enumerate(acts):
                if a["effector"] == "memory_edit" and status(a) != "ok":
                    nxt = acts[i + 1] if i + 1 < len(acts) else None
                    if nxt is None:
                        after_edit_fail["<phase ends>"] += 1
                    else:
                        same = "same file" if target(nxt) == target(a) else "other"
                        after_edit_fail[f"{nxt['effector']} ({same})"] += 1
            # A0: after a failed act, the following acts on the same target.
            i = 0
            while i < len(acts):
                a = acts[i]
                if status(a) == "ok":
                    i += 1
                    continue
                t0 = target(a)
                j = i + 1
                while t0 is not None and j < len(acts) and target(acts[j]) == t0:
                    j += 1
                extra += j - i - 1
                extra_by[a["effector"]] += j - i - 1
                i = j
            seqs.append((day, [(a["effector"], status(a)) for a in acts]))

    acts_n = sum(eff.values())
    print(f"== survey: {len(days)} days ({min(days)}..{max(days)}), {n_beats} beats, "
          f"{elapsed / 3600:.0f} h of beat time")
    print(f"model steps {steps}, prompt tokens {toks / 1e6:.1f}M, acts {acts_n}")
    for e, c in eff.most_common(15):
        r, f = bad[(e, "refused")], bad[(e, "failed")]
        print(f"  {e:16} {c:7}  refused {r / c:4.0%}  failed {f / c:4.0%}")

    print(f"\n== A0: acts going back to a target whose act just failed: {extra} "
          f"({extra / max(acts_n, 1):.1%} of acts)")
    print("  by the effector that failed first:", extra_by.most_common(5))
    print(f"  right after a failed memory_edit ({sum(after_edit_fail.values())} failed edits):")
    for k, c in after_edit_fail.most_common(6):
        print(f"    {c:6}  {k}")

    print("\n== trend (per 100 acts): week, acts, edit text-not-found, search refused, "
          "peer_ask to a conversation partner")
    for wk in sorted(weeks):
        c = weeks[wk]
        n = c["acts"] or 1
        print(f"  {wk} {c['acts']:6} {100 * c['edit_mismatch'] / n:6.1f} "
              f"{100 * c['search_refused'] / n:6.1f} {100 * c['peer_wrong_door'] / n:6.1f}")

    ds = sorted(days)
    cut = ds[int(len(ds) * o.split_frac)]
    train = [s for d, s in seqs if d < cut]
    test = [s for d, s in seqs if d >= cut]

    def pairs(ss, key):
        for s in ss:
            prev = ("<start>", "")
            for cur in s:
                yield key(prev), cur[0]
                prev = cur
            yield key(prev), "<end>"

    print(f"\n== B0: next act from the previous one; train < {cut}, test >= {cut}")
    for name, key in (("commonest act", lambda p: None),
                      ("previous act", lambda p: p[0]),
                      ("previous act + outcome", lambda p: p)):
        table = collections.defaultdict(collections.Counter)
        for k, nxt in pairs(train, key):
            table[k][nxt] += 1
        n = hit = cn = ch = 0
        for k, nxt in pairs(test, key):
            n += 1
            top, share = None, 0.0
            if k in table:
                top, c = table[k].most_common(1)[0]
                share = c / sum(table[k].values())
            hit += top == nxt
            if share >= 0.8:
                cn += 1
                ch += top == nxt
        print(f"  {name:24} top-1 {hit / n:.1%}; confident (>=0.8) on {cn / n:.1%} of "
              f"transitions, right there {ch / max(cn, 1):.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
