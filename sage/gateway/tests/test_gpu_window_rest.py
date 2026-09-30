"""A beat that rests for a held GPU courtesy window arms a beat for the window's end when work is
pending, and tells the daemon why it rests (SAGE #295/#296; scheme:
shared-context/machines/cbp-gpu-windows.md).

Against fakes only: a fake systemd (no real systemd-run), a fake daemon on an ephemeral port
(never :8760), and the per-test pending set conftest provides.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sage.gateway import activity, arousal, gpu_window
from sage.gateway.tests.test_activity_reports import _FakeDaemon

NOW = 1_790_000_000
REPO = Path(__file__).resolve().parents[3]


def _window(tmp_path, until=NOW + 600, holder="kimi-code", reason="ensemble run"):
    p = tmp_path / "cbp-gpu-window"
    p.write_text(f"holder={holder}\nreason={reason}\nuntil_epoch={until}\n")
    return str(p)


class FakeWindowSystemd:
    """systemd-run for the window timer, as systemd behaves for a fixed transient unit name: the
    first arm creates it, a second while it waits fails "already loaded"."""

    def __init__(self, rc=0):
        self.rc = rc
        self.waiting = False
        self.calls = []

    def __call__(self, args, timeout=10):
        self.calls.append(list(args))
        if args[0] == "systemd-run":
            if self.rc:
                return subprocess.CompletedProcess(args, self.rc, "", "Failed to connect to bus")
            if self.waiting:
                return subprocess.CompletedProcess(
                    args, 1, "", f"Failed to start transient timer unit: Unit {gpu_window.WINDOW_UNIT}.timer "
                                 "was already loaded or has a fragment file.")
            self.waiting = True
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:3] == ["systemctl", "--user", "show"]:
            return subprocess.CompletedProcess(
                args, 0, "ActiveState=active\n" if self.waiting else "ActiveState=inactive\n", "")
        raise AssertionError(f"unexpected systemd call {args}")

    def arms(self):
        return [c for c in self.calls if c[0] == "systemd-run"]


@pytest.fixture
def daemon(monkeypatch):
    d = _FakeDaemon()
    monkeypatch.setenv("SAGE_ACTIVITY_REPORT", "1")
    monkeypatch.setattr(activity, "ACTIVITY_URL", d.url)
    yield d
    d.close()


@pytest.fixture
def fake_systemd(monkeypatch):
    f = FakeWindowSystemd()
    monkeypatch.setattr(arousal, "_systemd", f)
    return f


# --- reading the window ----------------------------------------------------------------------

def test_a_held_window_is_read(tmp_path):
    w = gpu_window.read_window(_window(tmp_path), now=NOW)
    assert w == {"holder": "kimi-code", "reason": "ensemble run", "until_epoch": NOW + 600}


@pytest.mark.parametrize("text", ["", "holder=x\n", "holder=x\nuntil_epoch=soon\n",
                                  f"holder=x\nuntil_epoch={NOW}\n", f"until_epoch={NOW - 1}\n"])
def test_an_expired_or_malformed_window_is_no_window(tmp_path, text):
    p = tmp_path / "w"
    p.write_text(text)
    assert gpu_window.read_window(str(p), now=NOW) is None


def test_no_window_file_is_no_window(tmp_path):
    assert gpu_window.read_window(str(tmp_path / "absent"), now=NOW) is None


# --- (a) pending work wakes at the window's end ----------------------------------------------

def test_pending_events_arm_a_beat_for_the_windows_end(tmp_path, fake_systemd):
    arousal.add_pending("dp_turn", "dp wrote while the window was held")
    d = gpu_window.rest_for_window(gpu_window.read_window(_window(tmp_path), NOW), NOW,
                                   report=lambda *a, **k: True)
    assert d["pending"] == 1 and d["next"]["armed"]
    (cmd,) = fake_systemd.arms()
    assert f"--unit={gpu_window.WINDOW_UNIT}" in cmd
    assert f"--on-active={600 + gpu_window.WAKE_MARGIN_S}s" in cmd
    assert cmd[-5:] == ["systemctl", "--user", "start", "--no-block", arousal.UNIT]
    # nothing was claimed or dropped: the events are still pending for the beat that wakes
    assert [e["kind"] for e in arousal.peek_pending()] == ["dp_turn"]


def test_rests_in_one_window_coalesce_into_one_timer(tmp_path, fake_systemd):
    arousal.add_pending("heard", "words on audio")
    w = gpu_window.read_window(_window(tmp_path), NOW)
    first = gpu_window.rest_for_window(w, NOW, report=lambda *a, **k: True)
    second = gpu_window.rest_for_window(w, NOW + 60, report=lambda *a, **k: True)
    assert first["next"] == {"armed": True, "by": gpu_window.WINDOW_UNIT, "in_secs": 602}
    assert second["next"]["armed"] and second["next"]["already_armed"]
    assert len(fake_systemd.arms()) == 2 and fake_systemd.waiting   # one timer, still waiting


def test_nothing_pending_arms_nothing(tmp_path, fake_systemd):
    d = gpu_window.rest_for_window(gpu_window.read_window(_window(tmp_path), NOW), NOW,
                                   report=lambda *a, **k: True)
    assert d["pending"] == 0 and "next" not in d
    assert fake_systemd.calls == []     # the watchdog timer is the only wake, as before #295


def test_a_failed_arm_says_so_and_keeps_the_events(tmp_path, monkeypatch):
    monkeypatch.setattr(arousal, "_systemd", FakeWindowSystemd(rc=1))
    arousal.add_pending("peer_turn", "a peer wrote")
    d = gpu_window.rest_for_window(gpu_window.read_window(_window(tmp_path), NOW), NOW,
                                   report=lambda *a, **k: True)
    assert d["next"]["armed"] is False and "Failed to connect" in d["next"]["error"]
    assert len(arousal.peek_pending()) == 1


def test_the_tests_own_systemd_door_is_shut_by_default(tmp_path):
    """Without a fake, conftest's SAGE_NO_SYSTEMD refuses the arm: no test reaches real systemd."""
    arousal.add_pending("dp_turn", "x")
    d = gpu_window.rest_for_window(gpu_window.read_window(_window(tmp_path), NOW), NOW,
                                   report=lambda *a, **k: True)
    assert d["next"]["armed"] is False and "SAGE_NO_SYSTEMD" in d["next"]["error"]


# --- (b) the indicator says why --------------------------------------------------------------

def test_the_rest_is_reported_with_the_holder_and_a_ttl_to_the_windows_end(tmp_path, daemon, fake_systemd):
    d = gpu_window.rest_for_window(gpu_window.read_window(_window(tmp_path), NOW), NOW)
    assert d["reported"] is True
    ((path, body),) = daemon.reports
    assert path == "/activity"
    assert body == {"state": "rest", "source": "heartbeat:gpu-window:kimi-code", "ttl_secs": 600}
    # no beat_id: the daemon's beat counter (#298) does not count a rested beat as a beat


def test_a_daemon_that_is_down_costs_the_rest_nothing(tmp_path, monkeypatch, fake_systemd):
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    monkeypatch.setenv("SAGE_ACTIVITY_REPORT", "1")
    monkeypatch.setattr(activity, "ACTIVITY_URL", f"http://127.0.0.1:{port}/activity")
    arousal.add_pending("dp_turn", "x")
    d = gpu_window.rest_for_window(gpu_window.read_window(_window(tmp_path), NOW), NOW)
    assert d["reported"] is False and d["next"]["armed"]


# --- the CLI the script and the unit call ----------------------------------------------------

def test_check_exits_3_while_held_and_logs_why(tmp_path, daemon, fake_systemd, capsys):
    arousal.add_pending("dp_turn", "x")
    rc = gpu_window.main(["check", "--window", _window(tmp_path), "--now", str(NOW)])
    out = capsys.readouterr().out
    assert rc == gpu_window.HELD == 3
    assert "resting: GPU window held by kimi-code until" in out and "(ensemble run)" in out
    assert "1 event(s) pending, a beat is armed for the window's end" in out
    assert daemon.states() == [("rest", "heartbeat:gpu-window:kimi-code")]


def test_check_exits_0_with_no_window_and_does_nothing(tmp_path, daemon, fake_systemd):
    assert gpu_window.main(["check", "--window", str(tmp_path / "absent")]) == 0
    assert gpu_window.main(["check", "--window", _window(tmp_path, until=NOW - 1), "--now", str(NOW)]) == 0
    assert daemon.reports == [] and fake_systemd.calls == []


def test_check_fails_open(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("helper broke")
    monkeypatch.setattr(gpu_window, "rest_for_window", boom)
    assert gpu_window.main(["check", "--window", _window(tmp_path), "--now", str(NOW)]) == 0
    assert gpu_window.main(["check", "--bogus"]) == 0


def _condition(module, window):
    """The unit's ExecCondition line, as /bin/sh runs it (systemd turns `$$?` into `$?`)."""
    env = dict(os.environ, PYTHONPATH=str(REPO))
    return subprocess.run(["/bin/sh", "-c", f"{sys.executable} -m {module} check --window {window}; test $? -ne 3"],
                          cwd=REPO, env=env, capture_output=True, text=True, timeout=60).returncode


def test_the_exec_condition_skips_while_held_and_runs_otherwise(tmp_path):
    held = _window(tmp_path, until=4_000_000_000)
    assert _condition("sage.gateway.gpu_window", held) == 1              # skipped: the beat rests
    assert _condition("sage.gateway.gpu_window", str(tmp_path / "none")) == 0
    # an import-time crash exits 1, which is not 3: the beat runs
    assert _condition("sage.gateway.no_such_helper", held) == 0


def test_the_example_unit_and_the_script_call_the_same_check():
    unit = (REPO / "sage/gateway/systemd/sage-heartbeat.service.example").read_text()
    script = (REPO / "sage/scripts/cbp_heartbeat.sh").read_text()
    assert "-m sage.gateway.gpu_window check; test $$? -ne 3" in unit
    assert "python3 -m sage.gateway.gpu_window check" in script and "[ $? -eq 3 ]" in script
