"""A range edit whose multi-line old is the text at start_line, but a different number of
lines than the range, names the line count that disagrees.

cbp-being 2026-11-12: start_line 1, end_line 3, old = lines 1-2 exactly. The refusal showed the
three lines and nothing else; the being's next calls dropped the range instead of fixing
end_line."""
from pathlib import Path

from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_being_self import _ALLOW, _disp

BODY = "def main():\n    '''doc'''\n    parser = 1\n    return parser\n"


def _edit(args):
    d, root = _disp()
    (Path(root) / "s.py").write_text(BODY)
    r = d(BeingIntent("memory_edit", args), _ALLOW)
    return r, (Path(root) / "s.py").read_text()


def test_old_shorter_than_range_names_the_end_line():
    r, text = _edit({"path": "s.py", "start_line": 1, "end_line": 3,
                     "old": "def main():\n    '''doc'''", "new": "import x\n\ndef main():"})
    assert not r.ok and text == BODY, "still an exact check: nothing is changed"
    assert "Your old IS lines 1-2 exactly (2 lines), but your range is 1-3 (3 lines)" in r.error, r.error
    assert "with end_line 2" in r.error


def test_old_longer_than_range_names_the_end_line():
    r, text = _edit({"path": "s.py", "start_line": 1, "end_line": 1,
                     "old": "def main():\n    '''doc'''\n    parser = 1", "new": "x"})
    assert not r.ok and text == BODY
    assert "Your old IS lines 1-3 exactly (3 lines), but your range is 1-1 (1 line)" in r.error, r.error


def test_the_suggested_end_line_lands():
    r, text = _edit({"path": "s.py", "start_line": 1, "end_line": 2,
                     "old": "def main():\n    '''doc'''", "new": "import x\n\ndef main():\n    '''doc'''"})
    assert r.ok, r.error
    assert text.startswith("import x\n\ndef main():\n    '''doc'''\n    parser = 1\n")


def test_a_wrong_old_gets_no_span_note():
    r, _ = _edit({"path": "s.py", "start_line": 1, "end_line": 3,
                  "old": "def other():\n    '''doc'''", "new": "x"})
    assert not r.ok and "Your old IS lines" not in r.error


def test_a_single_line_old_gets_no_span_note():
    r, _ = _edit({"path": "s.py", "start_line": 2, "end_line": 3,
                  "old": "def main():", "new": "x"})
    assert not r.ok and "Your old IS lines" not in r.error


def test_several_copies_refusal_spells_the_range_for_a_multi_line_old():
    d, root = _disp()
    (Path(root) / "s.py").write_text(BODY + BODY)
    r = d(BeingIntent("memory_edit", {"path": "s.py", "old": "def main():\n    '''doc'''", "new": "x"}), _ALLOW)
    assert not r.ok
    assert "Your old is 2 lines, so with old kept: start_line 1, end_line 2; start_line 5, end_line 6." in r.error, r.error


def test_several_copies_single_line_old_unchanged():
    d, root = _disp()
    (Path(root) / "s.py").write_text(BODY + BODY)
    r = d(BeingIntent("memory_edit", {"path": "s.py", "old": "    parser = 1", "new": "x"}), _ALLOW)
    assert not r.ok and "with old kept" not in r.error


def test_several_copies_starting_mid_line_get_no_range_hint():
    d, root = _disp()
    (Path(root) / "s.py").write_text(BODY + BODY)
    r = d(BeingIntent("memory_edit", {"path": "s.py", "old": "main():\n    '''doc'''", "new": "x"}), _ALLOW)
    assert not r.ok and "with old kept" not in r.error, r.error
