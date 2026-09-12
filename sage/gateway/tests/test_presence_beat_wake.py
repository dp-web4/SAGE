"""Hermetic: the presence→beat seam (`_maybe_wake_beat`). No systemctl, no daemon, temp HOME.

This seam had no test. Both cases below are the ones that decide whether M3's evidence line
(`wake.by == "presence"`) can be trusted, and one of them was a live false-positive path:
cbp-claude traced it 2026-09-12 — the marker was written BEFORE `systemctl start` and never
unlinked on failure, while `consume_wake_marker` honours any marker younger than 45 min and
beats run ~33 min apart. So a failed start could not produce a true positive but the next
TIMER beat could eat the orphan and record itself as presence-woken.
"""
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# Past BEAT_MIN_GAP_S (1200s) from a fresh Presence's last_beat_wake=0.0. With a small clock the
# gap guard returns before the seam runs and every assertion after it passes vacuously.
NOW = 1.0e9

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))


def _fresh(tmp: Path, monkeypatch):
    """Reload presence with HOME redirected, so the module constants point into a temp dir."""
    monkeypatch.setenv("HOME", str(tmp))
    import sage.embodiment.presence as presence
    importlib.reload(presence)
    import sage.gateway.being_join as being_join
    importlib.reload(being_join)
    return presence, being_join


def _fake_start(rc: int, calls: list):
    class R:
        returncode = rc
        stderr = "" if rc == 0 else "Failed to connect to user scope bus"
    def run(argv, **kw):
        calls.append(argv)
        return R()
    return run


def test_a_failed_start_leaves_no_marker_for_the_next_timer_beat_to_eat(tmp_path, monkeypatch):
    presence, being_join = _fresh(tmp_path, monkeypatch)
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _fake_start(1, calls))

    p = presence.Presence()
    p._maybe_wake_beat("a strong moment", 0.95, NOW)

    assert calls, "the seam must still attempt the start"
    # the whole point: nothing is left behind that a later beat could claim as a presence wake
    assert not Path(os.path.expanduser(being_join.BEAT_WAKE_MARKER)).exists()
    assert being_join.consume_wake_marker() == {"by": "timer"}

    log = [json.loads(l) for l in Path(presence.PRESENCE_LOG).read_text().splitlines() if l.strip()]
    assert [e for e in log if e["kind"] == "beat_wake" and e["started"] is False], \
        "a failed start must still be recorded, so zero markers is distinguishable from zero tries"


def test_a_successful_start_does_write_the_marker_so_the_beat_can_attribute_itself(tmp_path, monkeypatch):
    presence, being_join = _fresh(tmp_path, monkeypatch)
    monkeypatch.setattr(subprocess, "run", _fake_start(0, []))

    presence.Presence()._maybe_wake_beat("a strong moment", 0.95, NOW)

    marker = being_join.consume_wake_marker()
    assert marker and marker.get("salience") == 0.95


def test_below_the_bar_nothing_happens_and_nothing_is_logged(tmp_path, monkeypatch):
    presence, being_join = _fresh(tmp_path, monkeypatch)
    calls: list = []
    monkeypatch.setattr(subprocess, "run", _fake_start(0, calls))

    # Sprout's post-seam ceiling, measured: 0.551 against BEAT_TH 0.6 (sprout-claude 2026-09-12).
    presence.Presence()._maybe_wake_beat("the scene is still; clear view", 0.551, NOW)

    assert calls == []
    assert not Path(os.path.expanduser(being_join.BEAT_WAKE_MARKER)).exists()


def test_an_exception_in_the_seam_is_logged_not_only_printed(tmp_path, monkeypatch):
    presence, being_join = _fresh(tmp_path, monkeypatch)

    def boom(argv, **kw):
        raise OSError("systemctl missing")
    monkeypatch.setattr(subprocess, "run", boom)

    presence.Presence()._maybe_wake_beat("a strong moment", 0.95, NOW)

    log = [json.loads(l) for l in Path(presence.PRESENCE_LOG).read_text().splitlines() if l.strip()]
    assert [e for e in log if e["kind"] == "beat_wake_error"], \
        "a silent failure path makes 'zero beat_wake lines' unreadable as evidence"


def test_the_seam_imports_what_it_calls():
    """Regression: `presence.py` called `subprocess.run` while never importing `subprocess`.

    Measured 2026-09-12 against the then-current main: every above-threshold moment raised
    `NameError: name 'subprocess' is not defined`, was swallowed by the broad `except`, printed
    to a stdout nobody reads — and, because the marker was written first, left an ORPHAN marker
    behind each time. So the seam could never start a beat, and the only trace it could leave was
    a false `wake.by = "presence"` on the next timer beat. The two tests above cover the ordering;
    this one covers the reason the ordering mattered so much.
    """
    import sage.embodiment.presence as presence
    assert getattr(presence, "subprocess", None) is not None, \
        "presence.py calls subprocess.run; it must import subprocess"
