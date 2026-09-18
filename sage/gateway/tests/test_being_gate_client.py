"""Hermetic tests for the society-safety fail-closed boundary of BeingGateClient.

No live hestia gate required: we bypass __init__ and inject fake _core/_mech, so
this exercises the Stage-2 policy in isolation. Runnable under pytest or directly
(`python3 test_being_gate_client.py`).
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingGateClient, BeingIntent  # noqa: E402


def _client(mech):
    """A client whose local law always ALLOWs, with an injected society mechanism."""
    c = BeingGateClient.__new__(BeingGateClient)
    c.member_id = "test-being"
    c.workspace = "/tmp/ws"
    c.memory_root = "/tmp/ws"
    c._import_error = ""
    c.host_session_id = None
    c._profile = object()
    c._mech = mech
    c._core = SimpleNamespace(
        NormalizedEvent=lambda **kw: SimpleNamespace(raw=kw.get("raw", {}), tool=kw.get("tool")),
        evaluate=lambda ev, prof, ws, policy=None: SimpleNamespace(
            decision="allow", rule="", reason="ok", innate=False),
    )
    return c


PEER = BeingIntent("peer_ask", {"to": "legion", "body": "hi"})       # consequential
WRITE = BeingIntent("memory_write", {"path": "/tmp/ws/n.md", "content": "x"})  # consequential
READ = BeingIntent("memory_read", {"path": "/tmp/ws/n.md"})          # observational
WIT = BeingIntent("witness", {"event": "x"})                          # observational

# The mechanism's real signature: query_society_safety(event, *, plugin_id, host_agent, ...)
# -> SafetyVerdict(allow, decided, message, ...). `allow` is the only field acted on.
def _mech(fn):
    return SimpleNamespace(query_society_safety=lambda event, **kw: fn(event, kw))

_raises = _mech(lambda e, kw: (_ for _ in ()).throw(TimeoutError("down")))
_denies = _mech(lambda e, kw: SimpleNamespace(allow=False, decided=True, message="nope"))
_noverd = _mech(lambda e, kw: SimpleNamespace(allow=False, decided=False, message="no verdict"))
_allows = _mech(lambda e, kw: SimpleNamespace(allow=True, decided=True, message="ok"))


def test_mech_absent_consequential_denies():
    v = _client(None).gate(PEER)
    assert v.blocks and v.rule == "society.unavailable", v


def test_mech_absent_observational_softpasses():
    v = _client(None).gate(READ)
    assert v.decision == "allow", v


def test_mech_raises_consequential_denies():
    v = _client(_raises).gate(WRITE)
    assert v.blocks and v.rule == "society.unreachable", v


def test_mech_raises_observational_softpasses():
    v = _client(_raises).gate(WIT)
    assert v.decision == "allow", v


def test_mech_denies_blocks():
    v = _client(_denies).gate(PEER)
    assert v.blocks and v.rule == "society.unsafe", v


def test_mech_allows_consequential_allows():
    v = _client(_allows).gate(PEER)
    assert v.decision == "allow", v


def test_mech_no_verdict_fails_closed_distinctly():
    v = _client(_noverd).gate(PEER)
    assert v.blocks and v.rule == "society.no_verdict", v


def test_mech_is_called_with_real_contract():
    seen = {}
    m = _mech(lambda e, kw: seen.update(event=e, **kw) or SimpleNamespace(allow=True, decided=True, message="ok"))
    c = _client(m)
    c.host_session_id = "run-1"
    c.gate(PEER)
    assert seen["event"]["tool_name"] == "peer_ask" and seen["event"]["tool_input"]["to"] == "legion"
    assert seen["plugin_id"] == "test-being" and seen["host_agent"] == "sage-gateway"
    assert seen["host_session_id"] == "run-1"


def test_unregistered_effector_denies_before_gate():
    v = _client(_allows).gate(BeingIntent("shell", {"command": "rm -rf /"}))
    assert v.blocks and v.rule == "registry.unbounded" and v.stage == "registry", v


def test_no_core_fails_closed():
    c = _client(_allows)
    c._core = None
    v = c.gate(PEER)
    assert v.blocks and v.rule == "gate.unreachable" and v.innate, v




def test_relative_memory_path_is_judged_at_the_being_memory_root():
    """The gate must judge the SAME path the dispatcher will touch: a relative memory
    path is rooted at the being's memory root (its instance dir), not the cwd or the
    workspace. Captures the NormalizedEvent the law is handed."""
    seen = {}
    c = _client(_allows)
    c.memory_root = "/tmp/being-home"
    c._core = SimpleNamespace(
        NormalizedEvent=lambda **kw: seen.update(kw) or SimpleNamespace(raw=kw.get("raw", {}), tool=kw.get("tool")),
        evaluate=lambda ev, prof, ws, policy=None: SimpleNamespace(
            decision="allow", rule="", reason="ok", innate=False),
    )
    c.gate(BeingIntent("memory_write", {"path": "notes/x.md", "content": "x"}))
    assert seen["paths"] == ["/tmp/being-home/notes/x.md"], seen["paths"]
    c.gate(BeingIntent("memory_read", {"path": "/tmp/being-home/notes/x.md"}))
    assert seen["paths"] == ["/tmp/being-home/notes/x.md"]


def test_pr_review_is_judged_as_the_gh_command_the_seat_runs():
    """pr_review reaches the law as the exact outward shell command, never as a verb
    name; the body travels by --body-file so no review text reaches the shell."""
    from sage.gateway.being_gate_client import pr_review_command
    seen = {}
    c = _client(_allows)
    c._core = SimpleNamespace(
        NormalizedEvent=lambda **kw: seen.update(kw) or SimpleNamespace(raw=kw.get("raw", {}), tool=kw.get("tool")),
        evaluate=lambda ev, prof, ws, policy=None: SimpleNamespace(
            decision="allow", rule="", reason="ok", innate=False),
    )
    c.gate(BeingIntent("pr_review", {"repo": "dp-web4/SAGE", "number": "24", "body": "looks fine; `rm -rf /`"}))
    assert seen["command"] == "gh pr review 24 --repo dp-web4/SAGE --comment --body-file -"
    assert seen["tool"] == "pr_review"
    # malformed args never reach the law: the gate turns the ValueError into a deny
    v = c.gate(BeingIntent("pr_review", {"repo": "dp-web4/SAGE; rm -rf /", "number": "24", "body": "x"}))
    assert v.decision == "deny" and v.rule == "gate.raised", v
    v = c.gate(BeingIntent("pr_review", {"repo": "dp-web4/SAGE", "number": "24 --approve", "body": "x"}))
    assert v.decision == "deny" and v.rule == "gate.raised", v
    for bad in ({"repo": "SAGE", "number": "24", "body": "x"},
                {"repo": "octocat/SAGE", "number": "24", "body": "x"},   # not a fleet repo
                {"repo": "dp-web4/SAGE", "number": "24", "body": " "}):
        try:
            pr_review_command(bad); assert False, bad
        except ValueError:
            pass


def test_pr_review_signature_is_fixed_and_advisory():
    from sage.gateway.being_gate_client import pr_review_signature
    s = pr_review_signature("legion-being", "act-1", "lct:web4:mb32:bt7a")
    assert "Advisory and non-binding" in s and "legion-being" in s
    assert "`lct:web4:mb32:bt7a`" in s and "`act-1`" in s


def test_tools_filter_never_widens_the_registry():
    from sage.gateway.being_gate_client import ollama_tools
    names = [t["function"]["name"] for t in ollama_tools(["pr_review", "witness", "shell"])]
    assert names == ["witness", "pr_review"], names




# ---- single gate (hestia #934) shim contract ---------------------------------------------
def _sg_client(decision="allow", rule="", available=True, raise_=False):
    """Client with a fake hestia_single_gate injected: decide() must be THE law path."""
    calls = []
    class GateProfile:
        def __init__(self, **kw): self.kw = kw
    class GateEvent:
        def __init__(self, **kw): self.kw = kw
    class D:
        def __init__(self): self.decision, self.rule, self.reason = decision, rule, "single-gate said so"; self.verdict_available = available
    def decide(ev, prof):
        calls.append((ev.kw, prof.kw))
        if raise_: raise RuntimeError("boom")
        return D()
    c = _client(_allows)
    c._single_gate = SimpleNamespace(GateProfile=GateProfile, GateEvent=GateEvent, decide=decide)
    c._identity_path = "/tmp/id.json"
    c._host_agent = "test-harness"
    return c, calls


def test_single_gate_decides_and_client_does_not_resequence():
    c, calls = _sg_client("allow")
    v = c.gate(PEER)
    assert v.decision == "allow" and v.stage == "single-gate", v
    assert len(calls) == 1
    ev, prof = calls[0]
    assert ev["tool"] == "peer_ask" and ev["tool_input"] == PEER.args and ev["raw"]["effector"] == "peer_ask"
    assert prof["member_id"] == "test-being" and prof["host_agent"] == "test-harness"


def test_single_gate_deny_and_no_verdict_map_fail_closed():
    assert _sg_client("deny", "mrh.path")[0].gate(WRITE).rule == "mrh.path"
    v = _sg_client("allow", available=False)[0].gate(WRITE)
    assert v.blocks and v.rule == "gate.no_verdict"
    v = _sg_client(raise_=True)[0].gate(WRITE)
    assert v.blocks and v.rule == "gate.raised" and v.innate


def test_registry_refusal_precedes_the_single_gate():
    c, calls = _sg_client("allow")
    v = c.gate(BeingIntent("shell", {"command": "rm -rf /"}))
    assert v.rule == "registry.unbounded" and not calls  # harness syntax, never reaches the law

def test_no_registry_entry_carries_a_cmd_arg():
    """The being never fills a command. A composed verb builds its own (pr_review); every
    other verb reaches the law with command=None. A registry entry with a cmd_arg would
    let the being's args become the judged shell line."""
    from sage.gateway.being_gate_client import _REGISTRY, _OBSERVATIONAL, _CONSEQUENTIAL
    assert all(spec["cmd_arg"] is None for spec in _REGISTRY.values()), _REGISTRY
    assert set(_REGISTRY) == _OBSERVATIONAL | _CONSEQUENTIAL   # every verb is classed
    assert not (_OBSERVATIONAL & _CONSEQUENTIAL)


def test_request_scope_path_is_not_judged_under_mrh_path():
    """request_scope names a path OUTSIDE the grant by definition. If the registry judged
    it as a path arg, stage 1 (mrh.path) would deny every request before it reached the
    daemon and the sanctioned answer to a deny could never be asked. So the law is handed
    paths=() — and the same holds for remember, whose reach is the seat-fixed cartridge."""
    seen = {}
    c = _client(_allows)
    c._core = SimpleNamespace(
        NormalizedEvent=lambda **kw: seen.update(kw) or SimpleNamespace(raw=kw.get("raw", {}), tool=kw.get("tool")),
        evaluate=lambda ev, prof, ws, policy=None: SimpleNamespace(
            decision="allow", rule="", reason="ok", innate=False),
    )
    v = c.gate(BeingIntent("request_scope", {"path": "/etc/somewhere/ungranted", "reason": "why"}))
    assert not v.blocks, v
    assert seen["paths"] == [] and seen["command"] is None and seen["tool"] == "request_scope", seen
    v = c.gate(BeingIntent("remember", {"content": "x", "path": "/etc/anything"}))
    assert not v.blocks and seen["paths"] == [] and seen["tool"] == "remember", seen


def test_request_scope_schema_offers_no_mode():
    """Measured against hestia a5e18af: the daemon reads plugin_id/role/path/reason and a
    grant is reach on the path, read and write. A `mode` would be a choice the law cannot
    honour, so the being is not offered one."""
    from sage.gateway.being_gate_client import ollama_tools
    (spec,) = ollama_tools(["request_scope"])
    params = spec["function"]["parameters"]
    assert set(params["properties"]) == {"path", "reason"}, params
    assert params["required"] == ["path", "reason"]
    assert "read and write" in spec["function"]["description"]

def test_registry_offers_appeal_as_an_observational_effector():
    from sage.gateway.being_gate_client import _REGISTRY, _OBSERVATIONAL, ollama_tools
    assert _REGISTRY["appeal"]["tool"] == "appeal" and "appeal" in _OBSERVATIONAL
    spec = ollama_tools(["appeal"])[0]["function"]
    assert set(spec["parameters"]["required"]) == {"deny_hash", "reason"}


def test_a_refusal_is_witnessed_and_names_its_appeal_handle():
    """dispatch(): a deny is handed to the dispatcher's witness_deny; the hash rides the
    envelope and the refusal text, so the being can appeal. No dispatcher method: the
    refusal says it could not be witnessed."""
    from sage.gateway.being_gate_client import BeingGateClient, GatewayVerdict, BeingIntent

    class Disp:
        def __init__(self): self.seen = []
        def witness_deny(self, intent, verdict): self.seen.append((intent.effector, verdict.rule)); return "dh-77"
        def __call__(self, intent, verdict): raise AssertionError("a refused intent must never be dispatched")

    c = BeingGateClient.__new__(BeingGateClient)
    c._dispatcher = Disp()
    c.gate = lambda intent: GatewayVerdict("deny", "mrh.path", "outside your grant", stage="local-law")
    env = c.dispatch(BeingIntent("memory_write", {"path": "/etc/x", "content": "c"}))
    assert env.refused and env.witness_id == "dh-77" and env.verdict.witness_id == "dh-77"
    assert "deny_hash=dh-77" in env.error and "deny_hash=dh-77" in env.to_tool_message()
    assert c._dispatcher.seen == [("memory_write", "mrh.path")]
    c._dispatcher = None
    env = c.dispatch(BeingIntent("memory_write", {"path": "/etc/x", "content": "c"}))
    assert env.refused and env.witness_id is None and "cannot be appealed yet" in env.error


def test_granted_roots_come_from_the_policy_scope():
    from sage.gateway.being_gate_client import _granted_roots, GatewayVerdict
    class Pol: scope = ("path:/tmp/being-home", "repo:sage", "path:~/nope-not-real")
    class Core:
        @staticmethod
        def _scope_parts(scopes, ws): return ((), tuple(s[5:] for s in scopes if s.startswith("path:")))
    assert _granted_roots(Core, Pol, "/ws") == ("/tmp/being-home", "~/nope-not-real")
    assert _granted_roots(object(), Pol, "/ws")[0].endswith("/tmp/being-home")   # fallback parser
    assert _granted_roots(Core, None, "/ws") == () and GatewayVerdict("allow").granted == ()


def test_a_refused_home_file_names_the_right_path_in_the_refusal_itself():
    import os, tempfile
    from sage.gateway.being_gate_client import BeingGateClient, GatewayVerdict, BeingIntent

    root = tempfile.mkdtemp(prefix="home-")

    class Disp:
        class _L:
            memory_root = root
        _local = _L()
        def witness_deny(self, intent, verdict):
            return "dh-1"
        def __call__(self, intent, verdict):
            raise AssertionError("a refused intent is never dispatched")

    c = BeingGateClient.__new__(BeingGateClient)
    c._dispatcher = Disp()
    c.gate = lambda i: GatewayVerdict("deny", "mrh.path", "outside your granted scope", stage="local-law")
    env = c.dispatch(BeingIntent("memory_write", {"path": "/home/user/journal.md", "content": "x"}))
    assert "no grant is needed" in env.error and os.path.join(os.path.realpath(root), "journal.md") in env.error
    # a real ask keeps its plain refusal, and the home file itself is never hinted at
    e2 = c.dispatch(BeingIntent("memory_read", {"path": "/srv/peer/notes.txt"}))
    assert "no grant is needed" not in e2.error
    e3 = c.dispatch(BeingIntent("memory_write", {"path": os.path.join(root, "journal.md"), "content": "x"}))
    assert "no grant is needed" not in e3.error


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


def test_granted_reach_reads_the_cores_reach_resolver_and_an_older_core_is_recursive():
    from sage.gateway.being_gate_client import _granted_reach, GatewayVerdict
    class Pol:
        scope = ("path:/tmp/being-home", "path:/tmp/shared/**", "repo:x")
    class Core:
        @staticmethod
        def _scope_roots_with_reach(scopes, ws):
            return (("/tmp/being-home", False), ("/tmp/shared", True))
        @staticmethod
        def _scope_parts(scopes, ws):
            return ((), ("/tmp/being-home", "/tmp/shared"))
    assert _granted_reach(Core, Pol, "/ws") == (("/tmp/being-home", False), ("/tmp/shared", True))
    # a core without the resolver matches every grant as a prefix: that reach is reported, not exact
    older = _granted_reach(object(), Pol, "/ws")
    assert older and all(rec for _, rec in older)
    assert _granted_reach(Core, None, "/ws") == () and GatewayVerdict("allow").granted_reach == ()


def test_search_quotes_its_pattern_so_judged_equals_executed():
    """The judged string must shlex.split into exactly the argv that runs (GPT on #56, #6).

    The earlier verbs bought that invariant by REJECTING whitespace, which would make a
    search verb useless — a being looking for `def compose(` needs spaces. shlex.quote
    round-trips instead, so the pattern is one argv element on both sides."""
    import shlex
    from sage.gateway.being_gate_client import search_command

    ctx = {"worktree": "/wt"}
    cmd = search_command({"pattern": "seed, posture_turn = compose"}, ctx)
    argv = shlex.split(cmd)
    assert argv[argv.index("-e") + 1] == "seed, posture_turn = compose"
    assert argv[-1] == "/wt"          # absolute pathspec: hestia matches absolute prefixes

    # a path narrows it, and is absolute-ised for the same reason
    cmd2 = search_command({"pattern": "x", "path": "sage/gateway"}, ctx)
    assert shlex.split(cmd2)[-1] == "/wt/sage/gateway"




def test_search_refuses_what_its_grammar_cannot_represent():
    """A refusal that names its own valid set is one the being can correct without asking."""
    from sage.gateway.being_gate_client import search_command, SEARCH_MAX_N
    ctx = {"worktree": "/wt"}

    for bad, expect in [
        ({}, "pattern"),
        ({"pattern": "   "}, "pattern"),
        ({"pattern": "a\nb"}, "single line"),
        ({"pattern": "x" * 201}, "under 200"),
        ({"pattern": "x", "path": "../escape"}, "plain path"),
        # absolute and off the tree: refused for REACH now, not for escaping the worktree
        # (search_command grew a workspace-wide reach; see the reach test below)
        ({"pattern": "x", "path": "/etc/passwd"}, "outside anything you can reach"),
        ({"pattern": "x", "path": "/etc/../etc/passwd"}, "plain path"),
        ({"pattern": "x", "path": "has space"}, "whitespace"),
        ({"pattern": "x", "path": "-rf"}, "plain path"),
    ]:
        try:
            search_command(bad, ctx)
            assert False, f"should have refused {bad!r}"
        except ValueError as e:
            assert expect in str(e), f"{bad!r} -> {e}"

    # n is clamped, never trusted
    assert f"--max-count={SEARCH_MAX_N}" in search_command({"pattern": "x", "n": 10_000}, ctx)
    assert "--max-count=1" in search_command({"pattern": "x", "n": -5}, ctx)

    # no worktree is a missing affordance, named
    try:
        search_command({"pattern": "x"}, {})
        assert False, "should have refused without a worktree"
    except ValueError as e:
        assert "worktree" in str(e)


def test_git_read_refuses_what_its_grammar_cannot_represent():
    """The being names an op, a revision and a path; it never supplies a flag. Anything the
    grammar cannot represent raises, and the refusal names its own valid set — a refusal the
    being can correct without asking (measured 2026-09-07: it did exactly that on `check`,
    in one beat, and declined to appeal a grammar error it agreed with)."""
    from sage.gateway.being_gate_client import git_read_command, GIT_OPS

    ctx = {"worktree": "/wt"}
    for bad, expect in [
        ({"op": "push"}, "must be one of"),
        ({"op": ""}, "must be one of"),
        ({"op": "log", "rev": "; rm -rf /"}, "sha"),
        ({"op": "show", "path": "../../etc/passwd"}, "plain path"),
        # /etc is not an escape from the worktree any more — it is OUTSIDE the machine's
        # shared tree, which is a different refusal with a different remedy (the reach
        # widened to the granted tree on this branch; the refusal names what is reachable).
        ({"op": "show", "path": "/etc/passwd"}, "outside anything you can reach"),
        ({"op": "show", "path": "has space"}, "whitespace"),
        ({"op": "show", "path": "-rf"}, "plain path"),
    ]:
        try:
            git_read_command(bad, ctx)
            assert False, f"should have refused {bad!r}"
        except ValueError as e:
            assert expect in str(e), f"{bad!r} -> {e}"

    # the ops it DOES accept compose, and none of them can write
    for op in GIT_OPS:
        cmd = git_read_command({"op": op, "path": "sage"} if op != "status" else {"op": op}, ctx)
        assert cmd.startswith("git --no-pager")
        for forbidden in (" push", " commit", " reset", " checkout ", " clean"):
            assert forbidden not in cmd, f"{op} composed a writing command: {cmd}"

    try:
        git_read_command({"op": "log"}, {})
        assert False, "no worktree must refuse"
    except ValueError as e:
        assert "worktree" in str(e)


def test_the_judged_command_round_trips_even_when_seat_paths_contain_spaces():
    """The judged==executed invariant is a property of the STRING, not of the fleet's
    current directory names. Both composers quoted the being-supplied value and interpolated
    the seat-configured worktree and target RAW; a worktree containing a space would split
    into extra argv, and the law would have judged a command that is not the one that runs
    (GPT review of #83). Fleet paths are simple today — the invariant must not depend on
    that staying true."""
    import shlex
    from sage.gateway.being_gate_client import git_read_command, search_command

    wt = "/home/dp/a path/with spaces"
    ctx = {"worktree": wt}

    for label, cmd in (("git_read", git_read_command({"op": "show", "path": "sage"}, ctx)),
                       ("search", search_command({"pattern": "def x", "path": "sage"}, ctx))):
        argv = shlex.split(cmd)
        assert argv[-1] == f"{wt}/sage", f"{label}: pathspec split into {argv[-3:]}"
        assert wt in argv[argv.index("-C") + 1] if "-C" in argv else True

    # and the being-supplied pattern stays one element beside them
    argv = shlex.split(search_command({"pattern": "seed, posture = compose"}, ctx))
    assert argv[argv.index("-e") + 1] == "seed, posture = compose"


def test_every_git_op_the_grammar_accepts_is_named_in_the_schema():
    """An affordance the being holds but is not told about is one it does not have.

    GPT's second pass on SAGE#83: GIT_OPS accepted 'cat' and the published schema listed
    only five ops, so `git_read op='cat'` worked and nothing ever said so. Same class as a
    registry verb that is never offered — the capability exists and the being cannot find
    it. The schema text is derived from GIT_OPS now, so the two cannot drift again; this
    pins that they agree in both directions.
    """
    from sage.gateway.being_gate_client import GIT_OPS, _TOOL_SCHEMAS
    op_text = _TOOL_SCHEMAS["git_read"][1]["op"]
    for op in GIT_OPS:
        assert repr(op) in op_text, f"git_read accepts {op!r} and the schema never mentions it"
    # And the reverse: the schema must not advertise an op the grammar would refuse. Only
    # the enumeration itself is an offer of ops — the prose after it names argument names
    # like 'path', which are not ops and must not be read as one.
    import re
    enumeration = op_text.split(" (", 1)[0]
    for advertised in re.findall(r"'([a-z]+)'", enumeration):
        assert advertised in GIT_OPS, \
            f"the schema offers {advertised!r}, which git_read_command refuses"


def test_an_escape_refusal_names_the_worktree_and_the_relative_form():
    """The refusal held the answer and did not say it.

    Measured 2026-09-14: legion-being, acting on a review comment, was refused four times in
    one beat for guessing at its own worktree root — first `/home/dp/ai-worktrees/...`, then
    `/home/dp/ai-workspace/SAGE/.worktrees/...`. Neither is right. Every refusal said only
    "escapes your worktree", which is the one fact it already had. The beat ended with no act.

    Naming the root in the seed is not the fix and the header comment beside `Your home`
    says why: 15 of 15 path refusals on Sprout were that string reproduced from memory and
    truncated. The correction belongs at the moment of the mistake, and it must point at the
    relative form, which needs no memory at all.
    """
    from sage.gateway.being_gate_client import search_command, git_read_command

    WT = "/home/dp/ai-workspace/being-worktrees/legion-being"
    wrong = "/home/dp/ai-worktrees/legion-being/sage/gateway"

    for verb, call in (("search", lambda p: search_command({"pattern": "x", "path": p},
                                                           {"worktree": WT})),
                       ("git_read", lambda p: git_read_command({"op": "blame", "path": p},
                                                               {"worktree": WT}))):
        try:
            call(wrong)
        except ValueError as e:
            msg = str(e)
        else:
            raise AssertionError(f"{verb} accepted a path outside the worktree")

        assert WT in msg, f"{verb} refusal does not name the worktree root: {msg!r}"
        assert "RELATIVE" in msg or "relative" in msg, \
            f"{verb} refusal does not point at the form that needs no memory: {msg!r}"
        assert wrong in msg, f"{verb} refusal should still quote what was asked for: {msg!r}"

    # A path INSIDE the worktree is unaffected, absolute or relative.
    assert "hestia_dispatch.py" in search_command(
        {"pattern": "x", "path": "sage/gateway/hestia_dispatch.py"}, {"worktree": WT})
    assert "hestia_dispatch.py" in search_command(
        {"pattern": "x", "path": f"{WT}/sage/gateway/hestia_dispatch.py"}, {"worktree": WT})


def test_a_failure_that_explains_itself_in_result_is_not_rendered_as_none():
    """The envelope held a complete account and the renderer threw it away.

    Found 2026-09-14 by legion-being, on the first live use of its own camera verb.
    `_do_camera` reports failures through `result` — device, exit code, and a sentence
    naming which kind of failure — and leaves `error` unset because the explanation is
    structured. to_tool_message assumed not-ok implied `error`, so the being was handed the
    literal string "[dispatch error — None]" twice and could diagnose nothing. It reported
    an empty-error envelope matching no code path, which was exactly right.

    Every other verb happens to set `error`, so this stayed invisible until a verb chose the
    other shape.
    """
    from sage.gateway.being_gate_client import ResultEnvelope

    structured = ResultEnvelope(ok=False, witness_id="act-1",
                                result={"device": "/dev/video0", "exit_code": 251,
                                        "note": "no frame was written"})
    msg = structured.to_tool_message()
    assert "None" not in msg, f"the failure rendered as None: {msg!r}"
    assert "/dev/video0" in msg and "251" in msg, \
        f"the account the envelope carried must survive rendering: {msg!r}"
    assert "act-1" in msg, "a witnessed failure is still witnessed"

    # The ordinary shape is unchanged.
    plain = ResultEnvelope(ok=False, error="it broke")
    assert plain.to_tool_message() == "[dispatch error — it broke]"

    # And an envelope carrying NEITHER says so, rather than saying None.
    empty = ResultEnvelope(ok=False)
    out = empty.to_tool_message()
    assert "None" not in out and "harness defect" in out, out


# ---- carried from legion/mission-artifact in the 2026-09-18 reconciliation ----
import tempfile


def test_recall_schema_offers_the_second_half_of_retrieval():
    """A search result is a PREVIEW. membot's own docstring names get_passage(idx) as the
    other half of the pattern, and until 2026-09-18 no verb reached it: 451 memories the
    being could see the opening of and read the whole of none. One verb, two forms —
    a second verb would cost ~700 characters of prompt on every beat."""
    from sage.gateway.being_gate_client import ollama_tools
    (spec,) = ollama_tools(["recall"])
    params = spec["function"]["parameters"]
    assert set(params["properties"]) == {"query", "top_k", "idx"}, params
    # NEITHER form is required: requiring `query` would make the idx form look malformed
    # to the model, and requiring nothing is safe because the dispatcher refuses a call
    # with neither and names both.
    assert params["required"] == [], params
    assert "idx" in spec["function"]["description"], spec["function"]["description"]

def test_check_is_judged_as_the_pytest_command_the_seat_runs():
    """check reaches the law as the exact command, and the allow-list is the whole grammar:
    a being can name a declared suite or one test inside it, and nothing else."""
    from sage.gateway.being_gate_client import check_command
    seen = {}
    c = _client(_allows)
    c.worktree = "/tmp/being-wt"
    c._core = SimpleNamespace(
        NormalizedEvent=lambda **kw: seen.update(kw) or SimpleNamespace(raw=kw.get("raw", {}), tool=kw.get("tool")),
        evaluate=lambda ev, prof, ws, policy=None: SimpleNamespace(
            decision="allow", rule="", reason="ok", innate=False),
    )
    c.gate(BeingIntent("check", {"target": "gateway"}))
    # ABSOLUTE, inside the worktree: the law must judge the path the command touches, not
    # the same relative path resolved against the shared checkout (measured 2026-09-07).
    #
    # Asserted as a SUFFIX rather than the whole string: since the M1 unblock the command
    # is wrapped in a bwrap prefix whose exact flags belong to
    # test_check_runs_under_a_principal_that_is_not_the_seat. Pinning the entire string
    # here made THIS test fail for a change it does not describe — and it is what the law
    # judges that matters, which is the pytest invocation and its paths.
    assert seen["command"].endswith(
        "python3 -m pytest -q -c /dev/null -p no:cacheprovider --rootdir=/tmp/being-wt "
        "/tmp/being-wt/sage/gateway/tests/"), seen["command"]
    assert seen["tool"] == "check"
    c.gate(BeingIntent("check", {"target": "gateway::test_thing"}))
    assert seen["command"].endswith("/tmp/being-wt/sage/gateway/tests/ -k test_thing")
    # no worktree is a deny, never a command judged against somebody else's tree
    c.worktree = None
    v = c.gate(BeingIntent("check", {"target": "gateway"}))
    assert v.decision == "deny" and v.rule == "gate.raised", v
    c.worktree = "/tmp/being-wt"
    # anything the allow-list cannot represent is a deny, never a shell
    for bad in ("; rm -rf /", "sage/", "gateway::a b", "gateway::../x", "", "other"):
        v = c.gate(BeingIntent("check", {"target": bad}))
        assert v.decision == "deny" and v.rule == "gate.raised", (bad, v)
    for bad in ({"target": "gateway::a;b"}, {"target": "irp::"}):
        try:
            check_command(bad, {"worktree": "/tmp/being-wt"})
            assert False, bad
        except ValueError:
            pass

def test_git_read_grammar_refuses_everything_that_would_make_a_read_a_run():
    """git IS the composition hazard, not the pairing (2026-09-07).

    `git` will execute code on request — external diff drivers, textconv filters, pagers,
    aliases, and `-c` overrides that install any of them. A read verb that let the being
    supply a flag would be a run verb wearing a read verb's name. So the seat builds the
    whole command, the being names only an op/rev/path/n, and every one is matched against
    a grammar first."""
    from sage.gateway.being_gate_client import git_read_command

    ctx = {"worktree": "/tmp/wt"}
    ok = git_read_command({"op": "log", "n": 5}, ctx)
    for pin in ("--no-pager", "--no-ext-diff", "--no-textconv"):
        assert pin in ok, f"{pin} must be pinned on every read: {ok}"
    # FLAGS ONLY: `-c key=value` hardening reads as a path token to hestia's mrh.command and
    # was refused on every invocation (measured 2026-09-07). The refusal was right; hardening
    # that trips the law is hardening that does not ship.
    assert " -c " not in ok, f"no -c overrides: mrh.command reads them as paths — {ok}"
    assert " log " in ok and "-n 5" in ok

    # n is clamped, not trusted
    assert "-n 50" in git_read_command({"op": "log", "n": 9999}, ctx)
    assert "-n 1" in git_read_command({"op": "log", "n": -3}, ctx)

    hostile = [
        ({"op": "push"}, "op"),                              # a writing subcommand
        ({"op": "log", "rev": "--upload-pack=evil"}, "rev"),  # a flag as a revision
        ({"op": "diff", "rev": "HEAD", "rev2": "-c"}, "rev2"),
        ({"op": "show", "path": "../../../etc/passwd"}, "path"),
        ({"op": "log", "path": "-c"}, "path"),               # a flag as a path
        ({"op": "blame"}, "path"),                           # blame without a target
    ]
    for args, expect in hostile:
        try:
            cmd = git_read_command(args, ctx)
            raise AssertionError(f"{args} produced a command instead of a refusal: {cmd}")
        except ValueError as e:
            assert expect in str(e), f"{args}: refusal must name the field, got {e}"

    # a pathspec is resolved ABSOLUTE so hestia's mrh.command can match it against the
    # being's granted prefixes; relative pathspecs match nothing and the read is refused
    cmd = git_read_command({"op": "show", "rev": "HEAD", "path": "sage/gateway/x.py"},
                           {"worktree": "/tmp/wt"})
    assert "-- /tmp/wt/sage/gateway/x.py" in cmd, cmd

    # no worktree is a refusal, never a read of the seat's own tree
    try:
        git_read_command({"op": "status"}, None)
        raise AssertionError("git_read without a worktree must refuse")
    except ValueError as e:
        assert "worktree" in str(e)

def test_git_read_is_offered_and_consequential():
    from sage.gateway.being_gate_client import ollama_tools, _CONSEQUENTIAL, _REGISTRY
    assert "git_read" in _REGISTRY and "git_read" in _CONSEQUENTIAL
    names = [t["function"]["name"] for t in ollama_tools()]
    assert "git_read" in names
    schema = next(t for t in ollama_tools() if t["function"]["name"] == "git_read")
    assert schema["function"]["parameters"]["required"] == ["op"]
    assert "cannot commit, push, or move a branch" in schema["function"]["description"]

def test_check_runs_under_a_principal_that_is_not_the_seat():
    """THE M1 PREREQUISITE. PRD r3 §5 made principal isolation a hard blocker on M1, with a
    concrete falsifier in §10.5: from the being's principal, reads of the vault, the hestia
    socket and the agent environment must all fail.

    Why it is not optional: `check` executes pytest, pytest imports conftest.py from its
    rootdir, and M1 gives the being write access to that rootdir. Under the seat's own uid
    those two gated verbs compose into arbitrary code holding the vault passphrase and
    every key on the box (measured 2026-09-07, SAGE#55).
    """
    from sage.gateway.being_gate_client import (
        check_command, sandbox_available, sandbox_prefix, SANDBOX_REQUIRED)

    if not sandbox_available():
        # Presence is not permission: on Ubuntu 24.04 bwrap exists and every attempt fails
        # until an AppArmor profile grants it `userns`. Where it is unavailable the only
        # correct behaviour is to REFUSE, never to run unsandboxed.
        assert SANDBOX_REQUIRED, "a machine without a sandbox must not run checks unsandboxed"
        try:
            check_command({"target": "gateway"}, {"worktree": "/tmp/wt"})
            raise AssertionError("check must refuse when it cannot get its sandbox")
        except ValueError as e:
            assert "sandbox" in str(e)
        return

    cmd = check_command({"target": "gateway"}, {"worktree": "/tmp/wt"})
    assert cmd.startswith("/usr/bin/bwrap "), cmd[:80]

    # the properties that make it a different principal, each named
    for flag, why in (
        ("--clearenv", "the seat's environment, agent sockets included, must not survive"),
        ("--unshare-net", "no network: the hestia socket and ollama are the seat's, not its"),
        ("--unshare-pid", "it cannot see or signal the seat's processes"),
        ("--new-session", "nor reach the seat's controlling terminal or process group"),
        ("--die-with-parent", "a runaway cannot outlive the beat that started it"),
        ("--ro-bind /usr /usr", "the system is readable and not writable"),
        ("--ro-bind /tmp/wt /tmp/wt", "the worktree is READ-ONLY inside the run: pytest imports "
                                      "conftest.py from the rootdir before collecting, so a "
                                      "writable mount lets a being-authored conftest rewrite "
                                      "source mid-run and restore it"),
        ("--tmpfs /tmp", "everything the run genuinely needs to write goes here"),
    ):
        assert flag in cmd, f"missing {flag}: {why}"

    # nothing of the seat's home is bound beyond the interpreter
    import re
    binds = re.findall(r"--(?:ro-)?bind (\S+) ", cmd)
    for b in binds:
        assert not b.startswith("/home/dp/ai-workspace/SAGE/sage/instances"), \
            f"the being's own home must not be inside the tree check executes: {b}"
    assert "C.UTF-8" not in cmd, \
        "hestia #988 splits a dotted token and refuses the whole command; PYTHONUTF8 instead"

def test_git_read_rev_suffixes_work_on_any_base_and_still_take_no_flags():
    """`<sha>~1` was refused (two witnessed denies, 2026-09-08). Flagged by the being as an
    affordance fact, not litigated. Widened deliberately: a suffix is ~ or ^ plus digits."""
    from sage.gateway.being_gate_client import git_read_command
    ctx = {"worktree": "/tmp/wt"}
    for rev in ("18c9526a6~1", "18c9526a6^", "legion/mission-artifact~3", "HEAD~2", "main^2"):
        cmd = git_read_command({"op": "show", "rev": rev}, ctx)
        assert f" {rev}" in cmd, cmd
    for bad in ("18c9526a6~x", "HEAD~1..HEAD", "--all", "sha~-1", "HEAD ~1"):
        try:
            git_read_command({"op": "show", "rev": bad}, ctx)
            raise AssertionError(f"{bad!r} must be refused")
        except ValueError:
            pass

def test_git_read_rejects_whitespace_so_judged_argv_is_executed_argv():
    """GPT review of #56, point 6: a path with a space passed the grammar, was interpolated
    unquoted into the judged string, and shlex.split() handed the executor more argv than
    the law saw. One representation, or the gate rules on a command that is not the one run."""
    from sage.gateway.being_gate_client import git_read_command
    ctx = {"worktree": "/tmp/wt"}
    for args in ({"op": "show", "rev": "HEAD", "path": "sage/gate way/x"},
                 {"op": "log", "path": "a\tb"},
                 {"op": "show", "rev": "HEAD --all"}):
        try:
            git_read_command(args, ctx)
            raise AssertionError(f"{args} must be refused")
        except ValueError as e:
            assert "whitespace" in str(e) or "rev" in str(e), e
    ok = git_read_command({"op": "show", "rev": "HEAD", "path": "sage/gateway/x"}, ctx)
    import shlex
    assert shlex.split(ok)[-1] == "/tmp/wt/sage/gateway/x", "one path, one argv element"

def test_pr_open_base_is_the_worktrees_upstream_not_a_hard_coded_branch(tmp_path, monkeypatch):
    """GPT review of #56, point 8: a hard-coded `legion/mission-artifact` base is right only
    while the being rides that branch; after decomposition it would propose against dead
    history. The base is read from what legion-being/work tracks — the current integration
    target by construction — with SAGE_PR_BASE as the explicit override."""
    import subprocess
    from sage.gateway.being_gate_client import pr_base_branch, pr_open_command
    origin = tmp_path / "o.git"; subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    wt = tmp_path / "wt"; subprocess.run(["git", "clone", "-q", str(origin), str(wt)], check=True)
    g = lambda *a: subprocess.run(["git", "-C", str(wt), *a], check=True, capture_output=True, text=True)
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (wt / "f").write_text("x"); g("add", "-A"); g("commit", "-q", "-m", "base")
    g("push", "-q", "origin", "HEAD:legion/some-integration-target")
    g("checkout", "-q", "-b", "legion-being/work", "--track", "origin/legion/some-integration-target")
    monkeypatch.delenv("SAGE_PR_BASE", raising=False)
    assert pr_base_branch(str(wt)) == "legion/some-integration-target"
    assert "--base legion/some-integration-target" in pr_open_command(
        {"slug": "s-1", "title": "a title long enough", "body": "b"}, {"worktree": str(wt)})
    monkeypatch.setenv("SAGE_PR_BASE", "main")
    assert pr_base_branch(str(wt)) == "main", "explicit override wins"
    assert pr_base_branch(str(tmp_path)) == "main", "no upstream: main, never a stale carrier"

def test_check_sandbox_measured_from_inside_with_a_real_conftest():
    """GPT on SAGE#56: "strengthen the bwrap regression arm with a real fixture." The test
    above asserts FLAGS. Flags are the command's claim about itself; this runs the command
    check would run — the exact string, shlex-split, no substitution — against a worktree
    whose conftest.py is the M1 attack (being-authored code that pytest imports before any
    test), and reads what that code could reach.

    HOW THE REPORT GETS OUT, now that the worktree is mounted READ-ONLY (GPT review of #84):
    the conftest writes it to the sandbox's own tmpfs, and a planted test FAILS with the
    content as its assertion message, which pytest prints. So the run is proved to have
    collected and executed inside the sandbox — not merely to have imported a conftest — and
    the probe still comes back. The read-only mount is itself one of the things probed.

    (`from os import environ`, here and in the probe, is hestia #988: the gate splits the
    dotted spelling and refuses the fragment as a secret file.)"""
    import json
    import os
    import shlex
    import shutil
    import subprocess
    import tempfile
    from os import environ
    from sage.gateway.being_gate_client import check_command, sandbox_available, CHECK_TARGETS

    if not sandbox_available():
        return  # the refusal arm is pinned above; nothing to measure from inside

    wt = tempfile.mkdtemp(prefix="m1-fixture-wt-")
    outside = tempfile.mkdtemp(prefix="m1-fixture-outside-")
    secret = os.path.join(outside, "vault.key")
    open(secret, "w").write("SEAT-ONLY")
    canary = "SAGE_M1_CANARY"
    suite_dir = os.path.join(wt, CHECK_TARGETS["gateway"])
    os.makedirs(suite_dir)
    open(os.path.join(wt, "conftest.py"), "w").write(f'''
import json, os, socket
from os import environ
r = {{"env_canary": {canary!r} in environ, "env_keys": sorted(environ)}}
try:
    open({secret!r}).read(); r["read_outside"] = True
except Exception as e:
    r["read_outside"] = repr(e)
try:
    open({secret!r} + ".w", "w").write("x"); r["write_outside"] = True
except Exception as e:
    r["write_outside"] = repr(e)
try:
    open(os.path.expanduser("~/.hestia")); r["home_hestia"] = True
except Exception as e:
    r["home_hestia"] = repr(e)
try:
    s = socket.create_connection(("127.0.0.1", 7711), timeout=2); s.close(); r["hestia_socket"] = True
except Exception as e:
    r["hestia_socket"] = repr(e)
try:
    # A pid number is namespace-relative: inside a nested sandbox (this suite run through
    # `check`, legion-being 20:41Z 2026-09-08) pid {os.getpid()} exists again and is a
    # different process. Compare the process's start time, not the number.
    st = open("/proc/{os.getpid()}/stat").read().rsplit(")", 1)[1].split()
    r["sees_seat_pid"] = (st[19] == {os.stat("/proc/self/stat") and open("/proc/self/stat").read().rsplit(")", 1)[1].split()[19]!r})
except Exception as e:
    r["sees_seat_pid"] = repr(e)
try:
    open(os.path.join({wt!r}, "probe-writes-into-the-worktree.txt"), "w").write("x")
    r["write_worktree"] = True
except Exception as e:
    r["write_worktree"] = repr(e)
open("/tmp/m1probe.json", "w").write(json.dumps(r))   # tmpfs: writable, and private to the sandbox
''')
    # The planted test carries the probe OUT: pytest prints a failing test's assertion
    # message, and nothing else inside this sandbox can reach the caller.
    open(os.path.join(suite_dir, "test_probe.py"), "w").write(
        "def test_probe_reports():\n"
        "    import json\n"
        # The marker is BUILT, not written whole: pytest echoes the failing test's source
        # above its message, so a literal marker would be found in the echo first.
        "    assert False, 'M1' + 'PROBE ' + json.dumps(json.load(open('/tmp/m1probe.json')))\n")

    cmd = check_command({"target": "gateway"}, {"worktree": wt})
    env = dict(environ, **{canary: "planted-in-the-seat-env"})
    try:
        r = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=120, env=env)
        # 1 == "collected and ran, and the planted test failed as designed" — which is how
        # the probe is carried out. A 2/3/4 would mean pytest never got that far.
        assert r.returncode == 1, r.stdout[-800:] + r.stderr[-800:]
        assert "1 failed" in r.stdout, r.stdout[-800:]                  # it RAN, in the sandbox
        # The worktree is under /tmp on purpose: the first cut of the sandbox mounted
        # --tmpfs /tmp AFTER the worktree bind and masked it — pytest collected nothing
        # and this file was never written. Mount order is part of what is measured.
        i = r.stdout.find("M1PROBE {")
        assert i >= 0, r.stdout[-800:] + r.stderr[-800:]
        probe = json.loads(r.stdout[i + len("M1PROBE "):].splitlines()[0])
    finally:
        shutil.rmtree(wt, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)
    assert probe["env_canary"] is False, probe["env_keys"]           # --clearenv held
    # What the SEAT had that the sandbox also has: only what the prefix sets on purpose.
    # (LC_CTYPE and PYTEST_VERSION show up inside — python's UTF-8 mode and pytest set
    # them there; they are not the seat's.)
    # PYTEST_VERSION: this test is itself running under pytest, so the seat has it too —
    # an intersection artefact, not a leak (the canary is the leak detector).
    leaked = (set(probe["env_keys"]) & set(environ)) - {
        "HOME", "PATH", "PWD", "PYTHONUTF8", "PYTHONDONTWRITEBYTECODE", "LANG", "LC_CTYPE",
        "PYTEST_VERSION"}
    assert not leaked, sorted(leaked)
    assert probe["read_outside"] is not True and "No such file" in probe["read_outside"], probe
    assert probe["write_outside"] is not True, probe                 # outside is not even bound
    assert probe["home_hestia"] is not True, probe
    assert probe["hestia_socket"] is not True, probe                 # --unshare-net held
    assert probe["sees_seat_pid"] is not True, probe                 # --unshare-pid held (start-time compared)
    # AND THE TREE IT EXECUTES IS NOT A TREE IT CAN WRITE. Being-authored code imported
    # before collection cannot rewrite the source the run is evidence about.
    assert probe["write_worktree"] is not True, probe

def test_pr_amend_reads_the_branch_from_the_worktree_and_refuses_a_non_pr_branch():
    """SAGE#63: the review asked for a corrected body and a green suite, and the author had
    no verb that could reach either — pr_open claims a slug once and refuses it after. The
    being names neither branch nor PR number here; both are read, so it can only revise its
    own open proposal."""
    import subprocess
    import pytest
    from sage.gateway.being_gate_client import pr_amend_command, _pr_number_for_branch

    wt = tempfile.mkdtemp(prefix="pr-amend-")
    def git(*a):
        return subprocess.run(["git", *a], cwd=wt, capture_output=True, text=True)
    git("init", "-q"); git("config", "user.email", "t@t"); git("config", "user.name", "t")
    open(os.path.join(wt, "f"), "w").write("x"); git("add", "-A"); git("commit", "-qm", "c")

    git("checkout", "-qb", "legion-being/work")
    with pytest.raises(ValueError, match="not one of your PR branches"):
        _pr_number_for_branch(wt)          # the work branch is not a proposal
    git("checkout", "-qb", "some/other")
    with pytest.raises(ValueError, match="not one of your PR branches"):
        _pr_number_for_branch(wt)

    # arg validation happens before any lookup, so a bad call never reaches the network
    for bad, msg in ((({"title": "too short", "message": "m"}), None),
                     (({"title": "a" * 200, "message": "m"}), "8-120"),
                     (({"title": "a proper title here", "message": "  "}), "needs a 'message'")):
        if msg is None:
            continue
        with pytest.raises(ValueError, match=msg):
            pr_amend_command(bad, {"worktree": wt})
    with pytest.raises(ValueError, match="needs a worktree"):
        pr_amend_command({"title": "a proper title here", "message": "m"}, {})

    # no new body -> commit and push only; nothing outward is composed
    assert pr_amend_command({"title": "a proper title here", "message": "why"},
                            {"worktree": wt}) == "true"

def test_pr_amend_is_offered_to_the_being():
    """A verb in the registry but not in the offered set is a verb the being does not have."""
    from sage.gateway.being_gate_client import _REGISTRY
    from sage.gateway.heartbeat import EXPLORE_TOOLS
    assert "pr_amend" in _REGISTRY
    assert "pr_amend" in EXPLORE_TOOLS
    assert _REGISTRY["pr_amend"]["tool"] == "pr_amend"      # the law sees the outward act

def test_pr_base_refuses_to_guess_when_the_upstream_is_unset():
    """#63: legion-being/work tracked nothing, pr_base_branch fell through to "main", and a
    159-line change was proposed as 9,271 additions across 55 files. Unreviewable, and
    closed. A wrong base is worse than no PR — the being cannot see the diff it proposed.

    (`from os import environ`, again, is hestia #988: the gate splits the dotted spelling
    and refuses the fragment as a secret path.)"""
    import subprocess
    import pytest
    from os import environ
    from sage.gateway.being_gate_client import pr_base_branch

    wt = tempfile.mkdtemp(prefix="pr-base-")
    def git(*a):
        return subprocess.run(["git", *a], cwd=wt, capture_output=True, text=True)
    git("init", "-q"); git("config", "user.email", "t@t"); git("config", "user.name", "t")
    open(os.path.join(wt, "f"), "w").write("x"); git("add", "-A"); git("commit", "-qm", "c")
    git("branch", "legion-being/work")

    with pytest.raises(ValueError, match="cannot determine the base branch"):
        pr_base_branch(wt)                       # no upstream: refuse, never "main"

    # an explicit override is still honoured
    environ["SAGE_PR_BASE"] = "legion/some-integration"
    try:
        assert pr_base_branch(wt) == "legion/some-integration"
    finally:
        del environ["SAGE_PR_BASE"]

def test_git_read_cat_returns_a_file_at_a_revision_and_still_takes_no_flags():
    """The being tried `show <rev>:<path>` to read the clean version of a file it had
    damaged — its worktree copy was the broken one and the good version existed only at the
    base commit. Refused (deny d250004396e0, 2026-09-10), and nothing else in its registry
    could read it. `show` with a pathspec is a DIFF lens, not the file."""
    import pytest
    from sage.gateway.being_gate_client import git_read_command, GIT_OPS
    ctx = {"worktree": "/tmp/wt"}
    assert "cat" in GIT_OPS

    cmd = git_read_command({"op": "cat", "rev": "cc64c838c", "path": "a/b.py"}, ctx)
    assert cmd.endswith(" cc64c838c:a/b.py")           # rev:path, relative — git resolves that
    assert git_read_command({"op": "cat", "path": "a/b.py"}, ctx).endswith(" HEAD:a/b.py")

    for bad, msg in ((({"op": "cat", "rev": "HEAD"}), "needs a 'path'"),
                     (({"op": "cat", "path": "../../etc/passwd"}), "plain path inside"),
                     (({"op": "cat", "path": "x", "rev": "--upload-pack=evil"}), "must be a sha"),
                     (({"op": "cat", "path": "a b.py"}), "may not contain whitespace")):
        with pytest.raises(ValueError, match=msg):
            git_read_command(bad, ctx)

def test_git_restore_takes_its_content_from_history_and_no_flags():
    """Restoring a file was possible with cat + memory_write(replace) and impossible in
    practice: it means copying the file verbatim through the being's own output. Fifteen
    beats, a 4,621-char file it could read perfectly, never restored. The reconstruction
    was the wall, not the intent."""
    import pytest
    from sage.gateway.being_gate_client import git_restore_command, _REGISTRY, _CONSEQUENTIAL
    from sage.gateway.heartbeat import EXPLORE_TOOLS
    ctx = {"worktree": "/tmp/wt"}

    cmd = git_restore_command({"rev": "cc64c838c", "path": "a/b.py"}, ctx)
    assert cmd.startswith("git --no-pager -C /tmp/wt checkout cc64c838c -- ")
    assert cmd.endswith("/tmp/wt/a/b.py")          # absolute, resolved inside the worktree

    for bad, msg in ((({"rev": "cc64c838c"}), "needs a 'path'"),
                     (({"path": "a/b.py"}), "must be a sha"),
                     (({"rev": "--upload-pack=x", "path": "a/b.py"}), "must be a sha"),
                     (({"rev": "HEAD", "path": "../../etc/passwd"}), "plain path inside"),
                     (({"rev": "HEAD", "path": "a b.py"}), "may not contain whitespace")):
        with pytest.raises(ValueError, match=msg):
            git_restore_command(bad, ctx)
    with pytest.raises(ValueError, match="needs a worktree"):
        git_restore_command({"rev": "HEAD", "path": "a.py"}, {})

    assert "git_restore" in _REGISTRY and "git_restore" in _CONSEQUENTIAL
    assert "git_restore" in EXPLORE_TOOLS

def test_every_composed_verb_composes_at_the_GATE_too(monkeypatch):
    """THERE ARE TWO COMPOSITION SITES AND ONLY ONE GETS EXERCISED BY THE VERB TESTS.

    The dispatcher composes the command it EXECUTES. `_normalize` composes the command the
    law JUDGES. They must agree, and the judged one is built from a context this client
    assembles — so a compose that starts needing a new root goes on passing every direct
    test of itself while the gate raises on it.

    Measured 2026-09-14: `camera` moved to resolving against the being's home. `_do_camera`
    was updated, `_normalize`'s ctx was not, and every capture came back
    `gate.raised: ValueError: camera requires a memory_root context`. Thirteen tests of
    camera_command and _do_camera were green throughout, because none of them went through
    the gate. It failed closed, which is the right direction, but the verb was dead and the
    refusal said nothing a being could act on.

    This is the cheap general guard: walk the registry and make every composed verb build
    its command from the client's real context.
    """
    import tempfile
    import types
    from sage.gateway.being_gate_client import _REGISTRY, BeingGateClient, BeingIntent

    # pr_open resolves its base branch from the worktree's upstream and REFUSES rather than
    # guessing 'main'. That refusal is correct and is not what this test is about, so use the
    # explicit escape its own error names.
    monkeypatch.setenv("SAGE_PR_BASE", "legion/mission-artifact")

    home, wt = tempfile.mkdtemp(), tempfile.mkdtemp()
    c = BeingGateClient.__new__(BeingGateClient)
    c.worktree, c.memory_root, c.workspace = wt, home, wt
    c.game_stepper = "/opt/arc/being_board_step.py"        # `game` composes only with one
    c.member_id = "legion-being"                           # `run` stages under the member name
    c._core = types.SimpleNamespace(NormalizedEvent=lambda **kw: kw)

    # Minimal valid args per verb: enough to reach composition, nothing more.
    args_for = {
        "camera": {}, "search": {"pattern": "x"}, "check": {"target": "gateway"},
        "git_read": {"op": "status"}, "git_restore": {"rev": "HEAD", "path": "a.py"},
        "game": {"probes": [["ACTION1"]]},
        "run": {"path": "scratch/e.py"},
        "pr_open": {"slug": "camera-verb", "title": "add the camera verb", "body": "body text"},
        "pr_amend": {"title": "amend the camera verb", "message": "a one line commit message"},
        "pr_review": {"repo": "dp-web4/SAGE", "number": 1, "body": "b"},
    }

    composed = [v for v, spec in _REGISTRY.items() if spec.get("compose")]
    assert composed, "no composed verbs found; the registry shape changed"

    unexercised = []
    for verb in composed:
        if verb not in args_for:
            unexercised.append(verb)
            continue
        try:
            ev = c._normalize(BeingIntent(verb, dict(args_for[verb])))
        except Exception as e:
            raise AssertionError(
                f"{verb} composes in its own tests but RAISES at the gate: "
                f"{type(e).__name__}: {e}") from None
        assert ev["command"], f"{verb} composed an empty command at the gate"

    assert not unexercised, (
        f"composed verbs with no args in this test: {unexercised}. Add them — a verb absent "
        f"from this walk is a verb whose gate path nothing checks.")

def test_a_search_refused_for_a_word_in_its_pattern_says_so():
    """The harness holds both halves the being lacks, and used to say neither.

    hestia#1024: the gate resolves a bare word in a search PATTERN as a path and refuses when
    that word also names a real directory. The refusal reads as a scope problem, so a being
    inspects its grants — which are fine — and learns nothing. legion-being lost parts of five
    beats to one word while wiring the code whose key is spelled exactly that.

    The seat has the pattern it just sent and the refusal naming the token. Joining them turns
    an opaque deny into a next step, and changes no decision: the gate has already refused and
    that refusal stands untouched.
    """
    from sage.gateway.being_gate_client import _pattern_collision_hint, BeingIntent

    hit = _pattern_collision_hint(
        BeingIntent("search", {"pattern": "fresh_frame|images", "path": "hb.py"}),
        "'images' is not granted (granted: path:/ws/**)")
    assert "appears in your PATTERN" in hit, hit
    assert "scope is not the problem" in hit, hit
    assert "hestia#1024" in hit, "point at the defect so it is not rediscovered"
    assert "imag" in hit and "." in hit, f"it must supply the adaptation, not just a diagnosis: {hit}"

    # SILENT WHEN IT DOES NOT APPLY — a hint that fires on everything teaches nothing.
    assert _pattern_collision_hint(
        BeingIntent("search", {"pattern": "something_else"}),
        "'images' is not granted") == "", "the token is not in this pattern"
    assert _pattern_collision_hint(
        BeingIntent("memory_read", {"path": "images/x"}),
        "'images' is not granted") == "", "a real path deny must not be explained away"
    assert _pattern_collision_hint(
        BeingIntent("search", {"pattern": "x"}), "") == "", "no token named, nothing to say"

    # A refusal naming a PATH token must stay a path refusal, hint or not.
    assert _pattern_collision_hint(
        BeingIntent("search", {"pattern": "q", "path": "/etc/x"}),
        "'/etc/x' is not granted") == "", "a token with a separator is a path, not a pattern word"

def test_search_reaches_the_granted_tree_and_stops_at_the_machine(tmp_path):
    """An absolute path inside the fleet repo root composes; one outside it is refused HERE.

    Both halves are load-bearing and neither is redundant with the law. Measured against
    the live daemon 2026-09-14 with legion-being's real standing grant: `search` intents
    naming '/etc' and the operator's dotfile directory were ALLOWED by the gate, because
    command_scope_reach judges a command by splitting it on the workspace string and an
    absolute path that never names the workspace is not a token it ever sees. The gate
    says so itself ("the engine sandbox, not this check, is the fs boundary") and `search`
    does not run in the being's sandbox. So this refusal is the only one there is.

    The other half is the defect this fix exists for: the being was granted standing
    recursive read on the whole tree, `memory_read` honoured it that beat, and `search`
    refused it — not at the gate, at THIS function, before the gate ever saw the path.
    """
    from sage.gateway.being_gate_client import search_command

    root = tmp_path / "ws"                      # stands in for ~/ai-workspace
    wt = root / "being-worktrees" / "b"         # the being's own tree
    ws = root / "SAGE"                          # the gate workspace
    peer = root / "hestia"                      # a sibling repo it was granted
    for d in (wt, ws, peer):
        d.mkdir(parents=True)
    ctx = {"worktree": str(wt), "workspace": str(ws)}

    # the shape that was refused: an absolute path in a sibling repo under the same root
    for inside in (ws, peer, root):
        cmd = search_command({"pattern": "needle", "path": str(inside)}, ctx)
        assert cmd.startswith("grep -rn -I -E "), cmd
        assert cmd.endswith(f"-- {inside}"), cmd
        assert "--exclude-dir=.git" in cmd          # .git/config carries remote tokens
        assert " -e needle " in cmd

    # and the boundary: outside that tree is not a scope question, it is a no
    for outside in ("/etc", str(tmp_path / "elsewhere"), "/"):
        try:
            search_command({"pattern": "x", "path": outside}, ctx)
            assert False, f"{outside} should not be reachable"
        except ValueError as e:
            assert "outside anything you can reach" in str(e)
            assert str(root) in str(e), "the refusal must name where the line IS"

    # the being's own tree still composes `git grep`, absolutely or relatively — unchanged
    (wt / "f.py").write_text("needle\n")
    for p_ in ("f.py", str(wt / "f.py")):
        assert search_command({"pattern": "needle", "path": p_}, ctx).startswith(
            f"git --no-pager -C {wt} grep ")

    # NO WORKSPACE IN CTX IS THE OLD, CLOSED BEHAVIOUR. It matters because the dispatcher
    # composes from its own ctx: if it lacked the workspace it would build the worktree-only
    # string while the client judged the wide one, and _do_search refuses a mismatch.
    try:
        search_command({"pattern": "x", "path": str(peer)}, {"worktree": str(wt)})
        assert False, "without a workspace the reach must close, not open"
    except ValueError as e:
        assert "outside anything you can reach" in str(e)

def test_both_composition_sites_build_the_same_search(tmp_path, monkeypatch):
    """The judged string and the executed string, for an absolute path. SAGE#90.

    _do_search refuses when they differ, so a disagreement is a dead verb rather than an
    ungoverned act — which is why this is a test and not a comment. The workspace had to
    be threaded to the dispatcher for this to hold; before that it composed worktree-only.
    """
    from sage.gateway.being_gate_client import search_command
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher

    root = tmp_path / "ws"
    wt, ws = root / "wt", root / "SAGE"
    (ws / "sub").mkdir(parents=True)
    wt.mkdir(parents=True)
    args = {"pattern": "needle", "path": str(ws / "sub")}

    judged = search_command(args, {"worktree": str(wt), "memory_root": str(wt),
                                   "workspace": str(ws)})
    d = HestiaF1aDispatcher("t", memory_root=str(wt), worktree=str(wt), workspace=str(ws))
    executed = search_command(args, {"worktree": d.worktree, "workspace": d.workspace})
    assert judged == executed

def test_check_accepts_the_pytest_spelling_of_a_node_id(tmp_path):
    """Dialect is not a boundary. SAGE, 2026-09-14.

    legion-being was working a hop that one test would settle, read that test in the source,
    typed the pytest node id it had just read — `test_being_tool_loop.py::test_name` — and
    was refused for not using our `<suite>::<test>` spelling. It adapted in one step, which
    is the good case; the verb still refused a correct, unambiguous request for being
    written in the language of the tool it wraps.

    The BOUND is "inside a declared suite", and that is unchanged: a filename that no
    declared suite contains is still refused, and so is anything that is not a bare test
    identifier. What changed is that the file — the thing the being actually read — now
    resolves the suite, instead of the being having to know our name for the directory.
    """
    from sage.gateway.being_gate_client import check_command, CHECK_TARGETS

    wt = tmp_path / "wt"
    for rel in CHECK_TARGETS.values():
        (wt / rel).mkdir(parents=True, exist_ok=True)
    (wt / CHECK_TARGETS["gateway"] / "test_thing.py").write_text("def test_x(): pass\n")
    ctx = {"worktree": str(wt)}

    ours = check_command({"target": "gateway::test_x"}, ctx)
    theirs = check_command({"target": "test_thing.py::test_x"}, ctx)
    assert "-k test_x" in ours and "-k test_x" in theirs
    assert ours == theirs, "the two spellings must compose the SAME judged command"

    # a full path is the same node id with more of it typed — also accepted
    full = check_command({"target": f"{CHECK_TARGETS['gateway']}test_thing.py::test_x"}, ctx)
    assert full == ours

    # THE BOUND HOLDS. A file no declared suite contains is still refused, and the refusal
    # names the suites rather than restating the grammar.
    for bad, expect in (("nope.py::test_x", "no declared suite contains"),
                        ("gateway::test_x[p]", "bare identifier"),
                        ("gateway::../../etc", "bare identifier"),
                        ("not_a_suite::test_x", "must be one of")):
        try:
            check_command({"target": bad}, ctx)
            assert False, f"should have refused {bad!r}"
        except ValueError as e:
            assert expect in str(e), f"{bad!r} -> {e}"

    # and a refusal that can name the working string does name it
    try:
        check_command({"target": "gateway::test_x[p]"}, ctx)
    except ValueError as e:
        assert "Try 'gateway::test_x'" in str(e), e

def test_git_read_reaches_the_granted_tree_and_stops_at_the_machine(tmp_path):
    """Same reach as `search` (3fcca0830), same reason. legion-being, holding a standing
    recursive read grant on the workspace, asked for `git log` of its own instance directory
    in the live checkout — to classify a harness drift for itself — and was refused for
    escaping a worktree it had not named. A read of git history is a read."""
    import pytest
    from sage.gateway.being_gate_client import git_read_command
    root = tmp_path.resolve() / "ws"; wt = root / "being-worktrees" / "b"; ws = root / "SAGE"
    (ws / "sage" / "instances" / "x").mkdir(parents=True); wt.mkdir(parents=True)
    (ws / "sage" / "instances" / "x" / "todo.md").write_text("t\n")
    ctx = {"worktree": str(wt), "workspace": str(ws)}
    inst = str(ws / "sage" / "instances" / "x")

    cmd = git_read_command({"op": "log", "path": inst, "n": 5}, ctx)
    assert cmd.startswith(f"git --no-pager -C {inst} log "), cmd
    assert cmd.endswith(f"-- {inst}"), cmd
    f = git_read_command({"op": "show", "path": inst + "/todo.md"}, ctx)
    assert f.startswith(f"git --no-pager -C {inst} show "), "a FILE resolves -C to its directory"

    # relative paths are unchanged: worktree-bound, no -C
    assert git_read_command({"op": "log", "path": "sage"}, ctx).startswith("git --no-pager log ")
    # the bound: outside the fleet root is a no, not a scope question
    for bad in ("/etc", str(tmp_path / "elsewhere")):
        with pytest.raises(ValueError, match="outside anything you can reach"):
            git_read_command({"op": "log", "path": bad}, ctx)
    # cat needs the repo-relative form; refused outside, with the alternative named
    with pytest.raises(ValueError, match="memory_read"):
        git_read_command({"op": "cat", "path": inst + "/todo.md"}, ctx)
    # no workspace in ctx -> the old, closed behaviour (the dispatcher must pass it, or the
    # judged and executed strings disagree and the mismatch guard refuses)
    with pytest.raises(ValueError, match="outside anything you can reach"):
        git_read_command({"op": "log", "path": inst}, {"worktree": str(wt)})

def test_both_composition_sites_build_the_same_git_read(tmp_path):
    from sage.gateway.being_gate_client import git_read_command
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
    root = tmp_path.resolve() / "ws"; wt, ws = root / "wt", root / "SAGE"
    (ws / "sub").mkdir(parents=True); wt.mkdir(parents=True)
    args = {"op": "log", "path": str(ws / "sub"), "n": 3}
    judged = git_read_command(args, {"worktree": str(wt), "memory_root": str(wt), "workspace": str(ws)})
    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher); d.worktree = str(wt); d.workspace = str(ws)
    executed = git_read_command(args, {"worktree": d.worktree, "workspace": getattr(d, "workspace", None)})
    assert judged == executed == f"git --no-pager -C {ws}/sub log --no-ext-diff --no-textconv --oneline --no-decorate -n 3 -- {ws}/sub"

def test_game_command_grammar_cap_and_both_sites(tmp_path):
    """dp 2026-09-15: "build the game verb, batch with cap 8". The being names a game and
    probes; the SEAT composes the stepper line the law judges; whitespace-free by
    construction so judged == executed argv; the cap is refused with the cap named."""
    import pytest, sys, shlex
    from sage.gateway.being_gate_client import game_command, GAME_BATCH_CAP
    step = "/opt/arc/being_board_step.py"; home = str(tmp_path.resolve() / "home")
    ctx = {"memory_root": home, "game_stepper": step}
    cmd = game_command({"probes": [["ACTION6", 39, 47], ["action1"], {"action": "ACTION6", "x": 0, "y": 63}]}, ctx)
    assert cmd == f'{sys.executable} {step} --batch ft09 ACTION6:39:47+ACTION1+ACTION6:0:63 --instance {home}'
    assert shlex.split(cmd)[4] == 'ACTION6:39:47+ACTION1+ACTION6:0:63', "one argv element, judged == run"
    # single-probe form
    assert ' ACTION6:5:6 ' in game_command({"action": "ACTION6", "x": 5, "y": 6}, ctx)
    assert ' RESET ' in game_command({"action": "RESET"}, ctx)
    # probes as a JSON string (the model sometimes serialises the list itself)
    assert ' ACTION2 ' in game_command({"probes": '[["ACTION2"]]'}, ctx)
    # the cap, named
    with pytest.raises(ValueError, match=f"at most {GAME_BATCH_CAP} probes"):
        game_command({"probes": [["ACTION1"]] * (GAME_BATCH_CAP + 1)}, ctx)
    assert GAME_BATCH_CAP == 8
    game_command({"probes": [["ACTION1"]] * GAME_BATCH_CAP}, ctx)       # exactly the cap is fine
    # grammar
    for bad, why in ((["ACTION6", 64, 0], "within 0-63"), (["ACTION6", 1], "exactly"), (["ACTION1", 2, 3], "no coordinates"),
                     (["ACTION9"], "must be one of"), (["ACTION6", "a", 1], "whole numbers")):
        with pytest.raises(ValueError, match=why):
            game_command({"probes": [bad]}, ctx)
    with pytest.raises(ValueError, match="four-character id"):
        game_command({"probes": [["ACTION1"]], "game": "../x"}, ctx)
    # no stepper configured on this seat -> a refusal that says whose fault it is
    with pytest.raises(ValueError, match="no game is set up on this seat"):
        game_command({"probes": [["ACTION1"]]}, {"memory_root": home})
    # both composition sites: the client's ctx carries game_stepper, so the judged string
    # is the executed string (the dispatcher passes the same per-being fact)
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    d = D.__new__(D); d.memory_root = home; d.game_stepper = step
    assert game_command({"probes": [["ACTION6", 1, 2]]}, {"memory_root": d.memory_root, "game_stepper": d.game_stepper}) == \
        game_command({"probes": [["ACTION6", 1, 2]]}, ctx)

def test_game_is_offered_composed_and_consequential():
    from sage.gateway import being_gate_client as b
    from sage.gateway.heartbeat import EXPLORE_TOOLS
    assert "game" in EXPLORE_TOOLS
    assert b._REGISTRY["game"]["compose"] is b.game_command and b._REGISTRY["game"]["cmd_arg"] is None
    assert "game" in b._CONSEQUENTIAL
    assert "game" in b._TOOL_SCHEMAS and "8 probes" in b._TOOL_SCHEMAS["game"][0]

def test_game_look_is_a_window_not_a_move():
    """LOOK:x0:y0:x1:y1 rides the same grammar; bounded to 16x16; not a click, not a click's shape."""
    import pytest
    from sage.gateway.being_gate_client import game_command, LOOK_MAX_EDGE
    ctx = {"memory_root": "/tmp/h", "game_stepper": "/opt/arc/being_board_step.py"}
    assert " LOOK:44:44:49:49 " in game_command({"probes": [["LOOK", 44, 44, 49, 49]]}, ctx)
    assert " LOOK:0:0:15:15+ACTION6:1:2 " in game_command({"probes": [["look", 0, 0, 15, 15], ["ACTION6", 1, 2]]}, ctx)
    assert LOOK_MAX_EDGE == 16
    # the off-by-one the being hit twice: inclusive bounds, so 0..16 is 17 cells. The refusal
    # must name the size asked for and the x1 that would have worked.
    try:
        game_command({"probes": [["LOOK", 0, 0, 16, 16]]}, ctx); assert False
    except ValueError as e:
        assert "INCLUSIVE" in str(e) and "is 17x17 cells" in str(e) and "x1=x0+15" in str(e), str(e)
    game_command({"probes": [["LOOK", 0, 0, 15, 15]]}, ctx)          # exactly the cap is fine
    for bad, why in ((["LOOK", 0, 0, 16, 3], "is 17x4 cells"), (["LOOK", 5, 5, 4, 5], "x0 <= x1"), (["LOOK", 0, 0, 64, 0], "x0 <= x1"),
                     (["LOOK", 1, 2], "needs"), (["LOOK", "a", 0, 1, 1], "whole numbers")):
        with pytest.raises(ValueError, match=why):
            game_command({"probes": [bad]}, ctx)

def test_run_command_grammar_and_what_the_sandbox_contains():
    """`run` exists because the being could author a simulator and never execute one: writes
    land in its home, `check` executes its worktree, and _safe_path keeps those disjoint. The
    composed line must bind ONE seat-staged directory and nothing else."""
    import pytest
    from sage.gateway.being_gate_client import run_command, RUN_MAX_DATA, sandbox_available, sandbox_prefix
    if not sandbox_available():
        pytest.skip("no bubblewrap here; run_command refuses by design and there is nothing to shape-check")
    ctx = {"memory_root": "/home/x/inst", "member": "legion-being"}
    cmd = run_command({"path": "scratch/eval.py", "data": ["scratch/game/moves.md"]}, ctx)

    assert " --unshare-net " in cmd and " --clearenv " in cmd and " --die-with-parent " in cmd
    assert " --bind /tmp/sage-run-legion-being /work" in cmd, "one writable dir, seat-owned"
    assert cmd.rstrip().endswith("/work/eval.py"), cmd
    assert " --chdir /work " in cmd
    # NOTHING OF THE BEING'S AND NOTHING OF OURS IS IN THERE
    assert "/home/x/inst" not in cmd, "its home is never bound"
    assert cmd.count("--bind ") == 1, "exactly one writable bind"
    for ro in ("--ro-bind /usr /usr", "--ro-bind /lib /lib"):
        assert ro in cmd
    # strictly weaker than the `check` it already has: check binds a whole writable worktree
    # `check`'s own sandbox binds the worktree READ-ONLY since the reconciliation of
    # 2026-09-18 (a being-authored conftest must not be able to rewrite the source the run
    # is evidence about); `run`'s sandbox is the one with a writable dir, and it is /work.
    assert "--ro-bind /w/t /w/t" in sandbox_prefix("/w/t")

    for bad, why in (({"path": "scratch/e.sh"}, "must end in .py"),
                     ({"path": "/etc/x.py"}, "must be a file in your home"),
                     ({"path": "../x.py"}, "plain paths"),
                     ({"path": "a b.py"}, "whitespace"),
                     ({"path": ""}, "needs a 'path'"),
                     ({"path": "e.py", "data": ["d%d.md" % i for i in range(RUN_MAX_DATA + 1)]}, "at most 8")):
        with pytest.raises(ValueError, match=why):
            run_command(bad, ctx)
    with pytest.raises(ValueError, match="member name of its own"):
        run_command({"path": "e.py"}, {"memory_root": "/home/x/inst"})
    assert RUN_MAX_DATA == 8
    # DATA may come from anywhere the being can already read (2026-09-18): it wrote a script
    # to parse a source file its own memory_read reaches and run refused the path. The SCRIPT
    # stays in its home — code it executes is code it wrote.
    reach_ctx = {"memory_root": "/home/x/inst", "member": "b", "workspace": "/home/x/ws/SAGE"}
    cmd2 = run_command({"path": "scratch/e.py", "data": ["/home/x/ws/SAGE/game/ft09.py"]}, reach_ctx)
    assert cmd2.rstrip().endswith("/work/e.py")
    with pytest.raises(ValueError, match="outside anything you can reach"):
        run_command({"path": "scratch/e.py", "data": ["/etc/shadow"]}, reach_ctx)

def test_run_data_accepts_the_shapes_a_model_actually_emits():
    """First real use, 2026-09-17: the being sent data as a JSON string and as a bare path.
    Both iterated into CHARACTERS — "m.md" became four filenames — and three of its calls died.
    `game` already tolerated the JSON-string form for probes; this must too."""
    from sage.gateway.being_gate_client import run_command, sandbox_available
    import pytest
    if not sandbox_available():
        pytest.skip("no bubblewrap here")
    ctx = {"memory_root": "/home/x/inst", "member": "b"}
    for shape in ([], None, ["scratch/game/moves.md"], '["scratch/game/moves.md"]', "scratch/game/moves.md"):
        cmd = run_command({"path": "scratch/e.py", "data": shape}, ctx)
        assert cmd.rstrip().endswith("/work/e.py"), (shape, cmd)
    # a bare path and a one-element list must compose identically
    assert run_command({"path": "e.py", "data": "m.md"}, ctx) == run_command({"path": "e.py", "data": ["m.md"]}, ctx)
    # PROSE LISTS. 2026-09-18: it sent "a, b, c" and then "a b c"; both were refused for
    # "whitespace", which named nothing it could act on. Both now mean the same three files.
    three = run_command({"path": "e.py", "data": ["a.py", "b.jsonl", "c.npy"]}, ctx)
    assert run_command({"path": "e.py", "data": "a.py, b.jsonl, c.npy"}, ctx) == three
    assert run_command({"path": "e.py", "data": "a.py b.jsonl c.npy"}, ctx) == three
    assert run_command({"path": "e.py", "data": '["a.py","b.jsonl","c.npy"]'}, ctx) == three
    # and the refusal for a real space-in-path names the shapes that work
    with pytest.raises(ValueError, match="or as one path per entry"):
        run_command({"path": "e.py", "data": ["my file.md"]}, ctx)
    with pytest.raises(ValueError, match="must be a list of paths"):
        run_command({"path": "e.py", "data": 7}, ctx)

def test_run_is_offered_composed_and_consequential():
    from sage.gateway import being_gate_client as b
    from sage.gateway.heartbeat import EXPLORE_TOOLS
    assert "run" in EXPLORE_TOOLS and "run" in b._CONSEQUENTIAL
    assert b._REGISTRY["run"]["compose"] is b.run_command
    assert "PRINT" in b._TOOL_SCHEMAS["run"][0]
