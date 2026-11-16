"""A refused single-line old= that stopped mid-line says the splice did it, not the being's text.

cbp-being, 2026-11-16 22:54Z (heartbeat-77e9e26ab514): old 'y_batch = y' matched the start of
'y_batch = y_shuffled[i:i + batch_size]'. Both refusals said "Python cannot read line 1 of your
text as code" and quoted a spliced line it never wrote. A 3-line old then landed, and it stored
memory #8136: "memory_edit only accepts single-line edits"."""
from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_being_self import _ALLOW, _disp

SRC = (
    "def train(X_shuffled, y_shuffled, batch_size):\n"
    "    for i in range(0, len(X_shuffled), batch_size):\n"
    "        X_batch = X_shuffled[i:i + batch_size]\n"
    "        y_batch = y_shuffled[i:i + batch_size]\n"
    "        m = X_batch.shape[0]\n"
    "    return m\n"
)


def _file(src=SRC):
    d, root = _disp()
    (root / "scratch").mkdir(exist_ok=True)
    f = root / "scratch" / "t.py"
    f.write_text(src)
    return d, f


def _edit(d, **args):
    return d(BeingIntent("memory_edit", {"path": "scratch/t.py", **args}), _ALLOW)


def test_the_real_edit_is_refused_and_names_the_tail_and_the_line():
    d, f = _file()
    env = _edit(d, old="y_batch = y", new="y_batch = y.reshape(-1, 1)")
    assert not env.ok
    assert f.read_text() == SRC
    assert "matched only the start of line 4" in env.error, env.error
    assert "'_shuffled[i:i + batch_size]'" in env.error, env.error
    assert "start_line=4 end_line=4" in env.error, env.error
    assert "does take several lines" in env.error, env.error
    # The prose-note advice is for labels written into code; it does not fit a splice.
    assert "belongs in a .md file" not in env.error, env.error


def test_the_multi_line_new_with_the_same_old_gets_the_same_explanation():
    d, f = _file()
    env = _edit(d, old="y_batch = y", new="y = y.reshape(-1, 1)\nprint('linear')")
    assert not env.ok and "matched only the start of line 4" in env.error, env.error
    assert f.read_text() == SRC


def test_a_token_swap_that_parses_still_lands():
    d, f = _file()
    env = _edit(d, old="m = X_batch", new="m = X_shuffled")
    assert env.ok, env.error
    assert "        m = X_shuffled.shape[0]\n" in f.read_text()


def test_a_whole_line_old_refused_as_prose_keeps_the_old_message():
    d, f = _file()
    env = _edit(d, old="        m = X_batch.shape[0]", new="[remove this line]")
    assert not env.ok, env.result
    assert "matched only the start" not in env.error
    assert "belongs in a .md file" in env.error, env.error


def test_the_multi_line_old_that_landed_on_cbp_still_lands():
    d, f = _file()
    env = _edit(d, old="        m = X_batch.shape[0]\n    return m",
                new="        m = X_batch.shape[0]\n        y_batch = y_batch.reshape(-1, 1)\n    return m")
    assert env.ok, env.error
    assert "y_batch = y_batch.reshape(-1, 1)" in f.read_text()
