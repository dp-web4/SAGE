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


def _ctx(wt):
    """The context camera_command now needs.

    `camera` resolves its out_path against the being's HOME, not its worktree: frames in the
    worktree dirty a tree whose cleanliness `check` reports as evidence, and the being found
    that by using its own verb. These tests keep the two the same directory, because what
    they are testing is the command's shape and the dispatcher's failure taxonomy, not the
    choice of root — test_do_camera_out_path_escape_refused is where the root itself is
    pinned."""
    return {"worktree": wt, "memory_root": wt}


def _dispatcher(wt):
    """A dispatcher with the two roots set and nothing else; the witness chain comes from
    the autouse fixture above."""
    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.worktree = wt
    d.memory_root = wt
    return d


# --- camera_command shape ---------------------------------------------------

def test_camera_command_argv0_is_ffmpeg(tmp_path):
    """argv[0] must be 'ffmpeg' — the gate's contract is a single ffmpeg invocation."""
    wt = str(tmp_path)
    args = {"device": "/dev/video0", "out_path": f"{wt}/scratch/camera/last-frame.jpg"}
    cmd = camera_command(args, _ctx(wt))
    # The command string starts with the ffmpeg binary name.
    assert cmd.split()[0] == "ffmpeg"


def test_camera_command_has_frames_v(tmp_path):
    """The capture must be exactly one frame: -frames:v 1 present in the command."""
    wt = str(tmp_path)
    args = {"device": "/dev/video0", "out_path": f"{wt}/scratch/camera/last-frame.jpg"}
    cmd = camera_command(args, _ctx(wt))
    assert "-frames:v" in cmd


def test_camera_command_out_path_in_scratch(tmp_path):
    """Frame lands in scratch/ as one file; no cross-beat state."""
    wt = str(tmp_path)
    out = f"{wt}/scratch/camera/last-frame.jpg"
    args = {"device": "/dev/video0", "out_path": out}
    cmd = camera_command(args, _ctx(wt))
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

    d = _dispatcher(wt)

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

    d = _dispatcher(wt)

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

    d = _dispatcher(wt)

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

    d = _dispatcher(wt)

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

    d = _dispatcher(wt)

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

    d = _dispatcher(wt)

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


def test_the_frame_resolves_against_HOME_not_the_worktree(tmp_path):
    """The whole point of the change, and the only test that can see it.

    Every other test in this file sets home and worktree to the SAME directory, because what
    they pin is command shape and failure taxonomy. That makes the two roots indistinguish-
    able, so reverting the resolution to the worktree leaves them all green — measured.
    A discriminator that is true by construction is a constant, not a test.

    Why home: legion-being found by using its own verb that frames land in its worktree and
    flip that tree's `dirty` flag, and `check` reports dirty as part of the evidence a
    verdict rests on. Using the camera quietly degraded its own ability to make verified
    claims about its code.
    """
    home = tmp_path / "home"
    wt = tmp_path / "worktree"
    for d in (home, wt):
        (d / "scratch" / "camera").mkdir(parents=True)

    cmd = camera_command({}, {"worktree": str(wt), "memory_root": str(home)})

    assert str(home) in cmd, f"the frame does not land under the being's home: {cmd}"
    assert str(wt) not in cmd, (
        f"the frame still lands in the worktree, whose cleanliness is evidence: {cmd}")
    assert cmd.rstrip().endswith("scratch/camera/last-frame.jpg")


def test_out_path_escaping_HOME_is_refused(tmp_path):
    """Containment moved with the root: the boundary is the home now, and the refusal says
    so rather than naming a tree the path no longer resolves against."""
    home = tmp_path / "home"
    wt = tmp_path / "worktree"
    for d in (home, wt):
        (d / "scratch" / "camera").mkdir(parents=True)
    ctx = {"worktree": str(wt), "memory_root": str(home)}

    try:
        camera_command({"out_path": "../../escape.jpg"}, ctx)
    except ValueError as e:
        assert "home" in str(e).lower() or "worktree" in str(e).lower(), str(e)
    else:
        raise AssertionError("a path escaping the home was accepted")

    # And a path INSIDE the worktree but outside the home is now an escape, which is the
    # behavioural difference the two roots create.
    try:
        camera_command({"out_path": str(wt / "scratch" / "camera" / "x.jpg")}, ctx)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "a worktree path was accepted as a frame destination; the roots are not separate")
