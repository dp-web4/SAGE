"""The run receipt names the version of the file that RAN, not the one on disk after it.

sprout's review of SAGE #224: the sha was taken after run_child returned. A run can outlast a
beat. If the being edited the file mid-run, the receipt would name the new version as the one
that ran, and the heartbeat would call never-run code "unchanged since that run". That is the
"fix applied" illusion #224 exists to remove, produced by the measurement itself.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seat_run_requests.py"
_spec = importlib.util.spec_from_file_location("seat_run_requests", _SCRIPT)
srr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srr)


def test_an_edit_during_the_run_does_not_become_the_version_that_ran(tmp_path, monkeypatch):
    inst = tmp_path / "home"
    inst.mkdir()
    target = inst / "a.py"
    target.write_text("print('the version that runs')\n")
    before = hashlib.sha256(target.read_bytes()).hexdigest()[:12]

    def edits_mid_run(argv, cwd, timeout, env):
        target.write_text("print('written while it ran')\n")     # the being's memory_edit
        return 1, "", "Traceback ...\n", False

    said = []
    monkeypatch.setattr(srr, "_instance", lambda: inst)
    monkeypatch.setattr(srr, "bind", lambda *a, **k: [])
    monkeypatch.setattr(srr, "run_child", edits_mid_run)
    monkeypatch.setattr(srr, "_say", said.append)
    srr.cmd_run(argparse.Namespace(path="a.py", seq=None, gpu=False, gpu_anyway=False, timeout=10))

    after = hashlib.sha256(target.read_bytes()).hexdigest()[:12]
    assert before != after
    first = said[0].splitlines()[0]
    assert f"I ran a.py (sha {before})" in first, first
    assert after not in first
