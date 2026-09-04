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

def test_pr_review_stamps_the_target_repo_so_the_law_scopes_it_by_name():
    """The composed gh line names no filesystem path, so command-scope cannot see it
    (measured 2026-09-03: allow, rule "", under an EMPTY grant). The outward act must
    reach the law with the repository it targets in `repos`, so gate 1b (mrh.repo) rules
    it by name. Full `dp-web4/<name>`, never the bare name: a bare `SAGE` scope is also a
    path grant on the seat's SAGE checkout."""
    seen = {}
    c = _client(_allows)
    c._core = SimpleNamespace(
        NormalizedEvent=lambda **kw: seen.update(kw) or SimpleNamespace(raw=kw.get("raw", {}), tool=kw.get("tool")),
        evaluate=lambda ev, prof, ws, policy=None: SimpleNamespace(
            decision="allow", rule="", reason="ok", innate=False),
    )
    c.gate(BeingIntent("pr_review", {"repo": " dp-web4/SAGE ", "number": "34", "body": "x"}))
    assert seen["repos"] == ["dp-web4/SAGE"], seen["repos"]
    assert seen["paths"] == []
    # every other verb carries no repo name: the memory verbs stay path-scoped
    c.gate(BeingIntent("memory_write", {"path": "n.md", "content": "x"}))
    assert seen["repos"] == [], seen["repos"]


def test_pr_review_under_an_empty_grant_is_denied_by_the_real_law():
    """Sprout's objection on #34 as a red test against the SHARED law, not a mock:
    with `repos` stamped, an empty grant denies the outward act on mrh.repo; the grant
    that admits it is the repo's full name; a bare `SAGE` grant does not match.
    Skipped where the hestia gate core is not installed."""
    import pytest
    from sage.gateway.being_gate_client import _resolve_hestia_shared
    if not _resolve_hestia_shared():
        pytest.skip("hestia gate core not installed on this host")
    c = BeingGateClient("test-being", "/tmp/ws/test-being/identity.json", "/tmp/ws")
    assert c._core is not None, c._import_error
    core = c._core
    ev = c._normalize(BeingIntent("pr_review", {"repo": "dp-web4/SAGE", "number": "34", "body": "x"}))
    def law(scope):
        pol = core.AgentPolicy(member_id="test-being", scope=tuple(scope), source="test")
        v = core.evaluate(ev, c._profile, c.workspace, policy=pol)
        return v.decision, v.rule
    assert law([]) == ("deny", "mrh.repo"), law([])
    assert law(["sage/instances/test-being"]) == ("deny", "mrh.repo")
    assert law(["SAGE"]) == ("deny", "mrh.repo")
    assert law(["dp-web4/web4"]) == ("deny", "mrh.repo")
    assert law(["dp-web4/SAGE"]) == ("allow", ""), law(["dp-web4/SAGE"])


def test_pr_review_body_is_capped():
    from sage.gateway.being_gate_client import pr_review_command, PR_REVIEW_BODY_CAP
    ok = {"repo": "dp-web4/SAGE", "number": "34", "body": "x" * PR_REVIEW_BODY_CAP}
    assert pr_review_command(ok).startswith("gh pr review 34 ")
    try:
        pr_review_command({**ok, "body": "x" * (PR_REVIEW_BODY_CAP + 1)}); assert False
    except ValueError as e:
        assert "cap" in str(e)


def test_no_registry_entry_carries_a_shell_verb():
    """The 'no shell verb' rule as a red test: the registry never carries a command
    argument the being fills; a composed verb builds its line from validated args."""
    from sage.gateway.being_gate_client import _REGISTRY
    assert all(spec["cmd_arg"] is None for spec in _REGISTRY.values()), _REGISTRY
    composed = [k for k, spec in _REGISTRY.items() if spec.get("compose")]
    assert composed == ["pr_review"], composed
    assert all(_REGISTRY[k].get("repo_arg") for k in composed), "a composed outward act is scoped by name"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")
