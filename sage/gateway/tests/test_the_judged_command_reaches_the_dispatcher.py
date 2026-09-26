"""The command the law judged reaches the dispatcher, so judged == executed is CHECKED, not assumed.

sprout, reviewing SAGE #218: `GatewayVerdict` had no `command` field, so every dispatcher guard
of the form `judged = getattr(self._verdict, "command", None); if judged is not None and
judged != cmd: refuse` read None on every real verdict and never fired. The tests that "pinned"
it injected `SimpleNamespace(command=...)`, so a mutation deleting the guard went red only
against a fake. It also made `check`'s evidence report `law_bound_command: false` on every run.

These tests go through the REAL path: BeingGateClient.dispatch -> gate() -> the verdict it
builds -> HestiaF1aDispatcher.__call__ -> _do_search. Only the law core and the society
mechanism are stubbed (both allow), because the question is what the verdict carries, not
what the law decides.
"""
import subprocess
import types

from sage.gateway.being_gate_client import BeingGateClient, BeingIntent
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher


def _allowing_core():
    seen = []

    class NormalizedEvent:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def evaluate(ev, profile, workspace, policy=None):
        seen.append(ev.command)
        return types.SimpleNamespace(decision="allow", rule="", reason="ok", innate=False)

    core = types.SimpleNamespace(NormalizedEvent=NormalizedEvent, evaluate=evaluate)
    return core, seen


def _wired(tmp_path):
    wt = tmp_path / "wt"; wt.mkdir()
    for a in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *a], cwd=wt, check=True, capture_output=True)
    (wt / "f.py").write_text("def needle():\n    return 1\n")
    subprocess.run(["git", "add", "-A"], cwd=wt, check=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=wt, check=True, capture_output=True)

    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.worktree = str(wt); d.plugin_id = d.member = "legion-being"; d.memory_root = str(tmp_path)
    d._call = lambda name, args: {"actionId": "act-1"} if name == "hestia_begin_action" else {}

    c = BeingGateClient.__new__(BeingGateClient)
    core, seen = _allowing_core()
    c._core, c._single_gate, c._mech, c._profile = core, None, None, None
    c.member_id, c.worktree, c.memory_root, c.workspace = "legion-being", str(wt), str(tmp_path), str(wt)
    c.host_session_id = "t"
    c._dispatcher = d
    return c, d, seen


def test_the_verdict_carries_the_judged_command_and_the_act_runs(tmp_path, monkeypatch):
    import sage.gateway.being_gate_client as bgc
    monkeypatch.setattr(bgc, "_CONSEQUENTIAL", frozenset())    # no society mechanism in a test
    c, d, seen = _wired(tmp_path)
    env = c.dispatch(BeingIntent("search", {"pattern": "needle"}))
    assert env.ok, env.error
    assert seen and seen[0], "the law was shown a composed command"
    assert d._verdict.command == seen[0], "and the verdict carries exactly that command"


def test_a_dispatcher_that_would_run_a_different_command_refuses(tmp_path, monkeypatch):
    """The guard, live: the gate composes one string, the dispatcher (made to diverge here, the
    way camera's ctx once did) composes another, and the act is refused rather than run."""
    import sage.gateway.being_gate_client as bgc
    monkeypatch.setattr(bgc, "_CONSEQUENTIAL", frozenset())
    c, d, seen = _wired(tmp_path)
    real = bgc.search_command
    monkeypatch.setattr(bgc, "search_command",
                        lambda args, ctx=None: real(args, ctx) + " --and -e smuggled"
                        if ctx is not None and "memory_root" not in ctx else real(args, ctx))
    env = c.dispatch(BeingIntent("search", {"pattern": "needle"}))
    assert not env.ok and "not the command this dispatcher would execute" in (env.error or ""), env
