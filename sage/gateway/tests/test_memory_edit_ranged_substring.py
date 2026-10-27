"""SAGE #417: a substring old with a range is located within the range, not compared with the whole of it.

cbp-being, 2026-10-10 02:25/02:27Z: line 5 held 'w_true.reshape(1, -1)' twice. The no-range refusal
said to add the range and keep old as a check; the range branch then said the lines "are not the
text you gave". Neither remedy could work, and the being journaled a mismatch that was not one."""
from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_being_self import _ALLOW, _disp

LINE5 = "Fix: w_true.reshape(1, -1) was wrong; it should be w_true.reshape(1, -1)\n"


def _file(lines):
    d, root = _disp()
    (root / "scratch").mkdir(exist_ok=True)
    f = root / "scratch" / "t.md"
    f.write_text("".join(lines))
    return d, f


def _edit(d, **args):
    return d(BeingIntent("memory_edit", {"path": "scratch/t.md", **args}), _ALLOW)


def test_a_substring_once_inside_the_range_is_replaced_there():
    d, f = _file(["a\n", "b = w.reshape(1, -1)\n", "c = w.reshape(1, -1)\n"])
    env = _edit(d, old="w.reshape(1, -1)", new="w.reshape(-1, 1)", start_line=3, end_line=3)
    assert env.ok, env.error
    assert f.read_text() == "a\nb = w.reshape(1, -1)\nc = w.reshape(-1, 1)\n"
    assert "1 occurrence inside lines 3-3" in env.result, env.result


def test_twice_inside_one_line_says_so_and_asks_for_the_whole_line():
    d, f = _file(["a\n"] * 4 + [LINE5])
    before = f.read_text()
    env = _edit(d, old="w_true.reshape(1, -1)", new="w_true.reshape(-1, 1)", start_line=5, end_line=5)
    assert not env.ok and "appears 2 times inside line 5" in env.error, env.error
    assert "not the text you gave" not in env.error and "not a mismatch" in env.error
    assert f.read_text() == before


def test_the_no_range_refusal_for_hits_on_one_line_drops_the_remedies_that_cannot_work():
    d, f = _file(["a\n"] * 4 + [LINE5])
    env = _edit(d, old="w_true.reshape(1, -1)", new="w_true.reshape(-1, 1)")
    assert not env.ok and "all on line 5" in env.error, env.error
    assert "neighbouring line in old" not in env.error and "whole of line 5" in env.error


def test_the_whole_line_as_old_still_works():
    d, f = _file(["a\n"] * 4 + [LINE5])
    fixed = "Fix: w_true.reshape(1, -1) was wrong; it should be w_true.reshape(-1, 1)"
    env = _edit(d, old=LINE5.rstrip("\n"), new=fixed, start_line=5, end_line=5)
    assert env.ok, env.error
    assert f.read_text().splitlines()[4] == fixed


def test_a_whole_line_new_with_a_substring_old_is_refused_not_doubled():
    d, f = _file(["x = 1\n", "y = A @ w_true + noise\n"])
    before = f.read_text()
    env = _edit(d, old="y = A @ ", new="y = A @ w_true + noise * 2", start_line=2, end_line=2)
    assert not env.ok and "twice" in env.error, env.error
    assert f.read_text() == before


def test_text_not_in_the_range_is_still_the_mismatch_refusal():
    d, f = _file(["a\n", "b\n"])
    env = _edit(d, old="zzz", new="q", start_line=2, end_line=2)
    assert not env.ok and "not the text you gave as old" in env.error, env.error


def test_an_old_that_holds_a_newline_is_still_an_exact_check_of_the_range():
    # a whole-line claim on the wrong line must not edit wherever that text also occurs (#450's control)
    d, f = _file(["[padding] [x]\n", "[x]\n"])
    before = f.read_text()
    env = _edit(d, old="[x]\n", new="[y]\n", start_line=1, end_line=1)
    assert not env.ok and "not the text you gave as old" in env.error, env.error
    assert f.read_text() == before
