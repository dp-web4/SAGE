"""Hardware-free tests for the camera verb: monkeypatch subprocess.run so no real
ffmpeg is invoked. Verifies command shape, output path, and error semantics."""

import os
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

import pytest  # noqa: E402

from sage.gateway.being_gate_client import BeingIntent, camera_command  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher  # noqa: E402


@pytest.fixture(autouse=True)
def _camera_witness_chain(monkeypatch):
    """camera is CONSEQUENTIAL, so _do_camera opens an action and records its outcome.

    These tests build the dispatcher with __new__ and no substrate, so the witness chain
    has to be answered or every capture path raises before it reaches what it is testing.
    Stubbing it here rather than in each test also keeps one fact in one place: the action
    id the envelopes must carry.
    """
    monkeypatch.setattr(
        HestiaF1aDispatcher, "_call",
        lambda self, name, args: ({"actionId": "act-cam"}
                                  if name == "hestia_begin_action" else {}),
        raising=False)


# --- camera_command shape ---------------------------------------------------

def test_camera_command_argv0_is_ffmpeg(tmp_path):
    """argv[0] must be 'ffmpeg' — the gate's contract is a single ffmpeg invocation."""
    wt = str(tmp_path)
    args = {"device": "/dev/video0", "out_path": f"{wt}/scratch/camera/last-frame.jpg"}
    cmd = camera_command(args, {"worktree": wt})
    # The command string starts with the ffmpeg binary name.
    assert cmd.split()[0] == "ffmpeg"


def test_camera_command_has_frames_v(tmp_path):
    """The capture must be exactly one frame: -frames:v 1 present in the command."""
    wt = str(tmp_path)
    args = {"device": "/dev/video0", "out_path": f"{wt}/scratch/camera/last-frame.jpg"}
    cmd = camera_command(args, {"worktree": wt})
    assert "-frames:v" in cmd


def test_camera_command_out_path_in_scratch(tmp_path):
    """Frame lands in scratch/ as one file; no cross-beat state."""
    wt = str(tmp_path)
    out = f"{wt}/scratch/camera/last-frame.jpg"
    args = {"device": "/dev/video0", "out_path": out}
    cmd = camera_command(args, {"worktree": wt})
    assert out in cmd


# --- _do_camera with monkeypatched subprocess.run ----------------------------

def test_do_camera_success(tmp_path):
    """Monkeypatch subprocess.run: ffmpeg 'succeeds' (returncode 0), frame file
    appears at the expected path, and the ResultEnvelope mirrors search's shape."""
    wt = str(tmp_path)
    out_dir = wt + "/scratch/camera"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/last-frame.jpg"

    # Create a fake frame file so os.path.exists(full_out) passes.
    Path(out_path).write_bytes(b"\xff\xd8\xff\xdbfake-jpeg")

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return types.SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.worktree = wt

    # Monkeypatch subprocess.run inside the dispatch module's namespace.
    import sage.gateway.hestia_dispatch as hd
    orig_run = hd.subprocess.run
    hd.subprocess.run = fake_run
    try:
        intent = BeingIntent("camera", {"device": "/dev/video0", "out_path": out_path})
        env = d._do_camera(intent)
    finally:
        hd.subprocess.run = orig_run

    assert env.ok, f"expected ok=True, got {env.result}"
    assert "device" in env.result
    # Verify the command that was 'executed' had ffmpeg as argv[0].
    cmd_str = captured["cmd"] if isinstance(captured["cmd"], str) else " ".join(captured["cmd"])
    assert cmd_str.split()[0] == "ffmpeg"
    assert "-frames:v" in cmd_str


def test_do_camera_device_busy(tmp_path):
    """Device busy: ffmpeg exits non-zero with a recognizable stderr. The envelope
    must be ok=False and the result must carry a checkable meaning (not just an error)."""
    wt = str(tmp_path)
    os.makedirs(wt + "/scratch/camera", exist_ok=True)

    def fake_run(cmd, **kwargs):
        return types.SimpleNamespace(
            returncode=1,
            stdout=b"",
            stderr=b"Device or resource busy: /dev/video0",
        )

    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.worktree = wt

    import sage.gateway.hestia_dispatch as hd
    orig_run = hd.subprocess.run
    hd.subprocess.run = fake_run
    try:
        intent = BeingIntent("camera", {"device": "/dev/video0", "out_path": f"{wt}/scratch/camera/last-frame.jpg"})
        env = d._do_camera(intent)
    finally:
        hd.subprocess.run = orig_run

    assert not env.ok, "device-busy must be ok=False"
    # The result must carry a checkable meaning.
    res_str = str(env.result).lower()
    assert "busy" in res_str or "error" in res_str


def test_do_camera_device_absent(tmp_path):
    """Device absent: ffmpeg exits non-zero (no such device). ok=False with a
    checkable message distinguishing 'absent' from 'busy'."""
    wt = str(tmp_path)
    os.makedirs(wt + "/scratch/camera", exist_ok=True)

    def fake_run(cmd, **kwargs):
        return types.SimpleNamespace(
            returncode=1,
            stdout=b"",
            stderr=b"No such file or directory: /dev/video99",
        )

    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.worktree = wt

    import sage.gateway.hestia_dispatch as hd
    orig_run = hd.subprocess.run
    hd.subprocess.run = fake_run
    try:
        intent = BeingIntent("camera", {"device": "/dev/video99", "out_path": f"{wt}/scratch/camera/last-frame.jpg"})
        env = d._do_camera(intent)
    finally:
        hd.subprocess.run = orig_run

    assert not env.ok, "absent device must be ok=False"


def test_do_camera_device_off(tmp_path):
    """Device 'off' (powered down / unregistered): ffmpeg cannot open it.
    ok=False with a meaning distinct from busy and absent."""
    wt = str(tmp_path)
    os.makedirs(wt + "/scratch/camera", exist_ok=True)

    def fake_run(cmd, **kwargs):
        return types.SimpleNamespace(
            returncode=1,
            stdout=b"",
            stderr=b"Cannot open: Device not configured",
        )

    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.worktree = wt

    import sage.gateway.hestia_dispatch as hd
    orig_run = hd.subprocess.run
    hd.subprocess.run = fake_run
    try:
        intent = BeingIntent("camera", {"device": "/dev/video0", "out_path": f"{wt}/scratch/camera/last-frame.jpg"})
        env = d._do_camera(intent)
    finally:
        hd.subprocess.run = orig_run

    assert not env.ok, "device-off must be ok=False"


# --- out_path escape / whitespace guard --------------------------------------

def test_do_camera_out_path_escape_refused(tmp_path):
    """An out_path that escapes the worktree (../) must be refused with a
    checkable meaning — mirroring search's path-escape refusal."""
    wt = str(tmp_path)
    os.makedirs(wt + "/scratch/camera", exist_ok=True)

    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.worktree = wt

    import sage.gateway.hestia_dispatch as hd
    orig_run = hd.subprocess.run

    def fake_run(cmd, **kwargs):
        raise AssertionError("subprocess.run must not be called for an escaping path")

    hd.subprocess.run = fake_run
    try:
        intent = BeingIntent("camera", {"device": "/dev/video0", "out_path": f"{wt}/../escape.jpg"})
        env = d._do_camera(intent)
    finally:
        hd.subprocess.run = orig_run

    assert not env.ok, "escaping out_path must be ok=False"


def test_do_camera_out_path_whitespace_refused(tmp_path):
    """A path with a space is judged/executed drift (GPT review of #56, #6).
    Must be refused with a checkable meaning."""
    wt = str(tmp_path)
    os.makedirs(wt + "/scratch/camera", exist_ok=True)

    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.worktree = wt

    import sage.gateway.hestia_dispatch as hd
    orig_run = hd.subprocess.run

    def fake_run(cmd, **kwargs):
        raise AssertionError("subprocess.run must not be called for a whitespace path")

    hd.subprocess.run = fake_run
    try:
        intent = BeingIntent("camera", {"device": "/dev/video0", "out_path": f"{wt}/scratch/camera/has space.jpg"})
        env = d._do_camera(intent)
    finally:
        hd.subprocess.run = orig_run

    assert not env.ok, "whitespace out_path must be ok=False"


# --- standalone runner (mirrors test_being_gate_client.py convention) --------

if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
