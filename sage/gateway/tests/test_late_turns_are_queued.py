"""Turns that arrive while a beat runs start the next beat (SAGE #295).

This file was the opt-in HELD WAKE and CONVERSATION MODE (dp, 2026-09-27): a late turn armed a
deferred wake only when `instance.json arousal.held_wake` was on, only at salience >= 0.6, and only
after the refractory pause, 8 min (60 s while "conversing", back to 8 min past 8 beats an hour).
Measured on Sprout: 2 of 13 dp turns since 09-25 waited ~31 min for the timer.

dp, 2026-09-30: "events wake the being, and wake state continues for as long as it has something to
do." So every late turn goes into the pending set, with no opt-in, bar or pause, and the beat's
end (arousal.after_beat) starts the next beat for it. What stays: an old unseen turn never
re-queues a beat every beat, a turn the beat showed is not late, and a heard voice is presence's.
"""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from sage.gateway import arousal, conversations as conv

ME = "sprout-being"


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _home(tmp_path, cfg=None):
    h = tmp_path / "home"
    h.mkdir()
    (h / "instance.json").write_text(json.dumps(cfg or {}))
    conv.create(h, "dp", title="dp", participants=["dp", ME], writable_by=["dp", ME])
    conv.create(h, "sprout-claude", title="seat", participants=["sprout-claude", ME],
                writable_by=["sprout-claude", ME])
    return h


def test_a_late_dp_turn_is_queued_with_no_opt_in(tmp_path):
    h = _home(tmp_path)                                 # no arousal.held_wake anywhere
    t0 = time.time() - 120
    conv.append(h, "dp", speaker="dp", text="are you there?", ts=_iso(t0 + 60))
    d = arousal.wake_for_late_turns(h, ME, since=t0)
    assert d["late"] == 1 and d["kinds"] == ["dp_turn"] and d["queued"] is True
    [e] = arousal.peek_pending()
    assert e["kind"] == "dp_turn" and e["key"].startswith("turn:dp:") and e["salience"] == 0.9


def test_a_late_seat_turn_is_queued_too_at_its_own_recorded_salience(tmp_path):
    h = _home(tmp_path)
    t0 = time.time() - 120
    conv.append(h, "sprout-claude", speaker="sprout-claude", text="a note", ts=_iso(t0 + 60))
    d = arousal.wake_for_late_turns(h, ME, since=t0)
    assert d["kinds"] == ["seat_turn"]
    assert arousal.peek_pending()[0]["salience"] == arousal.SALIENCE["seat_turn"]


def test_the_same_turn_seen_twice_is_one_pending_entry(tmp_path):
    h = _home(tmp_path)
    t0 = time.time() - 120
    conv.append(h, "dp", speaker="dp", text="hello", ts=_iso(t0 + 60))
    arousal.wake_for_late_turns(h, ME, since=t0)
    arousal.wake_for_late_turns(h, ME, since=t0)
    [e] = arousal.peek_pending()
    assert e["count"] == 2


def test_an_old_unseen_turn_never_requeues_a_beat_every_beat(tmp_path):
    h = _home(tmp_path)
    conv.append(h, "dp", speaker="dp", text="old words", ts=_iso(time.time() - 3600))
    assert arousal.wake_for_late_turns(h, ME, since=time.time() - 120) == {"late": 0}
    assert arousal.peek_pending() == []


def test_a_turn_the_beat_showed_is_not_late_and_voice_is_left_to_presence(tmp_path):
    h = _home(tmp_path)
    t0 = time.time() - 120
    t = conv.append(h, "dp", speaker="dp", text="hi", ts=_iso(t0 + 5))
    conv.mark_seen(h, ME, "dp", t["seq"])
    conv.create(h, "room", title="room", participants=[ME, "voice"], writable_by=[ME, "voice"])
    conv.append(h, "room", speaker="voice", text="hello?", via="voice", ts=_iso(t0 + 30), enforce_write=False)
    assert arousal.wake_for_late_turns(h, ME, since=t0)["late"] == 0
    assert arousal.peek_pending() == []


def test_the_conversation_mode_and_its_cap_are_gone():
    src = Path(arousal.__file__).read_text()
    for name in ("conversing(", "CONVERSING_WINDOW_S", "MAX_BEATS_PER_HOUR", "held_wake is off"):
        assert name not in src, name


def test_placement_the_late_scan_and_the_continuation_come_before_the_record():
    here = os.path.dirname(__file__)
    src = open(os.path.join(here, "..", "arousal.py")).read()
    assert src.index("def wake_for_late_turns") < src.index('if __name__ == "__main__"')
    assert "SAGE_HEARTBEAT_UNIT" in src
    hb = open(os.path.join(here, "..", "heartbeat.py")).read()
    write = hb.index('f.write(json.dumps(record, ensure_ascii=False, default=str)')
    assert hb.index("wake_for_late_turns(instance, args.member, since=t0)") < \
        hb.index("_arousal.after_beat(stay_awake=") < write
    assert write < hb.index("_arousal.release_claim(host_session_id)")
