"""The being knows the local clock and the people's usual nights (dp, 2026-09-26, near 2 am).

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
    assert out == "Local time on this machine: Saturday 01:52 (PDT)."


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
    assert out == "Local time on this machine: Saturday 01:52 (PDT)."


def test_the_beat_header_carries_it():
    src = open(os.path.join(os.path.dirname(__file__), "..", "heartbeat.py")).read()
    assert "{local_clock(now, instance_config(instance))}" in src
