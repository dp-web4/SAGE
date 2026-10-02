"""Wake continues while there is work; the being can choose to stay awake; the timer is a watchdog
(SAGE #295).

dp, 2026-09-30: "events wake the being, and wake state continues for as long as it has something to
do. the rest timer is a watchdog that wakes it if nothing else has." and "wake indicates an active
beat. there should not be artificial cap on beats, and if the being decides to stay awake
continously because of environment or curiosity, then so be it."

Everything runs against fakes: a fake daemon on an ephemeral loopback port for the activity reports
(never :8760) and a fake systemd for the beat unit and its successor.
"""
import configparser
from pathlib import Path

import pytest

from sage.gateway import activity, arousal
from sage.gateway import heartbeat as hb
from sage.gateway.being_gate_client import BeingIntent, ResultEnvelope
from sage.gateway.being_tool_loop import run_tool_turn
from sage.gateway.tests.fake_systemd import FakeSystemd
from test_activity_reports import _FakeDaemon

SYSTEMD_DIR = Path(__file__).resolve().parent.parent / "systemd"


@pytest.fixture
def daemon(monkeypatch):
    d = _FakeDaemon()
    monkeypatch.setenv("SAGE_ACTIVITY_REPORT", "1")
    monkeypatch.setattr(activity, "ACTIVITY_URL", d.url)
    monkeypatch.setattr(activity, "_reported_active", False)
    yield d
    d.close()


@pytest.fixture
def sysd(monkeypatch):
    f = FakeSystemd(running=True)          # hb.run is called from inside the running beat unit
    monkeypatch.setattr(arousal, "_systemd", f)
    return f


def _beat(beat_id, during=None, stay_awake=None):
    """Stands in for heartbeat.main: the phases, then main's real end-of-beat decision."""
    def main(argv=None):
        hb._BEAT_ID["id"] = beat_id
        hb._BEAT_ID["continuing"] = False
        arousal.claim_pending(beat_id)
        for state, phase in (("wake", "start"), ("wake", "explore"), ("wrap-up", "reflect")):
            hb._phase(state, phase, beat_id)
            if phase == "explore" and during:
                during()
        nxt = arousal.after_beat(stay_awake=stay_awake)
        hb._BEAT_ID["continuing"] = bool(nxt.get("continuing"))
        arousal.release_claim(beat_id)
        return 0
    return main


def test_back_to_back_beats_never_report_rest_in_between(daemon, sysd, monkeypatch, tmp_path):
    # beat 1: dp writes mid-beat. The event is queued and a successor is armed.
    monkeypatch.setattr(hb, "main", _beat("beat-1", during=lambda: arousal.respond(
        tmp_path, "dp_turn", descriptor="dp spoke mid-beat")))
    assert hb.run([]) == 0
    sysd.beat_ends()
    assert sysd.starts == 1, "the next beat started the moment beat 1 ended"
    # beat 2: nothing arrives, the being does not ask. It rests.
    monkeypatch.setattr(hb, "main", _beat("beat-2"))
    assert hb.run([]) == 0
    sysd.beat_ends()
    assert sysd.starts == 1, "nothing pending: no third beat"

    states = daemon.states()
    assert ("wake", "heartbeat:end:continuing") in states
    assert [s for s, _ in states].count("rest") == 1 and states[-1] == ("rest", "heartbeat:end"), states
    handoff = [b for _, b in daemon.reports if b["source"] == "heartbeat:end:continuing"][0]
    assert handoff["beat_id"] == "beat-1" and handoff["ttl_secs"] == activity.HANDOFF_TTL_S


def test_an_event_after_the_end_check_still_starts_the_next_beat(daemon, sysd, tmp_path):
    """The window between the beat's own pending check and the unit's exit: the event sees a
    running beat, is queued, and arms the successor itself."""
    assert arousal.after_beat()["continuing"] is False
    d = arousal.respond(tmp_path, "peer_turn", descriptor="a peer wrote as the beat closed")
    assert d["queued"] is True and d["next"]["armed"] is True
    sysd.beat_ends()
    assert sysd.starts == 1


def test_a_failed_arm_reports_rest_honestly(daemon, monkeypatch):
    """No successor could be armed (no systemd here): the being is not shown awake."""
    monkeypatch.setattr(hb, "main", _beat("beat-x", stay_awake="keep going"))
    assert hb.run([]) == 0            # the conftest's refusing systemd door is in force
    assert daemon.states()[-1] == ("rest", "heartbeat:end")


# --- the being's own choice to stay awake ---------------------------------------------------

class _Client:
    def __init__(self):
        self.dispatched = []

    def dispatch(self, intent):
        self.dispatched.append(intent.effector)
        return ResultEnvelope(ok=True, result="written")


def test_stay_awake_through_the_tool_loop_starts_another_beat(sysd):
    steps = iter([
        {"content": "", "intents": [BeingIntent("memory_write", {"path": "journal.md", "content": "x"}),
                                    BeingIntent("stay_awake", {"reason": "the cup is still moving; I want to watch"})]},
        {"content": "done for this beat", "intents": []},
    ])
    client = _Client()
    res = run_tool_turn(client, lambda convo: next(steps), [{"role": "user", "content": "reflect"}], max_steps=3)
    assert client.dispatched == ["memory_write"], "stay_awake touches nothing: never dispatched"
    assert res.stay_awake == "the cup is still moving; I want to watch"
    assert any(i.effector == "stay_awake" and e.note == "stay_awake" for i, e in res.trace), "recorded in the trace"
    assert res.rested is None, "asking to stay awake does not end the turn"

    reason = hb.stay_awake_reason(None, res)
    d = arousal.after_beat(stay_awake=reason)
    assert d["continuing"] is True and d["stay_awake"] == reason
    sysd.beat_ends()
    assert sysd.starts == 1


def test_stay_awake_is_offered_at_reflect_with_a_required_reason():
    from sage.gateway.being_gate_client import _TOOL_SCHEMAS
    assert "stay_awake" in hb.REFLECT_TOOLS
    desc, props, required = _TOOL_SCHEMAS["stay_awake"]
    assert required == ["reason"] and "reason" in props


def test_a_turn_without_it_asks_for_nothing():
    steps = iter([{"content": "all done", "intents": []}])
    res = run_tool_turn(_Client(), lambda c: next(steps), [{"role": "user", "content": "x"}])
    assert res.stay_awake is None and hb.stay_awake_reason(res, None) is None


# --- the timer is a watchdog ------------------------------------------------------------------

def _timer():
    cp = configparser.ConfigParser(strict=False)
    cp.read_string((SYSTEMD_DIR / "sage-heartbeat.timer.example").read_text())
    return cp


def test_the_watchdog_counts_quiet_from_the_end_of_the_last_beat():
    """OnUnitInactiveSec counts from the unit's last DEACTIVATION, so every beat that runs as the
    unit (timer, event, successor, stay_awake) restarts the 30-minute countdown when it ends.
    OnUnitActiveSec (CBP's installed timer) counts from activation; OnCalendar is a clock."""
    t = _timer()["Timer"]
    assert t["OnUnitInactiveSec"] == "30min"
    assert "OnUnitActiveSec" not in t and "OnCalendar" not in t
    assert t["Unit"] == arousal.UNIT == hb.IDLE_UNIT


def test_every_wake_path_starts_the_unit_the_timer_watches_and_never_touches_the_timer(sysd, tmp_path):
    sysd.running = False
    arousal.respond(tmp_path, "digest", descriptor="the mesh moved")        # a direct start
    arousal.respond(tmp_path, "seat_turn", descriptor="mid-beat")           # a successor
    arousal.after_beat(stay_awake="more")                                   # the being's choice
    starts = [c for c in sysd.calls if "start" in c]
    assert starts and all(c[-1] == arousal.UNIT for c in starts)
    assert not any(arousal.TIMER in " ".join(c) for c in sysd.calls), "the watchdog is never reprogrammed"
