"""The seat runs the being's code with CUDA devices hidden, and says only that (SAGE #148).

GPT's review: `CUDA_VISIBLE_DEVICES=""` mitigates the measured PyTorch path, but it is not proof
the code ran on the CPU, so the receipt must say what the seat did. These tests pin both: the
CHILD process really receives the empty variable, and no receipt claims "on the CPU".
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seat_run_requests.py"
_spec = importlib.util.spec_from_file_location("seat_run_requests", _SCRIPT)
srr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srr)

_PROBE = "import os, sys; sys.stdout.write(repr(os.environ.get('CUDA_VISIBLE_DEVICES')))"


def _child_sees(env: dict) -> str:
    return subprocess.run([sys.executable, "-c", _PROBE], env=env, capture_output=True,
                          text=True, timeout=30).stdout


def test_the_child_process_receives_hidden_devices_by_default():
    assert _child_sees(srr.child_env(False)) == "''", "the variable must reach the child, empty"


def test_gpu_leaves_the_seats_own_setting_alone(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")     # a seat that has one set
    assert _child_sees(srr.child_env(True)) == "'0'"
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES")          # and one that has none
    assert _child_sees(srr.child_env(True)) == "None"


def test_the_receipt_claims_what_was_done_not_where_it_ran():
    for where in (srr.WHERE_HIDDEN, srr.WHERE_GPU):
        assert "on the CPU" not in where and "on the GPU" not in where
    assert "CUDA_VISIBLE_DEVICES" in srr.WHERE_HIDDEN, "name the mechanism, so the claim is checkable"
