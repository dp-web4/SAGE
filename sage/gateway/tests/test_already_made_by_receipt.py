"""memory_edit: a retried fix the being's own earlier edit already made is "already in place" (#763),
however short and however indented it is sent.

cbp-being, 2026-11-17: `    return (sigmoid(z) > 0.5).astype(int)` landed at 10:44:36; at 10:47:46 it sent the
same fix three times as old="return sigmoid(z)" new="return (sigmoid(z) > 0.5).astype(int)" (37 chars, no
indent). The length-and-whole-line guess missed it and each retry read "that text is not in the file"."""
import json
from pathlib import Path

from sage.gateway.being_gate_client import BeingIntent
from sage.gateway import reference_f1a as rf
from sage.gateway.tests.test_reference_f1a import _ALLOW, _disp

SRC = ("import numpy as np\n\ndef sigmoid(z):\n    return 1 / (1 + np.exp(-z))\n\n"
       "def predict_lr(X, w):\n    z = X @ w\n    return sigmoid(z)\n")
OLD, NEW = "return sigmoid(z)", "return (sigmoid(z) > 0.5).astype(int)"


def _edit(d, old, new, path="scratch/xor_pure_numpy.py"):
    return d(BeingIntent("memory_edit", {"path": path, "old": old, "new": new}), _ALLOW)


def _setup():
    d, root = _disp()
    d(BeingIntent("memory_write", {"path": "scratch/xor_pure_numpy.py", "content": SRC}), _ALLOW)
    return d, Path(root)


def test_a_retry_in_the_same_beat_is_already_in_place():
    d, home = _setup()
    f = home / "scratch" / "xor_pure_numpy.py"
    assert _edit(d, "    " + OLD, "    " + NEW).ok
    before = f.read_bytes()
    r = _edit(d, OLD, NEW)                     # unindented, 37 chars: the #763 shape
    assert r.ok, r.error
    assert r.result.startswith("already in place; nothing changed. Your memory_edit of "
                               "'scratch/xor_pure_numpy.py' earlier in this beat made this change"), r.result
    assert "on line 8" in r.result
    assert f.read_bytes() == before


def test_a_retry_in_a_later_beat_is_found_in_the_beat_records():
    d, home = _setup()
    f = home / "scratch" / "xor_pure_numpy.py"
    f.write_text(SRC.replace("    " + OLD, "    " + NEW))
    beat = {"ts": "2099-01-01T10:44:36Z", "explore": {"trace": [
        {"effector": "memory_edit", "ok": True,
         "args": {"path": "scratch/xor_pure_numpy.py", "old": "def predict_lr(X, w):\n    z = X @ w\n    " + OLD,
                  "new": "def predict_lr(X, w):\n    z = X @ w\n    " + NEW}}]}}
    (home / "heartbeats.jsonl").write_text(json.dumps({"ts": "x"}) + "\n" + json.dumps(beat) + "\n")
    d2, _ = _disp()
    d2.memory_root = home.resolve()
    r = _edit(d2, OLD, NEW)
    assert r.ok and "at 2099-01-01T10:44:36Z made this change" in r.result, (r.error, r.result)


def test_without_the_beings_own_edit_a_short_line_on_disk_is_still_a_failure():
    d, home = _setup()
    f = home / "scratch" / "xor_pure_numpy.py"
    f.write_text(SRC.replace("    " + OLD, "    " + NEW))      # on disk, but not by its edit
    r = _edit(d, OLD, NEW)
    assert not r.ok and "not in" in r.error and "already in place" not in r.error


def test_a_failed_or_other_file_edit_is_not_a_receipt():
    d, home = _setup()
    f = home / "scratch" / "xor_pure_numpy.py"
    f.write_text(SRC.replace("    " + OLD, "    " + NEW))
    beat = {"ts": "2099-01-01T10:44:36Z", "explore": {"trace": [
        {"effector": "memory_edit", "ok": False, "args": {"path": "scratch/xor_pure_numpy.py", "new": NEW}},
        {"effector": "memory_edit", "ok": True, "args": {"path": "scratch/other.py", "new": NEW}}]}}
    (home / "heartbeats.jsonl").write_text(json.dumps(beat) + "\n")
    d2, _ = _disp()
    d2.memory_root = home.resolve()
    r = _edit(d2, OLD, NEW)
    assert not r.ok and "already in place" not in r.error


def test_old_beats_are_not_read():
    d, home = _setup()
    (home / "scratch" / "xor_pure_numpy.py").write_text(SRC.replace("    " + OLD, "    " + NEW))
    beat = {"ts": "2000-01-01T00:00:00Z", "explore": {"trace": [
        {"effector": "memory_edit", "ok": True, "args": {"path": "scratch/xor_pure_numpy.py", "new": NEW}}]}}
    (home / "heartbeats.jsonl").write_text(json.dumps(beat) + "\n")
    assert rf._edits_in_records(home) == []


def test_a_fragment_of_an_earlier_line_is_not_a_match():
    assert rf._lines_within("return x", "    return x\n")
    assert rf._lines_within("a\nb", "  a\n  b\n  c\n")
    assert not rf._lines_within("sigmoid(z)", "    return sigmoid(z)\n"), "a part of a line is not a line"
    assert not rf._lines_within("", "x")


def test_new_found_past_indent_only():
    assert rf._once_past_indent("def f():\n    return 1\n", "return 1")
    assert not rf._once_past_indent("x = return 1\n", "return 1"), "mid-line is not a whole line"
    assert not rf._once_past_indent("    return 10\n", "return 1"), "a prefix of a longer line is not it"
    assert not rf._once_past_indent("return 1\nreturn 1\n", "return 1")
