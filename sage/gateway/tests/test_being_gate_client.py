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
