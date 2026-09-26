"""judged == run for `game`, on the REAL path (GPT's merge condition for #218, 2026-09-26).

test_the_being_plays pins the game guard by injecting `SimpleNamespace(command=...)` into the
dispatcher, which is the pattern that hid a dead guard until GatewayVerdict carried `command`
(#210 / #222). These go through the real chain: BeingGateClient.dispatch -> gate() -> the
verdict it builds -> HestiaF1aDispatcher.__call__ -> _do_game. Only the law core is stubbed
(it allows and records what it was shown), because the question is what the verdict carries
and what runs, not what the law decides.
"""
import json
import os
import stat
import types

from sage.gateway.being_gate_client import BeingGateClient, BeingIntent, game_command
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher

PROBES = [["ACTION6", 3, 4], ["ACTION1"]]


def _stepper(path, marker):
    """A stand-in stepper that echoes its argv and leaves a marker proving it ran."""
    path.write_text("#!/usr/bin/env python3\nimport sys, json\n"
                    f"open({str(marker)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
                    "print(json.dumps({'argv': sys.argv[1:]}))\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path.resolve())


def _wired(tmp_path, gate_stepper, run_stepper):
    home = tmp_path.resolve() / "home"
    home.mkdir(exist_ok=True)
    seen = []

    class NormalizedEvent:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def evaluate(ev, profile, workspace, policy=None):
        seen.append(ev.command)
        return types.SimpleNamespace(decision="allow", rule="", reason="ok", innate=False)

    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.memory_root, d.game_stepper = str(home), run_stepper
    d.plugin_id = d.member = "legion-being"
    d._call = lambda name, args: {"actionId": "w1"} if name == "hestia_begin_action" else {}

    c = BeingGateClient.__new__(BeingGateClient)
    c._core = types.SimpleNamespace(NormalizedEvent=NormalizedEvent, evaluate=evaluate)
    c._single_gate, c._mech, c._profile = None, None, None
    c.member_id, c.memory_root, c.workspace, c.worktree = "legion-being", str(home), str(home), None
    c.host_session_id, c.game_stepper, c._dispatcher = "t", gate_stepper, d
    return c, d, seen, home


def test_the_verdict_carries_the_judged_game_line_and_exactly_that_line_runs(tmp_path, monkeypatch):
    import sage.gateway.being_gate_client as bgc
    monkeypatch.setattr(bgc, "_CONSEQUENTIAL", frozenset())      # no society mechanism in a test
    marker = tmp_path / "ran.txt"
    step = _stepper(tmp_path / "stepper.py", marker)
    c, d, seen, home = _wired(tmp_path, step, step)
    env = c.dispatch(BeingIntent("game", {"probes": PROBES}))
    assert env.ok, env.error
    expected = game_command({"probes": PROBES}, {"memory_root": str(home), "game_stepper": step})
    assert seen == [expected], "the law was shown the composed game line"
    assert d._verdict.command == expected, "a REAL verdict carries exactly that line"
    assert env.result["argv"] == ["--batch", "ft09", "ACTION6:3:4+ACTION1", "--instance", str(home)]
    assert marker.read_text().split() == env.result["argv"], "and that line is what ran"


def test_a_stepper_only_one_half_knows_is_refused_before_it_runs(tmp_path, monkeypatch):
    """#218's own docstring: 'a stepper only one of them knows is a verb the judged/executed
    guard refuses every time'. On the real path: the gate composes with one stepper, the
    dispatcher would run another. The act is refused and the stepper never runs."""
    import sage.gateway.being_gate_client as bgc
    monkeypatch.setattr(bgc, "_CONSEQUENTIAL", frozenset())
    marker = tmp_path / "ran.txt"
    judged = _stepper(tmp_path / "judged.py", marker)
    other = _stepper(tmp_path / "other.py", marker)
    c, d, seen, _ = _wired(tmp_path, judged, other)
    env = c.dispatch(BeingIntent("game", {"probes": PROBES}))
    assert not env.ok and "not the command this dispatcher would execute" in (env.error or ""), env
    assert seen and judged in seen[0] and other not in seen[0], "the law judged the gate's line"
    assert not marker.exists(), "nothing ran"
