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


def test_the_construction_site_gives_both_halves_the_same_tree():
    """`build_client` builds the gate and the dispatcher. Judged == executed requires that both
    get the SAME worktree, from one resolution -- pinned at source because constructing the real
    thing pulls in the model runtime, which no test should need."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "governed_turn.py")).read()
    body = src[src.index("def build_client("):src.index("\ndef ", src.index("def build_client(") + 10)]
    check("resolved once from instance.json",
          'worktree = instance_config(instance).get("worktree") or None' in body)
    check("handed to the dispatcher", "worktree=worktree)" in body)
    check("...and to the gate client", body.count("worktree=worktree") >= 2)
    # One variable, not two lookups: two would be one edit away from disagreeing.
    check("not looked up twice", body.count('get("worktree")'), 1)


def main():
    for fn in (test_every_registry_composer_takes_ctx, test_the_gate_composes_with_the_worktree,
               test_without_a_worktree_the_verbs_still_fail_closed,
               test_the_construction_site_gives_both_halves_the_same_tree):
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
