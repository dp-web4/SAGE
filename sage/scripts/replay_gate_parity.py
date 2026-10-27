#!/usr/bin/env python3
"""Gate-parity replay: judge a being's recent calls under two SAGE trees and diff the verdicts.

    replay_gate_parity.py <instance> <beats> <tree-a> <tree-b> [options]

Every distinct (effector, args) the being issued in its last <beats> heartbeats is judged
once under each tree, with the SAME law (--hestia-shared), the SAME grants and the same
live instance dir. Each tree is judged in its own subprocess, because the two trees import
different copies of sage.gateway.

Nothing executes: the client is built gate_only, so an allowed intent comes back `pending`.
`claim_scope` is stubbed so a deny files NO scope request in the being's name; the stub
answers "pending" and grants nothing, so every verdict is the gate's. If the mechanism
module is not loaded the replay refuses to run rather than replay with live claims.

Output: a rule-by-rule matrix, (decision, rule) under A x (decision, rule) under B, plus
the count of calls whose verdict changed. A verdict is the (decision, rule) pair; a deny
that changes rule is reported as changed. With --out, the per-call rows of both runs are
written as JSON (they hold the being's arguments: keep them local).

Origin: SAGE #441 / #547 (10-25 replay on Legion, 6,086 calls); written so another machine
can run the same instrument on its own being (cbp-claude, #547 thread).
"""
import argparse
import collections
import json
import os
import subprocess
import sys
from pathlib import Path

WANT = {"search", "check", "git_read", "run", "edit", "patch_apply", "git_restore", "git_clean",
        "camera", "game", "memory_read", "memory_write", "memory_edit", "identity_edit", "settle", "tune"}


def distinct_calls(heartbeats: Path, beats: int, only):
    seen, calls = set(), []
    for line in heartbeats.read_text().splitlines()[-beats:]:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        for ph in ("explore", "reflect"):
            for t in (d.get(ph) or {}).get("trace") or []:
                e = t.get("effector", "")
                if only is not None and e not in only:
                    continue
                if not (e in WANT or e.startswith("pr_")):
                    continue
                k = json.dumps([e, t.get("args")], sort_keys=True)
                if k not in seen:
                    seen.add(k)
                    calls.append(k)
    return calls


def judge(a):
    """Child mode: judge every call under the tree at a.tree; write rows to a.judge_out."""
    os.environ["HESTIA_GATE_SHARED"] = a.hestia_shared
    sys.path.insert(0, a.tree)
    from sage.gateway import governed_turn as gt
    from sage.gateway.being_gate_client import BeingIntent
    inst = Path(a.live) / "sage" / "instances" / a.instance
    model = a.model or json.loads((inst / "identity.json").read_text()).get("model", "replay")
    built = gt.build_client(a.member or a.instance, inst, model, a.live, None, "replay-gate-parity",
                            0.7, 256, gate_only=True)
    c = [x for x in built if hasattr(x, "gate")][0]
    if a.force_local_law:
        c._single_gate = None
    stubbed = []

    def _no_claim(*args, **kw):
        stubbed.append(args[0] if args else None)
        return ("pending", "replay: no request filed", None)

    m = sys.modules.get("hestia_gate_mechanism")
    assert m is not None, "mechanism not loaded: refusing to replay with live claims"
    m.claim_scope = _no_claim
    rows = []
    for k in json.loads(Path(a.calls).read_text()):
        e, args = json.loads(k)
        try:
            v = c.gate(BeingIntent(e, args or {}))
            rows.append([k, v.decision, v.rule, (v.reason or "")[:800], v.stage])
        except Exception as ex:  # a crash is a verdict too: report it, don't drop the call
            rows.append([k, "EXC", type(ex).__name__, str(ex)[:300], ""])
    Path(a.judge_out).write_text(json.dumps(rows))
    print(f"{a.tree}: gateway={gt.__file__} cwd={os.getcwd()} calls={len(rows)} path={getattr(c, 'gate_path', '?')}"
          f" core={sys.modules['hestia_gate_core'].__file__} claims_suppressed={len(stubbed)}",
          file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("instance", help="being instance name, e.g. legion-being")
    p.add_argument("beats", type=int, help="replay the last N heartbeats")
    p.add_argument("tree_a", help="SAGE tree A (e.g. the live carrier)")
    p.add_argument("tree_b", nargs="?", help="SAGE tree B (e.g. carrier + the PR)")
    p.add_argument("--live", default=os.path.expanduser("~/ai-workspace/SAGE"),
                   help="live SAGE checkout holding sage/instances/<instance>")
    p.add_argument("--hestia-shared",
                   default=os.path.expanduser("~/ai-workspace/hestia/plugins/_shared"))
    p.add_argument("--member", help="hestia member id when it differs from the instance dir name (cbp: cbp-being in cbp-qwen3.8-distill-4b). Wrong member = no grants = every call denied in both trees")
    p.add_argument("--model", help="model name for the client; gate_only never calls it, so a missing one only warns")
    p.add_argument("--only", help="comma-separated effectors to replay")
    p.add_argument("--force-local-law", action="store_true",
                   help="judge B with the single gate disabled (A is always as-is)")
    p.add_argument("--out", help="write per-call rows of both runs here (JSON)")
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--tree"), p.add_argument("--calls"), p.add_argument("--judge-out")
    a = p.parse_args()
    if a.judge_out:
        return judge(a)
    if not a.tree_b:
        p.error("tree_b is required")

    hb = Path(a.live) / "sage" / "instances" / a.instance / "heartbeats.jsonl"
    only = set(a.only.split(",")) if a.only else None
    calls = distinct_calls(hb, a.beats, only)
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="replay-parity-"))
    (tmp / "calls.json").write_text(json.dumps(calls))
    runs = {}
    for label, tree, force in (("A", a.tree_a, False), ("B", a.tree_b, a.force_local_law)):
        cmd = [a.python, os.path.abspath(__file__), a.instance, str(a.beats), a.tree_a,
               "--tree", os.path.abspath(tree), "--calls", str(tmp / "calls.json"),
               "--judge-out", str(tmp / f"{label}.json"), "--live", a.live,
               "--hestia-shared", a.hestia_shared]
        if a.model:
            cmd += ["--model", a.model]
        if a.member:
            cmd += ["--member", a.member]
        if force:
            cmd.append("--force-local-law")
        # cwd=--live, AS THE DAEMON RUNS (cbp-claude, #547, 2026-10-26): the gate reads its workspace
        # (.hestia-workspace marker walk) and the launch repo's dynamic grant from cwd. With cwd=tree
        # under /tmp both were wrong and 1308/1695 of cbp-being's calls, its own journal writes among
        # them, were denied mrh.path in BOTH trees: a parity of two wrong judges. Imports cannot cross
        # trees: sys.path[0] is this script's dir and the child inserts --tree ahead of it; the
        # child prints the sage.gateway it loaded so that is checkable on every run.
        subprocess.run(cmd, check=True, cwd=a.live)
        runs[label] = {r[0]: r for r in json.loads((tmp / f"{label}.json").read_text())}

    A, B = runs["A"], runs["B"]
    matrix = collections.Counter(((A[k][1], A[k][2]), (B[k][1], B[k][2])) for k in calls)
    changed = [k for k in calls if (A[k][1], A[k][2]) != (B[k][1], B[k][2])]
    print(f"instance={a.instance} beats={a.beats} distinct_calls={len(calls)}")
    print(f"A={a.tree_a}\nB={a.tree_b}{' (local-law)' if a.force_local_law else ''}")
    print("count  A(decision,rule) -> B(decision,rule)")
    for (va, vb), n in sorted(matrix.items(), key=lambda x: -x[1]):
        print(f"{n:6d}  {va[0]}:{va[1]} -> {vb[0]}:{vb[1]}{'' if va == vb else '   CHANGED'}")
    by_eff = collections.Counter((json.loads(k)[0], A[k][1], B[k][1]) for k in changed)
    print(f"changed={len(changed)}", dict(by_eff) if by_eff else "")
    if a.out:
        Path(a.out).write_text(json.dumps({"calls": calls, "A": A, "B": B}))


if __name__ == "__main__":
    sys.exit(main())
