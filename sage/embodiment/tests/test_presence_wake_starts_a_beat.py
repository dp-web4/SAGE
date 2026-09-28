"""A strong moment starts a beat, and the wake marker names only a beat that was asked for.

From 2026-09-05 to 09-27 `_maybe_wake_beat` wrote the marker, then raised NameError on
`subprocess` (never imported in presence.py); the broad except printed it. No presence wake ever
started a beat, and each left an orphan marker that the next timer beat recorded as its reason."""
import subprocess
import types

from sage.embodiment import presence as P
from sage.gateway import being_join


def _presence(monkeypatch):
    monkeypatch.setattr(P.Presence, "_heard_size", staticmethod(lambda: 0))
    p = P.Presence()
    logged = []
    monkeypatch.setattr(p, "_log", lambda ev: logged.append(ev))
    return p, logged


def _fake_run(rc, calls):
    def run(cmd, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=rc, stderr="" if rc == 0 else "unit failed")
    return run


def test_a_strong_moment_starts_the_beat_and_then_marks_it(monkeypatch):
    p, logged = _presence(monkeypatch)
    calls, marks = [], []
    monkeypatch.setattr(subprocess, "run", _fake_run(0, calls))
    monkeypatch.setattr(being_join, "write_wake_marker", lambda d, s: marks.append((d, s)))
    p._maybe_wake_beat("someone walked in", 0.9, now=10_000.0)
    assert calls and calls[0][:4] == ["systemctl", "--user", "start", "--no-block"], "the beat was asked for"
    assert marks == [("someone walked in", 0.9)]
    assert logged and logged[-1]["started"] is True


def test_a_start_that_fails_leaves_no_marker_to_mislabel_the_next_beat(monkeypatch):
    p, logged = _presence(monkeypatch)
    calls, marks = [], []
    monkeypatch.setattr(subprocess, "run", _fake_run(1, calls))
    monkeypatch.setattr(being_join, "write_wake_marker", lambda d, s: marks.append((d, s)))
    p._maybe_wake_beat("someone walked in", 0.9, now=10_000.0)
    assert calls and marks == [], "no beat was started, so no beat may be credited to this moment"
    assert logged[-1]["started"] is False
