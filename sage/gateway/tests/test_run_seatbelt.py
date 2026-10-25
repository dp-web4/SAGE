"""`run` on a Mac: the Seatbelt sandbox (dp, 2026-10-18: "we need macos sandbox functionality").

bwrap needs Linux user namespaces; a Mac's equivalent is Seatbelt (sandbox-exec). The behaviour tests in
test_run_verb.py run under it as well (needs_sandbox). These pin what is Seatbelt's own:
  * the command: deny by default, no network, a cleared environment, the home never readable;
  * what Seatbelt cannot do itself and the seat does instead (hestia_dispatch._wait_contained): a run
    past its memory cap, or past its disk allowance, is stopped and told why;
  * a run's HOME/TMPDIR is beside its working directory and is gone afterwards.
Skipped where Seatbelt is not the sandbox `run` uses (every Linux seat).
"""
import glob
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.gateway.being_gate_client import BeingIntent, run_sandbox_kind  # noqa: E402

needs_seatbelt = pytest.mark.skipif(run_sandbox_kind() != "seatbelt", reason="Seatbelt is not run's sandbox here")


def _dispatcher(tmp_path):
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    home = tmp_path.resolve() / "inst"; (home / "scratch").mkdir(parents=True)
    d = D.__new__(D); d.memory_root = str(home); d.member = "sb-being"
    d.worktree = str(home); d.workspace = None
    d._verdict = types.SimpleNamespace(command=None)
    d._call = lambda name, args: {"actionId": "w-run"}
    return d, home


@needs_seatbelt
def test_the_seatbelt_command_denies_by_default_and_never_names_the_home(tmp_path):
    from sage.gateway.being_gate_client import run_command, run_stage_dir, SEATBELT, SUDO, RUN_USER
    wt = tmp_path.resolve() / "wt"; wt.mkdir()
    home = tmp_path.resolve() / "inst"; home.mkdir()
    cmd = run_command({"path": "scratch/e.py"}, {"memory_root": str(home), "member": "b", "worktree": str(wt)})
    stage = os.path.realpath(run_stage_dir("b", ["scratch/e.py"]))
    # as the run user, never the seat's own (the procargs2 leak; see test below)
    assert cmd.startswith(f"{SUDO} -n -u {RUN_USER} {SEATBELT} -p ")
    for part in ("(deny default)", "(deny network*)", "/usr/bin/env -i", f"PYTHONPATH={wt}",
                 f"HOME={stage}.home", f"TMPDIR={stage}.home", f"(subpath \"{wt}\")"):
        assert part in cmd, part
    assert cmd.rstrip().endswith(f"{stage}/e.py"), cmd
    assert str(home) not in cmd, "the being's home is never readable from a run"
    # a worktree that IS the home is not readable either (the same rule as the bwrap form)
    same = run_command({"path": "scratch/e.py"}, {"memory_root": str(home), "member": "b", "worktree": str(home)})
    assert str(home) not in same and "PYTHONPATH" not in same


@needs_seatbelt
def test_other_processes_cannot_be_signalled_from_inside(tmp_path):
    d, home = _dispatcher(tmp_path)
    (home / "scratch" / "sig.py").write_text(
        "import os\n"
        f"try:\n    os.kill({os.getpid()}, 0); print('signal-seat: REACHED')\n"
        "except OSError as e:\n    print('signal-seat: denied', type(e).__name__)\n")
    r = d._do_run(BeingIntent("run", {"path": "scratch/sig.py"}))
    assert r.ok and "signal-seat: denied" in r.result["stdout"], r.result


@needs_seatbelt
def test_the_seats_arguments_and_environment_are_unreadable_from_inside(tmp_path):
    """The leak this design exists for (2026-10-18): Seatbelt does not govern kern.procargs2, and as the
    seat's own user a run read the seat's whole environment. As RUN_USER the kernel refuses it."""
    d, home = _dispatcher(tmp_path)
    (home / "scratch" / "peek.py").write_text(
        "import ctypes, ctypes.util, os\n"
        "libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)\n"
        f"for name, pid in (('seat', {os.getpid()}), ('parent', os.getppid())):\n"
        "    mib = (ctypes.c_int * 3)(1, 49, pid); n = ctypes.c_size_t(1 << 16)\n"
        "    buf = ctypes.create_string_buffer(1 << 16)\n"
        "    ok = libc.sysctl(mib, 3, buf, ctypes.byref(n), None, 0) == 0 and n.value > 0\n"
        "    print(f'procargs2-{name}:', 'REACHED' if ok else 'denied')\n"
        "print('uid:', os.getuid())\n")
    r = d._do_run(BeingIntent("run", {"path": "scratch/peek.py"}))
    assert r.ok, r.error
    out = r.result["stdout"]
    assert "procargs2-seat: denied" in out and "procargs2-parent: denied" in out, out
    assert f"uid: {os.getuid()}" not in out, "the run must not be the seat's own user: " + out


@needs_seatbelt
def test_a_run_past_its_memory_cap_is_stopped_and_told(tmp_path, monkeypatch):
    """macOS ignores RLIMIT_AS, so prlimit --as has no Mac equivalent: the seat watches the run's
    resident memory and stops it past the cap."""
    import sage.gateway.being_gate_client as b
    monkeypatch.setattr(b, "run_mem_cap_bytes", lambda: 200 << 20)
    d, home = _dispatcher(tmp_path)
    (home / "scratch" / "hog.py").write_text(
        "import time\nprint('allocating', flush=True)\n"
        "b = bytearray(600 << 20)\n"
        "for i in range(0, len(b), 4096):\n    b[i] = 1\n"   # touch every page: resident, not just reserved
        "time.sleep(30)\nprint('never')\n")
    r = d._do_run(BeingIntent("run", {"path": "scratch/hog.py"}))
    assert r.ok and r.result["exit"] == -9, r.result
    assert "allocating" in r.result["stdout"] and "never" not in r.result["stdout"]
    assert "more memory than half of this machine's" in r.result["stderr"], r.result


@needs_seatbelt
def test_a_run_past_its_disk_allowance_is_stopped_and_its_files_are_gone(tmp_path, monkeypatch):
    """No sized tmpfs on macOS: the seat measures the run's working dir and HOME together."""
    import sage.gateway.being_gate_client as b
    monkeypatch.setattr(b, "RUN_WORK_BYTES", 4 << 20)
    monkeypatch.setattr(b, "RUN_TMP_BYTES", 4 << 20)
    d, home = _dispatcher(tmp_path)
    (home / "scratch" / "fill.py").write_text(
        "import os, time\nprint('filling', flush=True)\n"
        "for i in range(100):\n"
        "    with open(os.path.join(os.environ['TMPDIR'], f'f{i}'), 'wb') as f:\n"
        "        f.write(os.urandom(1 << 20))\n"
        "    time.sleep(0.1)\n"
        "print('never')\n")
    r = d._do_run(BeingIntent("run", {"path": "scratch/fill.py"}))
    assert r.ok and r.result["exit"] == -9, r.result
    assert "more disk in its working directory than the sandbox allows" in r.result["stderr"], r.result
    assert "never" not in r.result["stdout"]
    left = glob.glob(f"/tmp/sage-run-sb-being-{os.getpid()}-*") + glob.glob(
        f"/private/tmp/sage-run-sb-being-{os.getpid()}-*")
    assert not left, f"no stage, output or run home survives: {left}"
