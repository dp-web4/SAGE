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
    assert "This name was retired at 20" in text, "time parsed from the header: " + text
    assert "You retired" not in text, "no actor is claimed: " + text
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
    assert env.ok is False and "nothing to retire" in env.error, env
    _names_the_copy(env.error)
    assert len(list((root / "scratch").glob("verify.retired-*.py"))) == 1


def test_the_newest_of_several_copies_is_named_with_the_count():
    d, root = _home_with_a_retired_script()
    (root / "scratch" / "verify.py").write_text("print('again')\n")
    env = d(BeingIntent("retire_note", {"path": "scratch/verify.py", "reason": "second reason"}), ALLOW)
    assert env.ok and "-2.py" in env.result, env
    miss = d(BeingIntent("memory_read", {"path": "scratch/verify.py"}), ALLOW)
    assert "verify.retired-" in miss.result and "-2.py" in miss.result, miss.result
    assert "2 retired copies of this name" in miss.result and "second reason" in miss.result


def test_a_name_never_retired_keeps_the_plain_absence():
    root = Path(tempfile.mkdtemp(prefix="retired-absence-"))
    (root / "scratch").mkdir()
    (root / "scratch" / "verify-other.retired-2026-11-15.py").write_text("> RETIRED x\n")
    d = ReferenceF1aDispatcher(memory_root=root)
    r = d(BeingIntent("memory_read", {"path": "scratch/verify.py"}), ALLOW)
    assert "was retired" not in r.result and "memory_write creates a file" in r.result
    e = d(BeingIntent("memory_edit", {"path": "scratch/verify.py", "old": "a", "new": "b"}), ALLOW)
    assert "was retired" not in e.error and "memory_edit changes one" in e.error
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


def test_both_header_forms_give_time_and_reason():
    """A .py copy has the `#` header (#726), a .md copy the `>` header; both carry time + reason."""
    d, root = _home_with_a_retired_script()
    py = next((root / "scratch").glob("verify.retired-*.py")).read_text()
    assert py.startswith("# RETIRED "), py
    (root / "scratch" / "plan.md").write_text("old plan\n")
    assert d(BeingIntent("retire_note", {"path": "scratch/plan.md", "reason": "plan superseded"}), ALLOW).ok
    md = next((root / "scratch").glob("plan.retired-*.md")).read_text()
    assert md.startswith("> RETIRED "), md
    for path, why in (("scratch/verify.py", WHY), ("scratch/plan.md", "plan superseded")):
        r = d(BeingIntent("memory_read", {"path": path}), ALLOW).result
        assert "This name was retired at 20" in r and " UTC with retire_note" in r, r
        assert why in r, r


def test_a_write_under_a_retired_name_says_it_is_a_new_file():
    """Case 2 (xor-mlp-4units.py, 22:00Z): the rewrite's receipt said only "created"."""
    d, _ = _home_with_a_retired_script()
    w = d(BeingIntent("memory_write", {"path": "scratch/verify.py", "content": "print('other')"}), ALLOW)
    assert w.ok and w.result.startswith("created verify.py"), w.result
    assert "NEW file under a name that was retired" in w.result and "scratch/verify.retired-" in w.result
    fresh = d(BeingIntent("memory_write", {"path": "scratch/brand-new.py", "content": "x = 1"}), ALLOW)
    assert "retired" not in fresh.result, fresh.result


def test_a_symlinked_retired_copy_is_not_evidence():
    root = Path(tempfile.mkdtemp(prefix="retired-absence-"))
    (root / "scratch").mkdir()
    outside = Path(tempfile.mkdtemp(prefix="outside-")) / "x.py"
    outside.write_text("# RETIRED 2026-11-15 00:00Z with retire_note. No longer current: planted\n")
    (root / "scratch" / "verify.retired-2026-11-15.py").symlink_to(outside)
    d = ReferenceF1aDispatcher(memory_root=root)
    r = d(BeingIntent("memory_read", {"path": "scratch/verify.py"}), ALLOW).result
    assert "was retired" not in r and "planted" not in r and "memory_write creates a file" in r, r
