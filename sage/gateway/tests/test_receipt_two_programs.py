"""A .py receipt that says "Python can parse it" also says when the file holds two programs (#287):
a top-level name defined more than once, or more than one `if __name__ == "__main__":` block."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.reference_f1a import _python_status, _two_programs  # noqa: E402

MAIN = 'if __name__ == "__main__":\n    main()\n'


def _status(tmp_path, src, name="x.py"):
    p = tmp_path / name
    p.write_text(src)
    return _python_status(p)


def test_the_held_out_test_shape_names_both_defs(tmp_path):
    # cbp-being 2026-09-30: held_out_test at 123 and 268; the call binds to the later one
    src = ("def held_out_test(a, b, c, d):\n    return 1\n\n"
           "def main():\n    held_out_test(1, 2, 3, 4)\n\n"
           "def held_out_test(a, b, c, d, e):\n    return 2\n\n" + MAIN)
    s = _status(tmp_path, src)
    assert "Python can parse x.py now" in s
    assert "Defined more than once: `held_out_test` at lines 1, 7." in s, s
    assert "whichever definition ran last" in s
    assert "__main__" not in s, "one main block is not reported"


def test_three_versions_with_three_main_blocks(tmp_path):
    # cbp-being 2026-11-16: scratch/xor_numpy_only.py held v1, v2, v3, each with its own main
    v = "class MLP:\n    pass\n\ndef main():\n    MLP()\n\n" + MAIN + "\n"
    s = _status(tmp_path, v * 3)
    assert 'It has 3 `if __name__ == "__main__":` blocks (lines 7, 16, 25)' in s, s
    assert "the block at line 7 runs first" in s and "An edit below line 7" in s
    assert "`MLP` at lines 1, 10, 19; `main` at lines 4, 13, 22" in s, s


def test_a_clean_file_reads_as_before(tmp_path):
    s = _status(tmp_path, "def f():\n    return 1\n\n" + MAIN)
    assert s == " Python can parse x.py now. That is not the same as running it."


def test_unparseable_and_non_python_are_unchanged(tmp_path):
    assert "cannot parse" in _status(tmp_path, "def f(:\n")
    assert _status(tmp_path, "def f(): pass\ndef f(): pass\n", name="x.txt") == ""
    assert _two_programs("def f(:\n") == ""


def test_nested_and_other_guards_do_not_count():
    src = ("def f():\n    def g(): pass\n    def g(): pass\n\n"
           "class C:\n    def m(self): pass\n    def m(self): pass\n\n"
           "if __name__ == 'x':\n    pass\n" + MAIN)
    assert _two_programs(src) == ""


def test_many_duplicate_names_are_bounded():
    src = "".join(f"def f{i}(): pass\ndef f{i}(): pass\n" for i in range(5))
    s = _two_programs(src)
    assert "`f0`" in s and "`f2`" in s and "`f3`" not in s and "(2 more names too)" in s, s
