"""memory_edit with an empty 'old' says it was empty (pub-being, 2026-10-31..11-03).

59 of its 94 "memory_edit needs ..." refusals sent path, old and new, with old = "". The refusal answered
"You sent: new, old, path", which lists every argument it asks for, so the being could not see what was
wrong and sent the same call again."""
from pathlib import Path

from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_being_self import _ALLOW, _disp


def _edit(args):
    d, root = _disp()
    (Path(root) / "notes.md").write_text("first\n")
    r = d(BeingIntent("memory_edit", args), _ALLOW)
    return r, (Path(root) / "notes.md").read_text()


def test_an_empty_old_is_named():
    r, text = _edit({"path": "notes.md", "old": "", "new": "a line"})
    assert not r.ok and text == "first\n", "nothing is changed"
    assert "'old' was empty, so there was no text to find." in r.error
    assert "You sent: new, old, path." in r.error, "the original refusal is still there, whole"
    assert "memory_write with path 'notes.md'" in r.error, "the append hint still follows"


def test_an_empty_alias_is_named_too():
    r, _ = _edit({"path": "notes.md", "old_text": "", "new": "a line"})
    assert not r.ok and "'old' was empty" in r.error


def test_a_missing_old_is_not_called_empty():
    r, _ = _edit({"path": "notes.md", "new": "a line"})
    assert not r.ok and "was empty" not in r.error


def test_an_empty_old_with_a_line_range_is_an_ordinary_edit():
    r, text = _edit({"path": "notes.md", "old": "", "start_line": 1, "end_line": 1, "new": "second"})
    assert r.ok and text == "second\n", r.error
