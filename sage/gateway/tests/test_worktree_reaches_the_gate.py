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
# Run as a plain script, conftest does not load -- so this file isolates itself the same way:
# never reach the seat's LIVE hestia daemon, which would mint `test-being` as a real member.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _isolate_hestia  # noqa: E402,F401  -- isolates on import, unconditionally
from sage.gateway import being_gate_client as B  # noqa: E402
from sage.gateway.tests._gate_core import requires_gate_core, standalone_skip_reason  # noqa: E402

FAILS = []
# UNDER PYTEST A FAILED CHECK MUST FAIL THE TEST (GPT, review of SAGE #257: check() only appended
# to FAILS, which only the __main__ runner reads -- so under pytest every test here returned
# normally, whatever it found). _fail() raises unless the standalone runner has set STANDALONE,
# which it does so it can report every failure in one pass instead of stopping at the first.
STANDALONE = False


def _fail(msg):
    FAILS.append(msg)
    if not STANDALONE:
        raise AssertionError(msg)


def check(name, got, want=True):
    if got != want:
        _fail(f"{name}: got {got!r}, want {want!r}")


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


@requires_gate_core
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
        # An ENUMERATION, and it grows only with a reason: #218 (the ARC game verb) added
        # `game_stepper`, which `game` composes the judged line from, and `member`, which a
        # composed git verb needs to name only the being's own branches (being_branch_prefix).
        # A key not listed here is a composer reaching past the law's view of the act.
        check("the ctx carries nothing unlisted -- a composer must not reach past the act",
              sorted(ctx), ["game_stepper", "member", "memory_root", "worktree"])
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


@requires_gate_core
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


# What each no-worktree refusal must say (2026-10-04). verb -> (words naming what it is FOR,
# the home-file tool it points to or None, that tool's parameters it must name).
# cbp-being asked dp three times to configure a worktree so `search` could find lines in its
# own scratch file. Search cannot read the home at all; memory_read with start_line could.
_REFUSAL_MUST_SAY = {
    "search":      ("code-repository checkout", "memory_read", ("path", "start_line")),
    "git_read":    ("git history", "memory_read", ("path", "start_line")),
    "check":       ("test suites", "request_run", ("path",)),
    # patch_apply has search's trap: changing a line of your own file is memory_edit's job.
    "patch_apply": ("applying a patch", "memory_edit", ("path", "start_line", "end_line", "new")),
    # git_restore: the home keeps no readable history, so memory_edit is the only honest pointer.
    "git_restore": ("git history", "memory_edit", ("path", "start_line", "end_line", "new")),
    # The PR verbs have no home counterpart: purpose plus "this seat has none".
    "pr_open":     ("opens a pull request", None, ()),
    "pr_amend":    ("revises a pull request", None, ()),
    "pr_sync":     ("up to date with its base branch", None, ()),
    "camera":      ("No other tool captures a frame", None, ()),
}
# Minimal args per verb. Every composer refuses on the missing worktree before it reads them.
_NO_WORKTREE_ARGS = {
    "search": {"pattern": "x"}, "git_read": {"op": "log"}, "check": {"target": "gateway"},
    "patch_apply": {"diff": "x", "why": "y"}, "git_restore": {"rev": "HEAD", "path": "a.py"},
    "pr_open": {"slug": "x-y", "title": "a title long enough", "body": "b"},
    "pr_amend": {"title": "a title long enough", "message": "why"}, "pr_sync": {},
    "camera": {},
}
_COMPOSERS = {"search": B.search_command, "git_read": B.git_read_command,
              "check": B.check_command, "patch_apply": B.patch_apply_command,
              "git_restore": B.git_restore_command, "pr_open": B.pr_open_command,
              "pr_amend": B.pr_amend_command, "pr_sync": B.pr_sync_command,
              "camera": B.camera_command}


def test_every_worktree_verb_has_a_refusal_and_a_check():
    """The table, the tests and the toolset's worktree verbs name the same set: a new worktree
    verb added without a refusal (and so with the old "configure one" shape) fails here."""
    from sage.gateway import toolset
    check("every toolset worktree verb has a refusal",
          sorted(set(toolset.WORKTREE_VERBS) - set(B.NO_WORKTREE_REFUSAL)), [])
    check("every refusal is pinned by _REFUSAL_MUST_SAY",
          sorted(B.NO_WORKTREE_REFUSAL), sorted(_REFUSAL_MUST_SAY))
# Wording that tells the being to get a worktree set up, or names the file someone would edit.
_CONFIGURE_WORDS = ("configur", "instance.json", "ask the operator", "ask dp", "request_scope",
                    "declare", "set up a worktree", "needs a worktree")
# Claims a no-worktree check never observed. The only fact in hand is "no checkout here": it says
# nothing about whether the home's files are tracked (the CBP being's home has 461 paths on main)
# or whether the being has an open PR. A refusal states what the verb cannot do, not these.
_UNOBSERVED_CLAIMS = ("not part of any repository", "not in any repository",
                      "no pull request of yours", "no proposal of yours", "you have no pull request")


def _assert_refusal_says_what_the_verb_is_for(verb, text):
    purpose, tool, params = _REFUSAL_MUST_SAY[verb]
    check(f"{verb}: names what it is for ({purpose!r})", purpose in text)
    check(f"{verb}: says this seat has none, or that it is not enabled",
          "this seat has none" in text or "not enabled" in text)
    if tool:
        check(f"{verb}: says what it works on is not the being's home",
              any(s in text for s in ("not your home", "not in your home", "not read your home",
                                      "not files in your home", "not reach your home",
                                      "not anything in your home")))
        check(f"{verb}: points to {tool}", tool in text)
        schema_params = B._TOOL_SCHEMAS[tool][1]
        for p in params:
            check(f"{verb}: names {tool}'s {p}", p in text)
            check(f"{verb}: {p} is a parameter {tool} really takes", p in schema_params)
        # EVERY line parameter the refusal names must be one the tool takes, listed or not. The
        # brief for this fix said "memory_read with start_line/end_line", but memory_read has no
        # end_line: it reads a window from start_line on. A parameter a refusal names is one the
        # being sends.
        for word in ("start_line", "end_line", "delete_lines"):
            if word in text:
                check(f"{verb}: {word} is a parameter {tool} really takes", word in schema_params)
    else:
        for other in ("memory_read", "memory_edit", "request_run"):
            check(f"{verb}: points to no home tool it was not given ({other})", other not in text)
    low = text.lower()
    for w in _CONFIGURE_WORDS:
        check(f"{verb}: contains no instruction to configure a worktree ({w!r})", w not in low)
    for w in _UNOBSERVED_CLAIMS:
        check(f"{verb}: asserts nothing the check did not observe ({w!r})", w not in low)


@requires_gate_core
def test_no_worktree_refusals_say_what_the_verb_is_for():
    """The deny the GATE returns, verb by verb: still a deny (the fail-closed test above), but now
    one that says what the verb is for, where the being's own files are served instead, and
    nothing that reads as "get someone to configure a worktree"."""
    c = _client(None)
    for eff in sorted(B.NO_WORKTREE_REFUSAL):
        v = c.gate(B.BeingIntent(effector=eff, args=dict(_NO_WORKTREE_ARGS[eff])))
        check(f"{eff}: denied", v.decision, "deny")
        reason = v.reason or ""
        check(f"{eff}: the deny carries the whole refusal", B.NO_WORKTREE_REFUSAL[eff] in reason)
        _assert_refusal_says_what_the_verb_is_for(eff, B.NO_WORKTREE_REFUSAL[eff])


_FIND_WORDS = ("find", "search", "grep", "locate", "look up", "look for")
# The home tools that address a file by path and line and search nothing. request_run is not here:
# check's refusal says "To find out what one of your own files does when it runs, use
# request_run", and running a file is how one finds that out.
_HOME_TOOLS = ("memory_read", "memory_edit")


def test_no_home_tool_is_credited_with_finding():
    """No refusal, and no toolset availability line, credits a home tool with FINDING anything.
    #354's search refusal said "To find or read lines in your own files ... use memory_read", but
    memory_read reads a window from start_line on and searches nothing (Codex, #354 follow-up). A
    being told it can find with memory_read goes looking with a tool that cannot look.

    Checked per CLAUSE (split on '.' and ';'), so "search reads a code-repository checkout" in the
    search refusal's first sentence is not mistaken for a claim about memory_read in its second."""
    import re
    from sage.gateway import toolset
    texts = [(f"refusal {k}", v) for k, v in B.NO_WORKTREE_REFUSAL.items()]
    texts += [(f"toolset {k}", v) for k, v in toolset.NO_WORKTREE_HERE.items()]
    for label, text in texts:
        for clause in re.split(r"[.;]\s", text):
            low = clause.lower()
            tools = [t for t in _HOME_TOOLS if t in low]
            if not tools:
                continue
            for w in _FIND_WORDS:
                check(f"{label}: {w!r} is not credited to {tools} ({clause!r})", w not in low)


def test_the_composers_and_the_dispatcher_say_the_same_refusal():
    """Without the gate core: each composer raises the refusal text, and the dispatcher's own
    no-worktree branch (its second line of defence) says the same words, so the being hears one
    answer however the act reaches it."""
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    for verb in sorted(B.NO_WORKTREE_REFUSAL):
        try:
            _COMPOSERS[verb](dict(_NO_WORKTREE_ARGS[verb]), {"worktree": None, "memory_root": "/tmp/x"})
            _fail(f"{verb}: composed with no worktree")
        except ValueError as e:
            check(f"{verb}: the composer raises the shared refusal", str(e), B.NO_WORKTREE_REFUSAL[verb])
        _assert_refusal_says_what_the_verb_is_for(verb, B.NO_WORKTREE_REFUSAL[verb])
    with tempfile.TemporaryDirectory() as home:
        d = D.__new__(D)
        d.worktree = os.path.join(home, "does-not-exist")
        d.memory_root = home
        # camera has no dispatcher-side worktree branch: its composer is the only refusal.
        for verb in sorted(set(B.NO_WORKTREE_REFUSAL) - {"camera"}):
            args = dict(_NO_WORKTREE_ARGS[verb])
            env = getattr(d, f"_do_{verb}")(B.BeingIntent(effector=verb, args=args))
            check(f"{verb}: dispatcher still refuses (pending, not run)", (env.ok, env.pending), (False, True))
            check(f"{verb}: dispatcher says the shared refusal", env.note, B.NO_WORKTREE_REFUSAL[verb])


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
    # The PROPERTY, not the spelling: the first cut pinned `worktree=worktree)` and went red when
    # #218 appended an argument after it, with the dispatcher still receiving the worktree.
    disp = body[body.index("HestiaF1aDispatcher("):body.index("client = BeingGateClient(")]
    check("build_client: handed to the dispatcher", "worktree=worktree" in disp)
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
               test_every_worktree_verb_has_a_refusal_and_a_check,
               test_no_worktree_refusals_say_what_the_verb_is_for,
               test_the_composers_and_the_dispatcher_say_the_same_refusal,
               test_the_construction_sites_give_both_halves_the_same_tree,
               test_no_other_call_site_builds_a_gate_without_a_worktree):
        why = standalone_skip_reason(fn)
        if why:
            print(f"SKIPPED {fn.__name__}: {why}")
            continue
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            _fail(f"{fn.__name__} raised {type(e).__name__}: {e}")
    for f in FAILS:
        print("FAIL", f)
    print(f"{'FAILED' if FAILS else 'ok'}: {len(FAILS)} failure(s)")
    return 1 if FAILS else 0


if __name__ == "__main__":
    STANDALONE = True
    sys.exit(main())
