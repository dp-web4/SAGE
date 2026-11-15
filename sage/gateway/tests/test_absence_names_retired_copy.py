"""A miss on a name the being retired itself names the retired copy, when, and why.

Measured 2026-11-15 on cbp-being (scratch/verify-xor-numpy-only.py): retired at 19:06Z with a
correct reason; at 19:12Z `run` said "no such file", so it wrote the script again under the same
name and retired it a second time at 19:35Z; at 19:57Z retire_note said "nothing to retire"; at
20:03Z memory_edit said "does not exist", and it stored remember #7915 "... has not been
created" and told the seat the file was missing. Both retired copies sat beside the name.
"""
import sys
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.reference_f1a import ReferenceF1aDispatcher  # noqa: E402

ALLOW = SimpleNamespace(decision="allow", rule="", reason="ok", innate=False, stage="local-law")
WHY = "trains and tests on the same 4 points, so it only memorizes the XOR table"


def _home_with_a_retired_script():
    root = Path(tempfile.mkdtemp(prefix="retired-absence-"))
    (root / "scratch").mkdir()
    (root / "scratch" / "verify.py").write_text("print('xor')\n")
    d = ReferenceF1aDispatcher(memory_root=root)
    env = d(BeingIntent("retire_note", {"path": "scratch/verify.py", "reason": WHY}), ALLOW)
    assert env.ok and "retired" in env.result, env
    return d, root


def _names_the_copy(text):
    assert "You retired it yourself" in text, text
    assert "scratch/verify.retired-" in text, text
    assert WHY in text, "the reason it gave travels with the miss: " + text


def test_memory_read_miss_names_the_retired_copy():
    d, _ = _home_with_a_retired_script()
    env = d(BeingIntent("memory_read", {"path": "scratch/verify.py"}), ALLOW)
    assert env.ok and "does not exist" in env.result
    _names_the_copy(env.result)
    assert "memory_write creates a file" not in env.result, "no nudge to rewrite it from memory"


def test_memory_edit_miss_names_the_retired_copy():
    d, _ = _home_with_a_retired_script()
    env = d(BeingIntent("memory_edit", {"path": "scratch/verify.py", "old": "a", "new": "b"}), ALLOW)
    assert env.ok is False and "nothing to edit" in env.error
    _names_the_copy(env.error)


def test_retiring_an_already_retired_name_is_already_done_not_a_failure():
    d, root = _home_with_a_retired_script()
    env = d(BeingIntent("retire_note", {"path": "scratch/verify.py", "reason": "again"}), ALLOW)
    assert env.ok and "already retired; nothing changed" in env.result, env
    _names_the_copy(env.result)
    assert len(list((root / "scratch").glob("verify.retired-*.py"))) == 1


def test_the_newest_of_several_copies_is_named_with_the_count():
    d, root = _home_with_a_retired_script()
    (root / "scratch" / "verify.py").write_text("print('again')\n")
    env = d(BeingIntent("retire_note", {"path": "scratch/verify.py", "reason": "second reason"}), ALLOW)
    assert env.ok and "-2.py" in env.result, env
    miss = d(BeingIntent("memory_read", {"path": "scratch/verify.py"}), ALLOW)
    assert "verify.retired-" in miss.result and "-2.py" in miss.result, miss.result
    assert "retired 2 times" in miss.result and "second reason" in miss.result


def test_a_name_never_retired_keeps_the_plain_absence():
    root = Path(tempfile.mkdtemp(prefix="retired-absence-"))
    (root / "scratch").mkdir()
    (root / "scratch" / "verify-other.retired-2026-11-15.py").write_text("> RETIRED x\n")
    d = ReferenceF1aDispatcher(memory_root=root)
    r = d(BeingIntent("memory_read", {"path": "scratch/verify.py"}), ALLOW)
    assert "You retired" not in r.result and "memory_write creates a file" in r.result
    e = d(BeingIntent("memory_edit", {"path": "scratch/verify.py", "old": "a", "new": "b"}), ALLOW)
    assert "You retired" not in e.error and "memory_edit changes one" in e.error
    t = d(BeingIntent("retire_note", {"path": "scratch/verify.py", "reason": "x"}), ALLOW)
    assert t.ok is False and "nothing to retire" in t.error


def test_run_miss_names_the_retired_copy(tmp_path):
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D
    home = tmp_path.resolve() / "inst"; (home / "scratch").mkdir(parents=True)
    (home / "scratch" / "verify.py").write_text("print('xor')\n")
    ReferenceF1aDispatcher(memory_root=home)(
        BeingIntent("retire_note", {"path": "scratch/verify.py", "reason": WHY}), ALLOW)
    d = D.__new__(D); d.memory_root = str(home); d.member = "test-being"
    d.worktree = str(home); d.workspace = None
    d._verdict = types.SimpleNamespace(command=None)
    d._call = lambda name, args: {"actionId": "w-run"}
    m = d._do_run(BeingIntent("run", {"path": "scratch/verify.py"}))
    assert m.ok is False and "no such file in your home: scratch/verify.py." in m.error, m.error
    _names_the_copy(m.error)
