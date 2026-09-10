"""Hermetic tests for the society-safety fail-closed boundary of BeingGateClient.

No live hestia gate required: we bypass __init__ and inject fake _core/_mech, so
this exercises the Stage-2 policy in isolation. Runnable under pytest or directly
(`python3 test_being_gate_client.py`).
"""
import os
import sys
import tempfile
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
        def _scope_roots_with_reach(scopes, ws):
            return tuple((s[5:].removesuffix("/**"), s.endswith("/**"))
                         for s in scopes if s.startswith("path:"))
    # reach travels with the root (hestia #1002): pairs, not bare roots
    assert _granted_roots(Core, Pol, "/ws") == (("/tmp/being-home", False), ("~/nope-not-real", False))
    fb = _granted_roots(object(), Pol, "/ws")                                  # fallback parser
    assert fb[0][0].endswith("/tmp/being-home") and fb[0][1] is False
    class PolRec: scope = ("path:/tmp/tree/**",)
    assert _granted_roots(object(), PolRec, "/ws") == (("/tmp/tree", True),), "the /** spelling is reach"
    assert _granted_roots(Core, None, "/ws") == () and GatewayVerdict("allow").granted == ()


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


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
        "python3 -m pytest -q -c /dev/null --rootdir=/tmp/being-wt "
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
        ("--bind /tmp/wt /tmp/wt", "its own worktree is the ONLY writable path"),
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
    test), and reads what that code could reach. The report is written INSIDE the worktree
    because that is the one writable path; everything else it reaches must fail.

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
open(os.path.join({wt!r}, "probe.json"), "w").write(json.dumps(r))
''')
    open(os.path.join(suite_dir, "test_probe.py"), "w").write("def test_ok():\n    assert True\n")

    cmd = check_command({"target": "gateway"}, {"worktree": wt})
    env = dict(environ, **{canary: "planted-in-the-seat-env"})
    try:
        r = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=120, env=env)
        assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]     # pytest ran, in the sandbox
        # The worktree is under /tmp on purpose: the first cut of the sandbox mounted
        # --tmpfs /tmp AFTER the worktree bind and masked it — pytest collected nothing
        # and this file was never written. Mount order is part of what is measured.
        probe = json.load(open(os.path.join(wt, "probe.json")))
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



# -- pr_amend: a review that requests changes must be answerable -----------------------
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
