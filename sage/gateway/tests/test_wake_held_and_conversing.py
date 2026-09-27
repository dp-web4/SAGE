"""The held wake and conversation mode (dp, 2026-09-27: "should we speed up the beat cadence?").

Not the timer. Measured on Sprout: 11 of 13 dp turns since 09-25 woke a beat within 0-4.5 min;
2 waited ~31 min because they arrived while a beat ran, and decide() armed nothing for them.
And in a live exchange the 8-minute refractory is lag, not protection."""
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


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _home():
    h = Path(tempfile.mkdtemp(prefix="wake-"))
    conv.create(h, "dp", title="dp", participants=["dp", ME], writable_by=["dp", ME])
    return h


def _armed(monkeypatch):
    got = []
    monkeypatch.setattr(arousal, "_arm_deferred_wake", lambda s, **k: (got.append(s) or {"deferred": True}))
    import sage.gateway.being_join as bj
    monkeypatch.setattr(bj, "write_wake_marker", lambda d, s: None)
    return got


def test_a_turn_that_arrived_during_the_beat_gets_its_own_wake(monkeypatch):
    h, got = _home(), _armed(monkeypatch)
    t0 = time.time() - 120
    conv.append(h, "dp", speaker="dp", text="are you there?", ts=_iso(t0 + 60))
    d = arousal.wake_for_late_turns(h, ME, since=t0)
    assert d["late"] == 1 and d["from"] == ["dp"] and got == [arousal.REFRACTORY_S]


def test_while_conversing_the_pause_is_short(monkeypatch):
    h, got = _home(), _armed(monkeypatch)
    t0 = time.time() - 120
    conv.append(h, "dp", speaker=ME, text="Hello, I'm here.", via="say", ts=_iso(t0 + 10))
    conv.append(h, "dp", speaker="dp", text="great, how are you?", ts=_iso(t0 + 60))
    d = arousal.wake_for_late_turns(h, ME, since=t0)
    assert got == [arousal.CONVERSING_REFRACTORY_S] and d["refractory"].startswith("conversing")


def test_an_old_unseen_turn_never_rearms_a_wake_every_beat(monkeypatch):
    """The loop guard: a turn from before this beat that was never marked seen (trimmed from
    the window, say) is not 'arrived during the beat'."""
    h, got = _home(), _armed(monkeypatch)
    conv.append(h, "dp", speaker="dp", text="old words", ts=_iso(time.time() - 3600))
    assert arousal.wake_for_late_turns(h, ME, since=time.time() - 120) == {"late": 0} and got == []


def test_a_turn_the_beat_showed_is_not_late(monkeypatch):
    h, got = _home(), _armed(monkeypatch)
    t0 = time.time() - 120
    t = conv.append(h, "dp", speaker="dp", text="hi", ts=_iso(t0 + 5))
    conv.mark_seen(h, ME, "dp", t["seq"])
    assert arousal.wake_for_late_turns(h, ME, since=t0)["late"] == 0 and got == []


def test_decide_uses_the_short_pause_while_conversing(monkeypatch):
    h = _home()
    now = time.time()
    monkeypatch.setattr(arousal, "beat_running", lambda: False)
    monkeypatch.setattr(arousal, "seconds_to_next_beat", lambda: None)
    (h / "heartbeats.jsonl").write_text(json.dumps({"t0": now - 200, "elapsed_s": 80}) + "\n")  # ended 120s ago
    d = arousal.decide(h, "dp_turn", now=now)
    assert not d["engage"] and "refractory" in d["reason"], "not conversing: 8 min pause"
    conv.append(h, "dp", speaker=ME, text="Hi dp.", via="say", ts=_iso(now - 300))
    d = arousal.decide(h, "dp_turn", now=now)
    assert d["engage"], "conversing: 120s > 60s pause, so engage now"


def test_the_heartbeat_arms_it_before_writing_the_record():
    src = open(os.path.join(os.path.dirname(__file__), "..", "heartbeat.py")).read()
    i = src.index("wake_for_late_turns(instance, args.member, since=t0)")
    assert i < src.index('f.write(json.dumps(record, ensure_ascii=False, default=str)')
