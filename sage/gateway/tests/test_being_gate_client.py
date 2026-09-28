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
        NormalizedEvent=lambda **kw: SimpleNamespace(raw=kw.get("raw", {}), tool=kw.get("tool"), command=kw.get("command")),
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
        NormalizedEvent=lambda **kw: seen.update(kw) or SimpleNamespace(raw=kw.get("raw", {}), tool=kw.get("tool"), command=kw.get("command")),
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
        NormalizedEvent=lambda **kw: seen.update(kw) or SimpleNamespace(raw=kw.get("raw", {}), tool=kw.get("tool"), command=kw.get("command")),
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
        NormalizedEvent=lambda **kw: seen.update(kw) or SimpleNamespace(raw=kw.get("raw", {}), tool=kw.get("tool"), command=kw.get("command")),
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
        ({"pattern": "x", "path": "/etc/passwd"}, "escapes your worktree"),
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
        ({"op": "show", "path": "/etc/passwd"}, "escapes"),
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

    Found 2026-09-14 by legion-being, on the first live use of a verb it wrote itself. That
    verb reports failures through `result` — device, exit code, a sentence naming the kind
    of failure — and leaves `error` unset because the explanation is structured. This
    renderer assumed not-ok implied `error`, so the being was handed the literal string
    "[dispatch error — None]" twice. It reported an empty-error envelope matching no code
    path, which was exactly right and as far as it could get.

    Latent on this branch, since every verb here sets `error`. Pinned anyway: the envelope
    is the contract, and a contract that silently drops one of its own fields will be
    rediscovered by whoever next writes a verb that fills the other one.
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

    assert ResultEnvelope(ok=False, error="it broke").to_tool_message() == \
        "[dispatch error — it broke]"

    out = ResultEnvelope(ok=False).to_tool_message()
    assert "None" not in out and "harness defect" in out, out


def test_unregistered_file_name_names_request_run():
    # cbp-being 2026-09-21: called its script's file name as a tool, appealed the refusal.
    v = _client(_allows).gate(BeingIntent("mechanism-training-script-clean.py", {"epochs": "10"}))
    assert v.rule == "registry.unbounded" and "request_run" in v.reason, v
    assert "path='mechanism-training-script-clean.py'" in v.reason, v
    # a plain unknown verb is not a file: no run hint, the door would be the wrong one
    v = _client(_allows).gate(BeingIntent("shell", {"command": "ls"}))
    assert v.rule == "registry.unbounded" and "request_run" not in v.reason, v
