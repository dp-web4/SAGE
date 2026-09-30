"""Metabolic response to world input.

dp, 2026-09-07: "we should have metabolic response to events. beat is default idle state.
world inputs require engagement."

The 30-minute timer had become the only rhythm, so everything that arrived waited an
average of fifteen minutes for attention regardless of what it was. These pin the three
properties that make the response metabolic rather than an interrupt: it is GRADED, it is
REFRACTORY, and it always says WHY.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import arousal  # noqa: E402


def _inst(last_beat_ended_s_ago=None):
    d = Path(tempfile.mkdtemp(prefix="arousal-"))
    if last_beat_ended_s_ago is not None:
        t0 = time.time() - last_beat_ended_s_ago - 100
        (d / "heartbeats.jsonl").write_text(json.dumps({"t0": t0, "elapsed_s": 100}) + "\n")
    return d


def _quiet(monkey_running=False, next_s=3600):
    arousal.beat_running = lambda: monkey_running
    arousal.seconds_to_next_beat = lambda: next_s


def setup_function(_):
    _quiet()
    # respond() writes the REAL wake marker (being_join.write_wake_marker defaults to the
    # live path); the first run of the deferral test stamped the being's next beat with
    # descriptor "t2" (heartbeats.jsonl, 2026-09-13T07:46:30Z). Tests must not touch it.
    from sage.gateway import being_join
    global _real_write_wake_marker
    _real_write_wake_marker = being_join.write_wake_marker
    being_join.write_wake_marker = lambda *a, **k: None


def teardown_function(_):
    # restore, or test_being_join's wake-marker test (which runs after this file) sees a no-op
    from sage.gateway import being_join
    being_join.write_wake_marker = _real_write_wake_marker
    import importlib
    importlib.reload(arousal)


def test_it_is_graded_not_binary():
    """Not everything that arrives deserves ~18 minutes of the only GPU on the machine.
    A seat turn WAKES the being (dp's vision of the beat, 2026-09-12: "a message from you
    or me wakes it immediately to respond"); it sat below the threshold until 2026-09-13,
    and the refractory period is what bounds a chattering seat, not this table. Ambient
    digest does not wake it."""
    inst = _inst(last_beat_ended_s_ago=3600)
    assert arousal.decide(inst, "dp_turn")["engage"] is True
    assert arousal.decide(inst, "peer_turn")["engage"] is True
    assert arousal.decide(inst, "scope_decided")["engage"] is True
    assert arousal.decide(inst, "seat_turn")["engage"] is True

    digest = arousal.decide(inst, "digest")
    assert digest["engage"] is False and "below the engagement threshold" in digest["reason"]
    # an unknown kind is quiet by default, never loud
    unknown = arousal.decide(inst, "something-new")
    assert unknown["engage"] is False and unknown["salience"] < arousal.ENGAGE_AT


def test_it_is_refractory_so_a_burst_is_not_five_beats():
    """Without this, five turns in a minute are five beats: the GPU thrashes and the
    being's attention is shredded across fragments of one exchange."""
    just_finished = _inst(last_beat_ended_s_ago=10)
    d = arousal.decide(just_finished, "dp_turn")
    assert d["engage"] is False
    assert "refractory" in d["reason"]
    assert d["refractory_s_left"] > 0

    rested = _inst(last_beat_ended_s_ago=arousal.REFRACTORY_S + 60)
    assert arousal.decide(rested, "dp_turn")["engage"] is True


def test_it_does_not_race_a_beat_that_is_already_coming():
    inst = _inst(last_beat_ended_s_ago=3600)
    _quiet(next_s=60)
    d = arousal.decide(inst, "dp_turn")
    assert d["engage"] is False and "already due" in d["reason"] and d["next_beat_s"] == 60


def test_a_running_beat_is_not_interrupted():
    inst = _inst(last_beat_ended_s_ago=3600)
    _quiet(monkey_running=True)
    d = arousal.decide(inst, "dp_turn")
    assert d["engage"] is False and "already running" in d["reason"]


def test_every_decision_says_why():
    """A wake policy that cannot say why it declined is indistinguishable from one that is
    broken — the failure this codebase keeps meeting from the other side."""
    inst = _inst(last_beat_ended_s_ago=3600)
    for kind in list(arousal.SALIENCE) + ["unknown-kind"]:
        d = arousal.decide(inst, kind)
        assert d["reason"], f"{kind} decided nothing out loud"
        assert isinstance(d["engage"], bool)
        assert 0.0 <= d["salience"] <= 1.0


def test_no_history_is_not_a_reason_to_refuse():
    """A being that has never beaten has no last-beat time. That must read as 'rested',
    not as 'unknown, therefore no' — a first world input should still land."""
    fresh = _inst(last_beat_ended_s_ago=None)
    assert arousal.decide(fresh, "dp_turn")["engage"] is True


def test_refractory_defers_rather_than_drops():
    """An engage-worthy input inside the refractory window used to wait for the idle
    timer — up to 30 minutes for arriving 3 minutes early. The refractory bounds HOW SOON,
    never WHETHER: the decision carries a deferral for when the window ends, and respond()
    arms exactly one timer for it, with a second input riding the same one."""
    inst = _inst(last_beat_ended_s_ago=100)
    d = arousal.decide(inst, "dp_turn")
    assert d["engage"] is False and "refractory" in d["reason"]
    assert d["deferred_s"] == d["refractory_s_left"] + 1
    assert 0 < d["deferred_s"] <= arousal.REFRACTORY_S
    # nothing engage-unworthy gets deferred: digest still just waits
    assert "deferred_s" not in arousal.decide(inst, "digest")

    import subprocess
    calls = []
    timer_state = {"sub": "waiting"}
    def fake_run(args, **kw):
        if args[:3] == ["systemctl", "--user", "show"]:
            return subprocess.CompletedProcess(args, 0, timer_state["sub"] + "\n", "")
        calls.append(args)
        if len(calls) > 1:
            raise subprocess.CalledProcessError(1, args, stderr="Unit sage-heartbeat-deferred-wake.timer was already loaded or has a fragment file.")
        return subprocess.CompletedProcess(args, 0, "", "")
    real = arousal.subprocess.run
    arousal.subprocess.run = fake_run
    arousal._sh = lambda *a: ""
    try:
        first = arousal.respond(inst, "dp_turn", descriptor="t")
        second = arousal.respond(inst, "seat_turn", descriptor="t2")
    finally:
        arousal.subprocess.run = real
    assert first["deferred"] is True and "already_armed" not in first
    assert second["deferred"] is True and second["already_armed"] is True
    assert all("systemd-run" in c[0] and f"--on-active={d['deferred_s']}s" in c for c in calls)
    # --no-block or the transient service blocks for the whole beat and is never collected
    assert all(c[-1] == arousal.UNIT and c[-2] == "--no-block" for c in calls)


def test_a_fired_deferred_timer_is_not_mistaken_for_an_armed_one():
    """The unit name is fixed, so a pair left over from a wake that already fired collides
    exactly like a pending one. Only a timer that is WAITING is believed; a stale pair is
    cleared and the arm retried, and the result says so."""
    import subprocess
    calls, stops = [], []
    def fake_run(args, **kw):
        if args[:3] == ["systemctl", "--user", "show"]:
            return subprocess.CompletedProcess(args, 0, "running\n", "")   # fired, not waiting
        calls.append(args)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(1, args, stderr="Unit sage-heartbeat-deferred-wake.timer was already loaded or has a fragment file.")
        return subprocess.CompletedProcess(args, 0, "", "")
    real, real_sh = arousal.subprocess.run, arousal._sh
    arousal.subprocess.run = fake_run
    arousal._sh = lambda *a: (stops.append(a), "")[1]
    try:
        d = arousal._arm_deferred_wake(30)
    finally:
        arousal.subprocess.run, arousal._sh = real, real_sh
    assert d["deferred"] is True and d.get("cleared_stale") is True and "already_armed" not in d
    assert len(calls) == 2 and any("stop" in a for a in stops)


def test_the_cli_is_what_the_daemon_calls_and_it_answers_in_json(tmp_path):
    """GPT review of SAGE#81: sage-rs conversations::arouse runs
    `python3 -m sage.gateway.arousal --instance --kind --descriptor` and parses stdout as
    JSON. The entry point was deleted on the nursery branch (723c04d73) and nothing failed.
    This runs the module exactly as the daemon does. --dry-run so no marker or unit."""
    import subprocess, sys as _sys
    repo = Path(__file__).resolve().parents[3]
    p = subprocess.run([_sys.executable, "-m", "sage.gateway.arousal", "--instance", str(tmp_path),
                        "--kind", "dp_turn", "--descriptor", "dp spoke in conversation 'dp'",
                        "--dry-run"], cwd=str(repo), capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    d = json.loads(p.stdout)
    assert d["kind"] == "dp_turn" and "engage" in d and "reason" in d and d["dry_run"] is True
    assert d["descriptor"] == "dp spoke in conversation 'dp'"


def test_a_running_beat_claims_in_flight_delivery_ONLY_BECAUSE_THE_HOOK_EXISTS(tmp_path):
    """INVERTED BY THE 2026-09-18 RECONCILIATION, deliberately.

    GPT's SAGE#81 review was right on main: with no interject hook, a turn posted mid-beat
    is not in the beat that is running, and the decision must not promise seconds. This test
    asserted that. The reconciliation merges the branch that HAS the hook
    (being_tool_loop.run_ollama_tool_turn drains conversations.drain_new_for between steps),
    so the capability is present and the promise is now true.

    The guard the old assertion provided is kept and made honest: the claim is asserted
    TOGETHER WITH the hook it depends on, so removing the hook reds this test rather than
    leaving a decision that lies about delivery."""
    import inspect
    from sage.gateway import being_tool_loop
    src = inspect.getsource(being_tool_loop.run_ollama_tool_turn)
    assert "interject" in src, "the promise below is only true while this hook exists"

    _quiet(monkey_running=True)
    d = arousal.decide(tmp_path, "dp_turn")
    assert d["engage"] is False and d.get("delivered_in_flight") is True
    assert d.get("beat_running") is True
    assert "between steps" in d["reason"]


def test_engage_is_not_started_when_the_wake_cannot_launch(tmp_path, monkeypatch):
    """GPT review of SAGE#81: `started` was True whenever policy said engage, even with no
    systemctl (McNugget runs launchd) or a unit that failed. Three arms: the tool is absent,
    the unit fails, the start succeeds. Only the last may say started."""
    import subprocess as _sp
    _quiet()                                   # idle, no beat due: the policy engages
    calls = []

    def absent(args, **kw):
        if "start" in args:
            raise FileNotFoundError("systemctl")
        return _sp.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(arousal.subprocess, "run", absent)
    d = arousal.respond(tmp_path, "dp_turn", descriptor="dp spoke")
    assert d["engage"] is True and d["started"] is False
    assert "no systemctl" in d["wake_error"] and "next scheduled beat" in d["fallback"]

    def failing(args, **kw):
        calls.append(args)
        return _sp.CompletedProcess(args, 5, "", "Unit sage-heartbeat.service not found.")
    monkeypatch.setattr(arousal.subprocess, "run", failing)
    d = arousal.respond(tmp_path, "dp_turn", descriptor="dp spoke")
    assert d["started"] is False and "exit 5" in d["wake_error"] and "not found" in d["wake_error"]

    monkeypatch.setattr(arousal.subprocess, "run",
                        lambda args, **kw: _sp.CompletedProcess(args, 0, "", ""))
    d = arousal.respond(tmp_path, "dp_turn", descriptor="dp spoke")
    assert d["started"] is True and "wake_error" not in d


# ---- carried from legion/mission-artifact in the 2026-09-18 reconciliation ----


def test_the_cli_entry_point_exists_and_prints_json():
    """THE DAEMON CALLS THIS AS A SUBPROCESS, and nothing in-process would notice its loss.

    723c04d73 rewrote the end of this module and took `main()` and the `__main__` block with
    it. `conversations.rs::arouse()` runs `python3 -m sage.gateway.arousal ...` and parses
    stdout as JSON; with no entry point stdout is empty, so for seventeen hours every turn
    posted through the daemon's /chat or /conversations route was appended and then answered
    `engage: false, reason: "arousal policy unreadable"`. The being was never woken early by
    a dashboard turn. The dp console calls respond() in-process and was unaffected, which is
    exactly why no test and no seat noticed.

    Found by GPT's review of SAGE#81 and reported by cbp-claude. Pinned here so the module
    cannot lose its own entry point again."""
    import json
    import subprocess
    import sys
    import tempfile
    from pathlib import Path
    from sage.gateway import arousal

    assert hasattr(arousal, "main"), "the module must keep a CLI entry point"

    inst = Path(tempfile.mkdtemp(prefix="arousal-cli-"))
    p = subprocess.run([sys.executable, "-m", "sage.gateway.arousal",
                        "--instance", str(inst), "--kind", "digest",
                        "--descriptor", "cli pin"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr[:400]
    d = json.loads(p.stdout)          # the daemon parses stdout as JSON; empty stdout is the bug
    assert d["kind"] == "digest" and d["engage"] is False
    assert d["descriptor"] == "cli pin" and d["reason"]
