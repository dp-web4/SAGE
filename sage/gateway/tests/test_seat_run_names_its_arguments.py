"""The seat's run receipt names the exact arguments the being's script got — including none.

36 of cbp-being's first 77 `request_run`s named flags in their `why` ("--output-dim 5", then
20, 25 and 30 to compare). The runner had no way to pass any, and the receipt said only "I ran
X", so four default-argument runs read as the being's four-way experiment. These tests pin that
flags after `--` reach the child, and that the receipt says which went in, or that none did.
"""
import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seat_run_requests.py"
_spec = importlib.util.spec_from_file_location("seat_run_requests", _SCRIPT)
srr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srr)


def _parse(monkeypatch, *argv):
    seen = {}
    monkeypatch.setattr(srr, "cmd_run", lambda a: seen.setdefault("a", a))
    monkeypatch.setattr(sys, "argv", ["seat_run_requests.py", *argv])
    srr.main()
    return seen["a"]


def test_flags_after_the_separator_go_to_the_script_not_the_runner(monkeypatch):
    a = _parse(monkeypatch, "run", "m.py", "--timeout", "30", "--",
               "--epochs", "10", "--output-dim", "1")
    assert a.timeout == 30
    assert a.script_args == ["--epochs", "10", "--output-dim", "1"]


def test_no_separator_means_no_script_arguments(monkeypatch):
    assert _parse(monkeypatch, "run", "m.py").script_args == []


def test_the_receipt_says_when_no_arguments_went_in():
    line = srr.ran_line("m.py", [])
    assert line.startswith("m.py ") and "no arguments" in line


def test_the_receipt_quotes_the_arguments_exactly():
    line = srr.ran_line("m.py", ["--epochs", "10", "--name", "a b"])
    assert line.startswith("m.py ") and "--epochs 10 --name 'a b'" in line
