"""A text-mode memory_edit says which line it changed, and which copy when a def is pasted twice.

cbp-being, 2026-11-16 19:02Z: old='da1 = dz2 @ W2.T' matched only in the second of two pasted
`def mlp_xor` blocks (line 313), because the first copy's line 134 already held the new text. The
receipt said "replaced 1 occurrence"; the run crashed at line 134 as before."""
from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_being_self import _ALLOW, _disp

V1 = ("def mlp(X):\n"
      "    da1 = W2.T @ dz2\n"
      "    return da1\n"
      "\n"
      "if __name__ == '__main__':\n"
      "    mlp(1)\n")
V2 = ("def mlp(X):\n"
      "    da1 = dz2 @ W2.T\n"
      "    return da1\n")


def _file(name, body):
    d, root = _disp()
    (root / "scratch").mkdir(exist_ok=True)
    f = root / "scratch" / name
    f.write_text(body)
    return d, f


def _edit(d, name, **args):
    return d(BeingIntent("memory_edit", {"path": f"scratch/{name}", **args}), _ALLOW)


def test_text_mode_names_the_line_and_the_copy():
    d, f = _file("x.py", V1 + "\n" + V2)
    env = _edit(d, "x.py", old="da1 = dz2 @ W2.T", new="da1 = W2.T @ dz2")
    assert env.ok, env.error
    assert "replaced 1 occurrence, on line 9, inside 'mlp' at line 8" in env.result, env.result
    assert "defines mlp 2 times (lines 1, 8)" in env.result, env.result
    assert "below the `if __name__ == \"__main__\":` at line 5" in env.result, env.result
    # reflect sees the first RECORD_RESULT_CHARS of a result; the location must sit inside that
    from sage.gateway.heartbeat import RECORD_RESULT_CHARS
    assert "line 8" in env.result[:RECORD_RESULT_CHARS], env.result[:RECORD_RESULT_CHARS]


def test_a_single_def_gets_the_line_and_no_copy_note():
    d, f = _file("y.py", V2)
    env = _edit(d, "y.py", old="da1 = dz2 @ W2.T", new="da1 = W2.T @ dz2")
    assert env.ok, env.error
    assert "replaced 1 occurrence, on line 2;" in env.result, env.result
    assert "times (lines" not in env.result


def test_two_classes_with_init_are_not_copies():
    body = ("class A:\n    def __init__(self):\n        self.x = 1\n\n"
            "class B:\n    def __init__(self):\n        self.y = 2\n")
    d, f = _file("z.py", body)
    env = _edit(d, "z.py", old="self.y = 2", new="self.y = 3")
    assert env.ok, env.error
    assert "times (lines" not in env.result, env.result


def test_no_guard_note_when_the_changed_copy_is_above_the_guard():
    d, f = _file("g.py", V2 + "\n" + V1)  # copies at lines 1 and 5, guard at line 9
    env = _edit(d, "g.py", old="da1 = dz2 @ W2.T", new="da1 = W2.T @ dz2")
    assert env.ok, env.error
    assert "inside 'mlp' at line 1" in env.result and "__main__" not in env.result, env.result


def test_ranged_edit_names_the_copy_too():
    d, f = _file("r.py", V1 + "\n" + V2)
    env = _edit(d, "r.py", old="    da1 = dz2 @ W2.T", new="    da1 = W2.T @ dz2",
                start_line=9, end_line=9)
    assert env.ok, env.error
    assert "replaced lines 9-9 (1 lines), inside 'mlp' at line 8" in env.result, env.result


def test_a_markdown_file_gets_no_copy_note():
    d, f = _file("n.md", "def a():\n  x\ndef a():\n  y\n")
    env = _edit(d, "n.md", old="  y", new="  z")
    assert env.ok, env.error
    assert "on line 4" in env.result and "times (lines" not in env.result, env.result
