"""Every sense event wakes the being (SAGE #295).

dp, 2026-09-30: "a message from me, you, mesh watcher, words detected on audio, motion on video or
imu - all should wake it." and "there should not be artificial cap on beats".

Presence used to gate on the cortex's blended salience (WAKE_TH 0.45, 0.70 with eyes closed, BEAT_TH
0.6 for a beat) and rate-limit (COOLDOWN_S 300 s, HOURLY_CAP 6, BEAT_MIN_GAP_S 20 min). A moment at
0.3 woke nothing. Now an event is what the cortex's own detectors say happened (motion on a live eye,
IMU self-motion, an audio onset, a new object), and each one wakes a beat through
sage.gateway.arousal. The one flood mechanism is descriptor dedup, and it drops nothing.

Folded in from test_presence_ignores_the_state_display (SAGE #291): the daemon's /status (state, ATP)
is never read to decide a wake. Folded in from test_presence_wake_starts_a_beat: the wake marker names
only a beat that was asked for.

All against a fake systemd (sage/gateway/tests/fake_systemd.py); the conftest refuses the real one.
"""
import time
import urllib.request
from pathlib import Path

import pytest

from sage.embodiment import presence as P
from sage.gateway import arousal
from sage.gateway.tests.fake_systemd import FakeSystemd


def _frame(motion=0.0, self_motion="still", onset=False, new_objects=None, salience=0.3,
           descriptor="gentle motion to the left (one eye only); clear view", gaze="open"):
    sal = {"salience": salience, "surprise": 0.1, "novelty": 0.2, "arousal": 0.1, "conflict": 0}
    if new_objects:
        sal["new_objects"] = new_objects
    return {"ts": time.time(), "gaze": gaze, "descriptor": descriptor,
            "cameras": {"0": {"motion": motion}, "1": {"motion": 0.0}},
            "proprioception": {"self_motion": self_motion}, "audio": {"ok": True, "onset": onset},
            "salience": sal, "coherence": 0.8}


@pytest.fixture
def world(monkeypatch):
    sysd = FakeSystemd()
    monkeypatch.setattr(arousal, "_systemd", sysd)
    monkeypatch.setattr(P.Presence, "_heard_size", staticmethod(lambda: 0))
    noticed = []
    monkeypatch.setattr(P, "_wake", lambda d, r, s=None, c=None: noticed.append(d) or
                        {"response": "I noticed that.", "metabolic_state": "wake"})
    p = P.Presence()
    logged = []
    monkeypatch.setattr(p, "_log", lambda ev: logged.append(ev))
    return p, sysd, noticed, logged


def test_the_cortex_detectors_define_an_event_not_salience():
    assert P.sense_events(_frame(motion=0.2)) == ["motion"]
    assert P.sense_events(_frame(self_motion="rotating")) == ["imu"]
    assert P.sense_events(_frame(onset=True)) == ["audio"]
    assert P.sense_events(_frame(new_objects=["cup"])) == ["object"]
    assert P.sense_events(_frame(motion=0.05, salience=0.9)) == [], "a high score with nothing happening is not an event"
    assert P.sense_events(_frame(motion=0.9, gaze="closed")) == [], "closed eyes: the cortex is not sensing"
    stalled = _frame(motion=0.9)
    stalled["cameras"]["0"]["stalled"] = True
    assert P.sense_events(stalled) == [], "a dark eye reports no motion, not motion"


@pytest.mark.parametrize("frame", [
    _frame(motion=0.2, salience=0.3),                       # video motion at 0.3: below every old bar
    _frame(self_motion="moving", salience=0.1,
           descriptor="the scene is still; I'm moving; clear view"),   # IMU
    _frame(onset=True, salience=0.2,
           descriptor="the scene is still — I heard a sound, though nothing I see moved; clear view"),
])
def test_a_sense_event_below_the_old_bars_starts_a_beat(world, frame):
    p, sysd, noticed, logged = world
    d = p.sense(frame, now=time.time())
    assert d["engage"] is True and d["started"] is True and sysd.starts == 1
    assert noticed == [frame["descriptor"]], "between beats, the being still voices it"
    [e] = arousal.peek_pending()
    assert e["kind"] == "sense" and e["salience"] == frame["salience"]["salience"], "recorded, not read"
    assert logged[-1]["kind"] == "noticed" and logged[-1]["beat"]["started"] is True


def test_no_cooldown_no_hourly_cap_n_events_n_beats(world):
    """Twelve distinct events a minute apart, each after the previous beat ended: twelve beats.
    The old limits (300 s cooldown, 6 an hour, 20 min between presence beats) allowed one."""
    p, sysd, _, _ = world
    t = time.time()
    for i in range(12):
        p.sense(_frame(motion=0.2, descriptor=f"motion {i}"), now=t + 60 * i)
        arousal.claim_pending(f"b{i}")
        sysd.beat_ends()
    assert sysd.starts == 12


def test_an_event_mid_beat_is_queued_with_no_noticing_and_starts_the_next_beat(world):
    p, sysd, noticed, logged = world
    sysd.running = True
    d = p.sense(_frame(motion=0.3, descriptor="strong motion to the right"), now=time.time())
    assert d["queued"] is True and noticed == [], "no /chat/raw generation contending with the beat"
    assert logged[-1]["kind"] == "sensed"
    sysd.beat_ends()
    assert sysd.starts == 1, "the next beat started as soon as the running one ended"


def test_a_sustained_identical_event_is_coalesced_and_never_dropped(world):
    p, sysd, _, _ = world
    sysd.running = True
    t = time.time()
    for i in range(30):
        p.sense(_frame(motion=0.3, descriptor="strong motion to the right"), now=t + i)
    [e] = arousal.peek_pending()
    assert e["count"] == 30 and len(sysd.arms) == 1
    # once a beat has claimed it, the same moment persisting is not new work
    arousal.claim_pending("b1")
    p.sense(_frame(motion=0.3, descriptor="strong motion to the right"), now=t + 31)
    assert arousal.peek_pending() == []
    # a quiet frame ends the moment; the same motion again is a new event
    p.sense(_frame(motion=0.0, descriptor="the scene is still; clear view"), now=t + 32)
    p.sense(_frame(motion=0.3, descriptor="strong motion to the right"), now=t + 33)
    assert len(arousal.peek_pending()) == 1


def test_the_daemon_is_not_consulted_to_decide_a_wake(world, monkeypatch):
    """SAGE #291: whatever /status says (state rest, ATP 3%) is not read. The noticing POST goes
    through _wake (faked here); urlopen itself must not be called."""
    p, sysd, _, _ = world
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("presence read the daemon")))
    assert p.sense(_frame(motion=0.2), now=time.time())["started"] is True
    assert not hasattr(P, "LOW_ATP") and not hasattr(p, "_read_energy")


def test_the_marker_names_the_event_and_a_failed_start_keeps_it_pending(world, tmp_path):
    from sage.gateway import being_join
    p, sysd, _, _ = world
    sysd.start_rc = 1
    d = p.sense(_frame(motion=0.2, descriptor="someone walked in"), now=time.time())
    assert d["started"] is False
    assert [e["descriptor"] for e in arousal.peek_pending()] == ["someone walked in"], "nothing lost"
    w = being_join.consume_wake_marker()
    assert w["by"] == "presence" and w["descriptor"] == "someone walked in"


def test_the_gates_are_gone_from_presence():
    src = Path(P.__file__).read_text()
    for name in ("WAKE_TH", "BEAT_TH", "COOLDOWN_S", "HOURLY_CAP", "BEAT_MIN_GAP_S",
                 "HEARD_BEAT_GAP_S", "_should_wake", "_maybe_wake_beat", '"systemctl"'):
        assert name not in src, name
