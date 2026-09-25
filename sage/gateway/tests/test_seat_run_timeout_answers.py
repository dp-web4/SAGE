"""A run that times out still produces an answer (seq 3755, 2026-09-25).

CPython's TimeoutExpired carries the partial output as bytes even when the run asked for
text, so the answer builder's `head + "\\n" + clipped` raised TypeError and the seat posted
nothing: the being's request stayed unanswered while the seat's console said "timed out".
"""
import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seat_run_requests.py"
_spec = importlib.util.spec_from_file_location("seat_run_requests", _SCRIPT)
srr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srr)

_SLOW = ("import sys, time; print('before the wait', flush=True); "
         "sys.stderr.write('err before\\n'); sys.stderr.flush(); time.sleep(30)")


def test_a_timed_out_run_returns_text_with_its_partial_output(tmp_path):
    rc, out, err, timed = srr.run_child([sys.executable, "-c", _SLOW], str(tmp_path), 2, None)
    assert timed and rc is None
    assert isinstance(out, str) and isinstance(err, str)
    assert "before the wait" in out and "err before" in err


def test_a_finished_run_is_unchanged(tmp_path):
    rc, out, err, timed = srr.run_child([sys.executable, "-c", "print('hi')"], str(tmp_path), 30, None)
    assert (rc, out, err, timed) == (0, "hi\n", "", False)
