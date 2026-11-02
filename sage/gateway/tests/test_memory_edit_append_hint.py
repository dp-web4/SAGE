"""memory_edit with path and new but nothing to replace names memory_write (mcnugget-being, 2026-10-26..28).

Over 150 beats its memory_edit succeeded 6 times of 34; 5 failures sent only path + new, and each one was text
to ADD (a journal line, a todo item, a log entry). The refusal listed old / start_line+end_line and never said
that adding is memory_write's job, so the being retried edits that could not express what it meant."""
from pathlib import Path

from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_being_self import _ALLOW, _disp


def _edit(args):
    d, root = _disp()
    (Path(root) / "journal.md").write_text("first\n")
    r = d(BeingIntent("memory_edit", args), _ALLOW)
    return r, (Path(root) / "journal.md").read_text()


def test_path_and_new_with_nothing_to_replace_names_memory_write():
    r, text = _edit({"path": "journal.md", "new": "2026-10-28: a line to add"})
    assert not r.ok and text == "first\n", "nothing is changed"
    assert "memory_write with path 'journal.md'" in r.error and "appends and never replaces" in r.error
    assert "You sent: new, path." in r.error, "the original refusal is still there, whole"


def test_other_incomplete_calls_do_not_get_the_append_hint():
    for args in ({"new": "x"}, {"path": "journal.md"}, {}):
        r, _ = _edit(args)
        assert not r.ok and "memory_write" not in r.error, (args, r.error)


def test_an_ordinary_edit_is_untouched():
    r, text = _edit({"path": "journal.md", "old": "first", "new": "second"})
    assert r.ok and text == "second\n"
