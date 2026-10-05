"""A replace keeps the old copy, and mode='restore' puts it back (legion-being, 2026-09-27..10-04).

Of 537 whole-file replaces, four took a large file to almost nothing (todo.md 143 KB -> 1.1 KB, 48 KB
-> 1.9 KB, 102 KB -> 385 B; a worktree test 90 KB -> 12 B), at least two by mistake. A 100 KB file
cannot be retyped through a 24k window, so the receipt alone could not undo it.
"""
import os
import tempfile
import time
from pathlib import Path

from sage.gateway import reference_f1a as R
from sage.gateway.being_gate_client import BeingIntent


def _disp():
    home = Path(tempfile.mkdtemp(prefix="home-"))
    d = R.ReferenceF1aDispatcher.__new__(R.ReferenceF1aDispatcher)
    d.memory_root = home.resolve()
    d.worktree = None
    d._extra_roots = ()
    d._witness = lambda what: f"w:{what}"
    return d, home


def _w(d, **a):
    return d._do_memory_write(BeingIntent(effector="memory_write", args=a))


def test_replacing_a_large_file_keeps_it_and_says_how_to_undo():
    d, home = _disp()
    big = "- old line\n" * 1000                       # ~11 KB
    (home / "todo.md").write_text(big)
    r = _w(d, path="todo.md", content="- the new short todo", mode="replace")
    assert r.ok and "The previous version" in r.result and "mode='restore'" in r.result, r
    kept = list((home / R.REPLACE_KEEP_DIR).iterdir())
    assert len(kept) == 1 and kept[0].read_text() == big
    assert (home / "todo.md").read_text().startswith("- the new short todo")


def test_restore_puts_back_the_newest_kept_copy_and_keeps_the_one_it_replaces():
    d, home = _disp()
    big = "- v1\n" * 2000
    (home / "todo.md").write_text(big)
    _w(d, path="todo.md", content="- oops", mode="replace")
    r = _w(d, path="todo.md", content="", mode="restore")
    assert r.ok and "RESTORED todo.md" in r.result, r
    assert (home / "todo.md").read_text() == big
    assert len(list((home / R.REPLACE_KEEP_DIR).iterdir())) == 2, "the replaced 'oops' is kept too"


def test_small_files_and_appends_keep_nothing_and_restore_says_why_without_a_copy():
    d, home = _disp()
    (home / "scratch").mkdir()
    (home / "scratch" / "probe.py").write_text("x = 1\n")
    r = _w(d, path="scratch/probe.py", content="x = 2", mode="replace")
    assert r.ok and "previous version" not in r.result
    _w(d, path="journal.md", content="entry")
    assert not (home / R.REPLACE_KEEP_DIR).exists()
    r = _w(d, path="journal.md", content="", mode="restore")
    assert not r.ok and "no kept copy" in r.error


def test_kept_copies_older_than_the_window_are_pruned():
    d, home = _disp()
    kd = home / R.REPLACE_KEEP_DIR
    kd.mkdir(parents=True)
    old = time.strftime("%Y%m%d-%H%M%S", time.gmtime(time.time() - R.REPLACE_KEEP_S - 3600))
    (kd / f"{old}-todo.md").write_text("ancient")
    (home / "todo.md").write_text("y" * 5000)
    _w(d, path="todo.md", content="new", mode="replace")
    names = [x.name for x in kd.iterdir()]
    assert not any(n.startswith(old) for n in names) and len(names) == 1
