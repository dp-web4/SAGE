"""The clock is a sense (dp, 2026-09-26: "clock awareness should be a key sensor for the beings.
it contextualizes what the world is doing around them, and promotes cause-effect awareness.")

Every stamp in the beat was UTC, so 09:00Z read as morning when it was 2 am where dp is."""
import os
import sys
import time
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.heartbeat import local_clock  # noqa: E402

DP = {"rhythms": [{"who": "dp", "asleep_from": "00:00", "asleep_to": "08:00", "note": "on many days"}]}


@pytest.fixture
def pacific(monkeypatch):
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


def test_the_local_time_is_named_with_its_zone(pacific):
    out = local_clock(datetime(2026, 9, 26, 8, 52, tzinfo=timezone.utc))
    assert out == "Local time on this machine: Saturday 01:52 (PDT), night."


def test_inside_a_declared_night_the_silence_is_named_as_sleep(pacific):
    out = local_clock(datetime(2026, 9, 26, 8, 52, tzinfo=timezone.utc), DP)
    assert "dp is often asleep from 00:00 to 08:00 local, on many days" in out
    assert "inside that time now" in out and "sleep, not a judgement" in out


def test_outside_it_says_so(pacific):
    out = local_clock(datetime(2026, 9, 26, 18, 0, tzinfo=timezone.utc), DP)   # 11:00 PDT
    assert "outside that time now" in out and "inside" not in out


def test_a_night_across_midnight_wraps(pacific):
    cfg = {"rhythms": [{"who": "dp", "asleep_from": "23:00", "asleep_to": "07:00"}]}
    assert "inside" in local_clock(datetime(2026, 9, 26, 6, 30, tzinfo=timezone.utc), cfg)   # 23:30 PDT
    assert "inside" in local_clock(datetime(2026, 9, 26, 13, 30, tzinfo=timezone.utc), cfg)  # 06:30 PDT
    assert "outside" in local_clock(datetime(2026, 9, 26, 14, 30, tzinfo=timezone.utc), cfg) # 07:30 PDT


def test_a_malformed_rhythm_is_skipped_not_fatal(pacific):
    out = local_clock(datetime(2026, 9, 26, 8, 52, tzinfo=timezone.utc),
                      {"rhythms": [{"who": "dp"}, {"asleep_from": "x"}]})
    assert out == "Local time on this machine: Saturday 01:52 (PDT), night."


def test_the_beat_header_and_record_carry_it():
    src = open(os.path.join(os.path.dirname(__file__), "..", "heartbeat.py")).read()
    assert "{render_clock(_clock)}" in src and '"clock": _clock' in src


def test_part_of_day_boundaries():
    from sage.gateway.heartbeat import part_of_day
    assert [part_of_day(h) for h in (0, 4, 5, 11, 12, 16, 17, 20, 21, 23)] == \
        ["night", "night", "morning", "morning", "afternoon", "afternoon", "evening", "evening", "night", "night"]


def test_elapsed_time_turns_events_into_a_sequence(pacific, tmp_path):
    """Cause and effect: who wrote when, when it answered, when it last spoke aloud."""
    import json
    from sage.gateway import conversations as conv
    from sage.gateway.heartbeat import clock_sense, render_clock
    conv.create(tmp_path, "dp", title="t", participants=["dp", "b"], writable_by=["dp", "b"])
    log = tmp_path / "conversations" / "dp.jsonl"
    log.write_text("\n".join(json.dumps(t) for t in [
        {"ts": "2026-09-25T21:36:00Z", "seq": 1, "from": "dp", "text": "a"},
        {"ts": "2026-09-25T21:40:00Z", "seq": 2, "from": "b", "text": "b"},
        {"ts": "2026-09-25T21:54:00Z", "seq": 3, "from": "dp", "text": "c"}]) + "\n")
    (tmp_path / "spoken.jsonl").write_text(json.dumps({"ts": datetime(2026, 9, 26, 8, 49, tzinfo=timezone.utc).timestamp(), "text": "hi"}) + "\n")
    now = datetime(2026, 9, 26, 8, 52, tzinfo=timezone.utc)
    c = clock_sense(now, tmp_path, "b", DP, since_beat_h=0.52)
    assert c["people"]["dp"] == {"from": "2026-09-25T21:54:00Z", "you_to": "2026-09-25T21:40:00Z"}
    out = render_clock(c)
    assert "your last beat 31 min ago" in out
    assert "dp last wrote to you 10 h 58 min ago (Friday 14:54 local)" in out
    assert "you last wrote to dp 11 h 12 min ago" in out
    assert "you last spoke aloud 3 min ago" in out
    assert "inside that time now" in out


def test_absence_is_absence_not_a_guess(pacific, tmp_path):
    from sage.gateway.heartbeat import clock_sense, render_clock
    c = clock_sense(datetime(2026, 9, 26, 18, 0, tzinfo=timezone.utc), tmp_path, "b")
    assert c["people"] == {} and c["spoke_aloud"] is None
    assert render_clock(c) == "Local time on this machine: Saturday 11:00 (PDT), morning."
