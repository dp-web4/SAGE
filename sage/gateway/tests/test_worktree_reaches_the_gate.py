"""The being's worktree must reach the GATE, not only the dispatcher.

WHY THIS FILE EXISTS (McNugget, 2026-09-24, measured). `git_read`, `search` and `check` landed
on 2026-09-13 as composed verbs: the being names an op, the SEAT builds the exact command, and
the law judges that string. Each composer reads the worktree out of a `ctx` dict.

The dispatcher passed one (`check_command(intent.args, {"worktree": self.worktree})`). The gate
did not -- `_normalize` called `compose(intent.args)`, one argument -- and `BeingGateClient` had
no worktree at all. So all three composers raised inside the gate and every intent came back:

    deny / gate.raised -- "needs a worktree of your own; none is configured on this seat"

Measured on McNugget before the fix: check, search and git_read denied; witness allowed. Worse,
`HestiaF1aDispatcher(worktree=...)` was never passed by ANY caller in the tree, and no being's
`instance.json` declared a worktree, so the three organs were unreachable by construction from
the day they were written. The deny was correct. Nobody read it.

The guard that would have caught it on 2026-09-13 is `test_every_registry_composer_takes_ctx`:
one composer (`pr_review_command`) had a one-argument signature, which is why the call site was
written that way in the first place.

Run: python3 sage/gateway/tests/test_worktree_reaches_the_gate.py   (or pytest)
"""
import inspect
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import being_gate_client as B  # noqa: E402

FAILS = []


def check(name, got, want=True):
    if got != want:
        FAILS.append(f"{name}: got {got!r}, want {want!r}")


def _client(worktree):
    """A client with the law imported but nothing injected: enough to compose and gate."""
    inst = os.path.join(os.path.dirname(__file__), "..", "..", "instances", "mcnugget-gemma3-12b")
    return B.BeingGateClient("test-being", os.path.join(inst, "identity.json"),
                             os.path.abspath("."), worktree=worktree)


def test_every_registry_composer_takes_ctx():
    """THE GUARD. Every composed verb must accept (args, ctx), or the one call site in
    `_normalize` cannot pass a worktree uniformly -- which is exactly how three verbs became
    unreachable. A new composer with a one-argument signature fails here."""
    for eff, spec in sorted(B._REGISTRY.items()):
        compose = spec.get("compose")
        if compose is None:
            continue
        params = list(inspect.signature(compose).parameters)
        check(f"{eff}: composer takes (args, ctx)", params[:2], ["args", "ctx"])
        # ...and ctx must be OPTIONAL, so the dispatcher's own two-arg calls and any
        # single-arg caller both remain valid.
        check(f"{eff}: ctx has a default",
              inspect.signature(compose).parameters["ctx"].default is None)


def test_the_gate_composes_with_the_worktree():
    """With a worktree, the worktree verbs reach the law instead of raising in the composer."""
    with tempfile.TemporaryDirectory() as wt:
        subprocess.run(["git", "-C", wt, "init", "-q"], check=True)
        c = _client(wt)
        check("the client keeps a resolved worktree", c.worktree == os.path.realpath(wt))
        ctx = c._compose_ctx()
        check("the ctx carries the worktree", ctx.get("worktree"), c.worktree)
        check("...and the memory root, the other fact a composer may know",
              ctx.get("memory_root"), c.memory_root)
        check("the ctx carries nothing else -- a composer must not reach past the act",
              sorted(ctx), ["memory_root", "worktree"])
        for eff, args in (("search", {"pattern": "def compose("}), ("git_read", {"op": "log"})):
            ev = c._normalize(B.BeingIntent(effector=eff, args=args))
            check(f"{eff}: the gate composed a command at all", bool(ev.command))
            check(f"{eff}: and it names the worktree the dispatcher will use",
                  c.worktree in (ev.command or ""))
        # camera reaches the law once a worktree exists -- the fourth verb this unlocked. It
        # aims at memory_root BY DESIGN (an uncommitted frame in the worktree would dirty the
        # tree check reports as evidence), so it is the one ctx verb whose command must NOT
        # name the worktree. Asserted, not assumed: it is why camera is absent from the loop
        # above and present in the fail-closed one below.
        ev = c._normalize(B.BeingIntent(effector="camera", args={}))
        check("camera: the gate composed a command at all", bool(ev.command))
        check("camera: aimed at the being's home", c.memory_root in (ev.command or ""))
        check("camera: and not at the worktree it nonetheless requires",
              c.worktree not in (ev.command or ""))


def test_without_a_worktree_the_verbs_still_fail_closed():
    """The refusal is CORRECT and must survive. A seat with no worktree declared gets a deny
    that names what is missing -- not a command composed against the shared checkout, which is
    the tree the being does not hold.

    CAMERA IS IN THIS LIST AND NOT IN THE COMPOSE TEST ABOVE, which is the whole of CBP's
    second note on #208. It is a composed verb whose composer requires a worktree, so it was
    unreachable at the gate for the same reason as the other three and this PR makes it
    reachable too -- but it uses memory_root, not the worktree, so it composes a command that
    never names the tree. Pinning the deny here is what keeps that requirement from being
    removed as "unused": it is the only thing holding a camera to the same condition as a
    git log.
    """
    c = _client(None)
    check("no worktree, no claim", c.worktree, None)
    for eff, args in (("search", {"pattern": "x"}), ("git_read", {"op": "log"}),
                      ("check", {"target": "gateway"}), ("camera", {})):
        v = c.gate(B.BeingIntent(effector=eff, args=args))
        check(f"{eff}: denied", v.decision, "deny")
        check(f"{eff}: and says a worktree is what is missing",
              "worktree" in (v.reason or "").lower())


def _call_args(src, needle, start=0):
    """The argument text of the first `needle(` call at or after `start`, paren-matched."""
    i = src.index(needle, start)
    j = src.index("(", i)
    depth, k = 0, j
    while k < len(src):
        if src[k] == "(":
            depth += 1
        elif src[k] == ")":
            depth -= 1
            if depth == 0:
                return src[j + 1:k], i
        k += 1
    raise AssertionError(f"unbalanced parens after {needle}")


def test_the_construction_sites_give_both_halves_the_same_tree():
    """Both real construction sites build a gate AND a dispatcher. Judged == executed requires
    that both get the SAME worktree, from ONE resolution -- pinned at source because
    constructing the real thing pulls in the model runtime, which no test should need.

    TWO SITES, NOT ONE. #208 fixed `build_client` and stopped there; the being on sprout is
    launched by `autonomous-sprout-sage.service`, which runs the raising session's own tool
    turn and never touches `build_client`. A seat that declared `worktree` in instance.json
    still heard "none is configured on this seat" -- a refusal naming a cause the seat had
    already fixed. That is sprout's blocking item on #208, and this is what keeps it fixed.
    """
    here = os.path.dirname(__file__)
    gt = open(os.path.join(here, "..", "governed_turn.py")).read()
    body = gt[gt.index("def build_client("):gt.index("\ndef ", gt.index("def build_client(") + 10)]
    check("build_client: resolved through the one resolver",
          "worktree = worktree_for(instance)" in body)
    check("build_client: handed to the dispatcher", "worktree=worktree)" in body)
    check("build_client: ...and to the gate client", body.count("worktree=worktree") >= 2)
    # One variable, not two lookups: two would be one edit away from disagreeing.
    check("build_client: not looked up twice", body.count("worktree_for("), 1)
    check("the resolver reads instance.json and nothing else",
          'return instance_config(instance).get("worktree") or None' in gt)

    rs = open(os.path.join(here, "..", "..", "raising", "scripts",
                           "ollama_raising_session.py")).read()
    offer = rs[rs.index("def _maybe_offer_tools("):rs.index("\n    def ", rs.index("def _maybe_offer_tools(") + 10)]
    check("raising: resolved through the SAME resolver, not a second instance.json read",
          "from sage.gateway.governed_turn import worktree_for" in offer
          and "worktree = worktree_for(self.instance.root)" in offer)
    check("raising: not looked up twice", offer.count("worktree_for("), 1)
    check("raising: handed to the real dispatcher", "worktree=worktree)" in offer)
    check("raising: ...and to the gate client", "worktree=worktree," in offer)


# Every OTHER construction of a gate in the tree must either hand it a worktree or be named
# here with the reason it cannot need one. This is the half of sprout's note that #208's
# single-site guard could not carry: a new call site is how the verbs went unreachable the
# first time, and a guard pinned to one function does not see the next one.
GATE_WITHOUT_A_WORKTREE = {
    "sage/gateway/conformance.py":
        "proposes witness/memory_write/mesh/shell only -- no composed worktree verb",
    "sage/gateway/escalate.py":
        "dispatches one `mesh` notice to wake a seat; gates no composed verb",
    "sage/gateway/being_gate_client.py":
        "the module's own __main__ demo (peer_ask/witness/memory_write/escapes)",
}


def test_no_other_call_site_builds_a_gate_without_a_worktree():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    for dirpath, dirnames, filenames in os.walk(os.path.join(root, "sage")):
        dirnames[:] = [d for d in dirnames if d != "tests" and not d.startswith(".")]
        for fn in filenames:
            if not fn.endswith(".py") or fn.startswith("test_"):
                continue
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            src = open(path, encoding="utf-8", errors="replace").read()
            pos = 0
            while "BeingGateClient(" in src[pos:]:
                args, at = _call_args(src, "BeingGateClient(", pos)
                pos = at + 1
                if "worktree" in args:
                    continue
                check(f"{rel}: gate built with no worktree -- wire it, or name it in "
                      f"GATE_WITHOUT_A_WORKTREE with the reason",
                      rel in GATE_WITHOUT_A_WORKTREE)


def main():
    for fn in (test_every_registry_composer_takes_ctx, test_the_gate_composes_with_the_worktree,
               test_without_a_worktree_the_verbs_still_fail_closed,
               test_the_construction_sites_give_both_halves_the_same_tree,
               test_no_other_call_site_builds_a_gate_without_a_worktree):
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            FAILS.append(f"{fn.__name__} raised {type(e).__name__}: {e}")
    for f in FAILS:
        print("FAIL", f)
    print(f"{'FAILED' if FAILS else 'ok'}: {len(FAILS)} failure(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
