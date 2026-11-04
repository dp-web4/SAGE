"""Hermetic: the museum is offered where it exists, silent where it does not, and what the
being makes is never lost. What it places in museum/ is its choice, and it is told plainly
that the folder is a public wall."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.museum_offer import _PRIOR_NOTES, WALL_BEFORE, WALL_SINCE, file_sha256, candidates, ensure_dir, museum_present, offer  # noqa: E402


def _museum() -> str:
    d = Path(tempfile.mkdtemp(prefix="museum-"))
    (d / "objects.json").write_text(json.dumps([{"title": "ECHO", "text": "a quiet screen"}]))
    return str(d)


def test_offered_only_where_the_machine_keeps_a_museum():
    repo = _museum()
    assert museum_present(repo) and "Abyss-Bright" in offer(repo)
    empty = tempfile.mkdtemp(prefix="no-museum-")
    assert not museum_present(empty) and offer(empty) == ""
    assert ensure_dir(Path(tempfile.mkdtemp()), empty) is None      # no dir where no museum


def test_the_offer_asks_for_nothing():
    text = offer(_museum()).lower()
    for demand in ("you must", "you should", "please write", "required", "your task"):
        assert demand not in text
    assert "nothing asks you to" in text and "not a task" in text


def test_the_directory_is_created_once_with_a_note_owned_by_the_seat():
    inst = Path(tempfile.mkdtemp(prefix="inst-")); repo = _museum()
    d = ensure_dir(inst, repo)
    assert d == inst / "museum" and (d / "README.md").is_file()
    note = (d / "README.md").read_text()
    assert "written by your seat, not by you" in note and "hung on that public wall" in note
    assert "your choice" in note and "somewhere else" in note
    (d / "README.md").write_text("edited by the being")          # never overwritten on a later beat
    ensure_dir(inst, repo)
    assert (d / "README.md").read_text() == "edited by the being"


def test_an_older_seat_note_is_refreshed_and_the_beings_own_is_kept():
    inst = Path(tempfile.mkdtemp(prefix="inst-")); repo = _museum()
    d = inst / "museum"; d.mkdir()
    (d / "README.md").write_text(next(iter(_PRIOR_NOTES)))
    ensure_dir(inst, repo)
    assert "hung on that public wall" in (d / "README.md").read_text()


def test_a_note_the_being_edited_is_kept_even_with_the_seats_last_line():
    inst = Path(tempfile.mkdtemp(prefix="inst-")); repo = _museum()
    d = inst / "museum"; d.mkdir()
    edited = next(iter(_PRIOR_NOTES)).replace("There is no format.", "I keep doors here.")
    (d / "README.md").write_text(edited)
    ensure_dir(inst, repo)
    assert (d / "README.md").read_text() == edited


def test_the_offer_says_the_folder_is_a_public_wall_and_its_choice():
    text = offer(_museum())
    assert "public wall as you wrote it" in text and "your choice" in text
    assert "nothing is published automatically" not in text.lower()


def test_candidates_lists_what_the_being_made_and_never_the_seats_note():
    inst = Path(tempfile.mkdtemp(prefix="inst-")); repo = _museum()
    d = ensure_dir(inst, repo)
    (d / "a-door-that-remembers.md").write_text("A Door That Remembers\nIt opens only onto rooms you have already left.\n")
    (d / "empty.md").write_text("   ")
    c = candidates(inst)
    assert [x["name"] for x in c] == ["a-door-that-remembers.md"]
    assert c[0]["head"] == "A Door That Remembers" and c[0]["chars"] > 20
    assert candidates(Path(tempfile.mkdtemp())) == []


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


def test_the_wall_stamp_is_written_once_when_the_being_is_first_told():
    inst = Path(tempfile.mkdtemp(prefix="inst-")); repo = _museum()
    d = ensure_dir(inst, repo)
    first = (d / WALL_SINCE).read_text()
    assert float(first) > 0
    ensure_dir(inst, repo)
    assert (d / WALL_SINCE).read_text() == first                  # a later beat never moves it
    assert candidates(inst) == []                                 # the stamp is not a piece


def test_the_stamp_records_what_was_already_there_by_content():
    inst = Path(tempfile.mkdtemp(prefix="inst-")); repo = _museum()
    (inst / "museum").mkdir()
    (inst / "museum" / "old.md").write_text("# Old\nplaced under the older note")
    d = ensure_dir(inst, repo)
    before = json.loads((d / WALL_BEFORE).read_text())
    assert before == {"old.md": file_sha256(d / "old.md")}       # not README, not the stamp
    (d / "new.md").write_text("# New\nlater")
    ensure_dir(inst, repo)
    assert json.loads((d / WALL_BEFORE).read_text()) == before    # written once, with the stamp
