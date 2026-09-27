"""The held wake and conversation mode (dp, 2026-09-27: "should we speed up the beat cadence?").

Not the timer. Measured on Sprout: 11 of 13 dp turns since 09-25 woke a beat within 0-4.5 min;
2 waited ~31 min because they arrived while a beat ran and decide() armed nothing. Both are
opt-in per instance (cbp-claude's pre-review: fleet-wide, CBP's being `say`s to its seat on 77%
of beats, which would have made a 60 s pause its normal state on a shared GPU)."""
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import arousal, conversations as conv  # noqa: E402

ME = "sprout-being"
ON = {"arousal": {"held_wake": True, "conversation_mode": True, "people": ["dp"]}}


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _home(cfg=ON):
    h = Path(tempfile.mkdtemp(prefix="wake-"))
    (h / "instance.json").write_text(json.dumps(cfg))
    conv.create(h, "dp", title="dp", participants=["dp", ME], writable_by=["dp", ME])
    conv.create(h, "sprout-claude", title="seat", participants=["sprout-claude", ME],
                writable_by=["sprout-claude", ME])
    return h


def _armed(monkeypatch):
    got, marks = [], []
    monkeypatch.setattr(arousal, "_arm_deferred_wake", lambda s, **k: (got.append(s) or {"deferred": True}))
    import sage.gateway.being_join as bj
    monkeypatch.setattr(bj, "write_wake_marker", lambda d, s: marks.append((d, s)))
    return got, marks


def test_a_dp_turn_that_arrived_during_the_beat_gets_its_own_wake(monkeypatch):
    h = _home(); got, marks = _armed(monkeypatch)
    t0 = time.time() - 120
    conv.append(h, "dp", speaker="dp", text="are you there?", ts=_iso(t0 + 60))
    d = arousal.wake_for_late_turns(h, ME, since=t0)
    assert d["late"] == 1 and d["kinds"] == ["dp_turn"] and got == [arousal.REFRACTORY_S]
    assert marks == [("dp wrote while your last beat was running", 0.9)]


def test_off_by_default_nothing_is_armed(monkeypatch):
    h = _home({}); got, marks = _armed(monkeypatch)
    t0 = time.time() - 120
    conv.append(h, "dp", speaker="dp", text="are you there?", ts=_iso(t0 + 60))
    d = arousal.wake_for_late_turns(h, ME, since=t0)
    assert d["armed"] is False and "off" in d["why"] and got == [] and marks == []
    assert arousal.refractory_s(h)[0] == arousal.REFRACTORY_S


def test_a_seat_turn_carries_seat_salience_not_dp(monkeypatch):
    h = _home(); got, marks = _armed(monkeypatch)
    t0 = time.time() - 120
    conv.append(h, "sprout-claude", speaker="sprout-claude", text="a note", ts=_iso(t0 + 60))
    d = arousal.wake_for_late_turns(h, ME, since=t0)
    assert d["kinds"] == ["seat_turn"] and marks[0][1] == arousal.SALIENCE["seat_turn"]


def test_conversing_means_a_person_not_the_seat(monkeypatch):
    """CBP's shape: the being says to its seat every beat. That is not a live exchange."""
    h = _home(); now = time.time()
    conv.append(h, "sprout-claude", speaker=ME, text="done", via="say", ts=_iso(now - 60))
    conv.append(h, "sprout-claude", speaker="sprout-claude", text="thanks", ts=_iso(now - 30))
    assert arousal.conversing(h, now)[0] is False and arousal.refractory_s(h, now)[0] == arousal.REFRACTORY_S
    conv.append(h, "dp", speaker=ME, text="Hi dp.", via="say", ts=_iso(now - 200))
    conv.append(h, "dp", speaker="dp", text="hi!", ts=_iso(now - 100))
    assert arousal.conversing(h, now)[0] is True
    assert arousal.refractory_s(h, now)[0] == arousal.CONVERSING_REFRACTORY_S


def test_the_beat_cap_restores_the_ordinary_pause():
    h = _home(); now = time.time()
    conv.append(h, "dp", speaker=ME, text="Hi dp.", via="say", ts=_iso(now - 200))
    conv.append(h, "dp", speaker="dp", text="hi!", ts=_iso(now - 100))
    (h / "heartbeats.jsonl").write_text("".join(json.dumps({"t0": now - 60 * i}) + "\n"
                                                for i in range(arousal.MAX_BEATS_PER_HOUR)))
    secs, why = arousal.refractory_s(h, now)
    assert secs == arousal.REFRACTORY_S and "cap" in why


def test_an_old_unseen_turn_never_rearms_a_wake_every_beat(monkeypatch):
    h = _home(); got, _ = _armed(monkeypatch)
    conv.append(h, "dp", speaker="dp", text="old words", ts=_iso(time.time() - 3600))
    assert arousal.wake_for_late_turns(h, ME, since=time.time() - 120) == {"late": 0} and got == []


def test_a_turn_the_beat_showed_is_not_late_and_voice_is_left_to_presence(monkeypatch):
    h = _home(); got, _ = _armed(monkeypatch)
    t0 = time.time() - 120
    t = conv.append(h, "dp", speaker="dp", text="hi", ts=_iso(t0 + 5))
    conv.mark_seen(h, ME, "dp", t["seq"])
    conv.create(h, "room", title="room", participants=[ME, "voice"], writable_by=[ME, "voice"])
    conv.append(h, "room", speaker="voice", text="hello?", via="voice", ts=_iso(t0 + 30), enforce_write=False)
    assert arousal.wake_for_late_turns(h, ME, since=t0)["late"] == 0 and got == []


def test_decide_uses_the_short_pause_only_in_a_live_exchange(monkeypatch):
    h = _home(); now = time.time()
    monkeypatch.setattr(arousal, "beat_running", lambda: False)
    monkeypatch.setattr(arousal, "seconds_to_next_beat", lambda: None)
    (h / "heartbeats.jsonl").write_text(json.dumps({"t0": now - 200, "elapsed_s": 80}) + "\n")
    assert not arousal.decide(h, "dp_turn", now=now)["engage"], "not conversing: 8 min pause"
    conv.append(h, "dp", speaker=ME, text="Hi dp.", via="say", ts=_iso(now - 300))
    conv.append(h, "dp", speaker="dp", text="hello", ts=_iso(now - 150))
    assert arousal.decide(h, "dp_turn", now=now)["engage"], "conversing: 120s > 60s pause"


def test_placement_and_unit_override():
    src = open(os.path.join(os.path.dirname(__file__), "..", "arousal.py")).read()
    assert src.index("def wake_for_late_turns") < src.index('if __name__ == "__main__"')
    assert 'os.environ.get("SAGE_HEARTBEAT_UNIT"' in src
    hb = open(os.path.join(os.path.dirname(__file__), "..", "heartbeat.py")).read()
    assert hb.index("wake_for_late_turns(instance, args.member, since=t0)") < \
        hb.index('f.write(json.dumps(record, ensure_ascii=False, default=str)')
