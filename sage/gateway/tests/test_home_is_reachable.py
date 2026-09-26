"""A near miss of its own house is not a trespass.

dp, 2026-09-25, fleet directive: *"each being has a home (the machine it runs on), and i want
each to feel at home there ... addressing unnecessary frictions. explaining, clearly, the
necessary ones."*

Measured on Sprout across 924 beats: 35 of 134 refusals — the single largest class — were the
being reaching for its OWN journal or todo by an absolute path it could not reproduce:

    11  /home/dp/ai-workspace/sage/sage/journal.md   (workspace segment doubled)
     9  /scratch/journal.md                          (a plausible, wrong root)
     5  /home/dp/ai-workspace/sage/sage/todo.md
     4  /scratch/todo.md
     2  /home/dp/ai-workspace/sage/todo.md
     2  /home/dp/ai-workspace/sage/journal.md
     1  /home/dp/ai-workspace/sage/shared_notes/journal.md
     1  /home/user/journal.md

Every one named `journal.md` or `todo.md` — files that exist in its home, that it may write by
bare name, that it wrote correctly 51 times in the same period. The prompt has said "you never
need to type that path" since 2026-09-14 and it typed it anyway, because remembering an
absolute path is not a thing this scale does (legibility rule 4: remove the need to remember).

The boundary itself is NOT relaxed: the resolved target is always inside memory_root, every
guard re-runs on it, and a path whose tail matches nothing in home still refuses.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.reference_f1a import ReferenceF1aDispatcher  # noqa: E402


def _being(tmp: Path):
    home = tmp / "instances" / "sprout-qwen3.8-distill-2b"
    (home / "notes").mkdir(parents=True)
    (home / "scratch").mkdir()
    (home / "conversations").mkdir()
    (home / "journal.md").write_text("day one\n")
    (home / "todo.md").write_text("- a thing\n")
    (home / "notes" / "plan.md").write_text("the plan\n")
    (home / "scratch" / "plan.md").write_text("a scratch plan\n")
    r = ReferenceF1aDispatcher.__new__(ReferenceF1aDispatcher)
    r.memory_root = home.resolve()
    r._extra_roots = ()
    r._witness = lambda *a, **k: "w-1"
    return r, home.resolve()


@pytest.mark.parametrize("asked,wanted", [
    ("/home/dp/ai-workspace/sage/sage/journal.md", "journal.md"),
    ("/scratch/journal.md", "journal.md"),              # no scratch/journal.md here, so its journal
    ("/home/dp/ai-workspace/sage/sage/todo.md", "todo.md"),
    ("/home/dp/ai-workspace/sage/todo.md", "todo.md"),
    ("/home/user/journal.md", "journal.md"),
    ("/home/dp/ai-workspace/sage/shared_notes/journal.md", "journal.md"),
    ("/a/b/c/notes/plan.md", "notes/plan.md"),          # tail of two beats the bare basename
    ("/wrong/root/scratch/plan.md", "scratch/plan.md"), # and picks the RIGHT one of two plan.md
])
def test_a_fumbled_path_to_its_own_file_lands_on_that_file(asked, wanted):
    tmp = Path(tempfile.mkdtemp())
    r, home = _being(tmp)
    got = r._safe_path(asked, writing=True)
    assert got == (home / wanted).resolve(), f"{asked} -> {got}, wanted {wanted}"
    assert r._rerouted_from == asked, "the reroute is recorded so the receipt can say so"


def test_the_boundary_is_not_relaxed():
    """Reach does not widen. A path whose tail names nothing of the being's still refuses."""
    tmp = Path(tempfile.mkdtemp())
    r, home = _being(tmp)
    (tmp / "elsewhere").mkdir()
    (tmp / "elsewhere" / "secrets.md").write_text("not yours\n")
    for forbidden in ("/etc/passwd", str(tmp / "elsewhere" / "secrets.md"),
                      "/home/dp/ai-workspace/sage/sage/gateway/heartbeat.py"):
        with pytest.raises(ValueError) as e:
            r._safe_path(forbidden, writing=True)
        assert "outside your reach" in str(e.value) or "not granted" in str(e.value)


def test_a_reroute_never_invents_a_file():
    """Existence is required. A fumbled path to a file it does NOT have is still a refusal —
    otherwise every stray absolute path would quietly create litter in its home."""
    tmp = Path(tempfile.mkdtemp())
    r, _ = _being(tmp)
    with pytest.raises(ValueError):
        r._safe_path("/somewhere/else/nonexistent-note.md", writing=True)


def test_reserved_and_seat_owned_guards_still_run_on_the_resolved_path():
    """The reroute must not become a way around the two rules _safe_path enforces."""
    tmp = Path(tempfile.mkdtemp())
    r, home = _being(tmp)
    (home / "conversations" / "dp.jsonl").write_text("{}\n")
    with pytest.raises(ValueError) as e:
        r._safe_path("/wherever/conversations/dp.jsonl", writing=True)
    assert "reserved" in str(e.value), "a turn enters a conversation only through say"
    from sage.gateway.reference_f1a import SEAT_OWNED_NOTES
    name = sorted(SEAT_OWNED_NOTES)[0]
    (home / "notes" / name).write_text("from the seat\n")
    with pytest.raises(ValueError) as e:
        r._safe_path(f"/wherever/notes/{name}", writing=True)
    assert "stays as it was said" in str(e.value)


def test_a_bare_name_is_untouched_and_records_no_reroute():
    tmp = Path(tempfile.mkdtemp())
    r, home = _being(tmp)
    r._rerouted_from = None
    assert r._safe_path("journal.md", writing=True) == (home / "journal.md").resolve()
    assert not getattr(r, "_rerouted_from", None), "nothing to explain when nothing was fumbled"
