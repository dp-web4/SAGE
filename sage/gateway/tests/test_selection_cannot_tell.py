"""A failed turn selection is recorded, never read as "no one is waiting" (2026-10-04).

On HUB, hub-claude's 09-21 question was never selected in 300+ beats while every beat record looked clean:
pending_selection swallowed all exceptions and returned the same empty tuple as an empty inbox."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv, heartbeat as hb  # noqa: E402


def test_a_selection_that_raises_is_named_in_the_record(monkeypatch):
    def broken(instance):
        raise ValueError("bad meta file")
    monkeypatch.setattr(conv, "listing", broken)
    monkeypatch.setattr(hb, "LAST_SELECTION_ERROR", None)
    out = hb.pending_selection(Path(tempfile.mkdtemp()), "hub-being")
    assert out == ("", "", "", "", None)
    assert hb.LAST_SELECTION_ERROR == "ValueError: bad meta file"


def test_a_clean_empty_selection_records_no_error(monkeypatch):
    monkeypatch.setattr(hb, "LAST_SELECTION_ERROR", None)
    hb.pending_selection(Path(tempfile.mkdtemp()), "hub-being")
    assert hb.LAST_SELECTION_ERROR is None


def test_the_beat_record_carries_it():
    src = (Path(hb.__file__)).read_text()
    assert '"selection_error": LAST_SELECTION_ERROR,' in src
    assert '"selected": ({"turn": f"{selected.cid}:{selected.seq}"' in src, "never selected vs selected, unanswered"


def test_selected_is_defined_before_anything_can_kill_the_beat():
    """The record reads `selected`; a beat killed before selection would otherwise lose its record to NameError."""
    src = Path(hb.__file__).read_text()
    init = src.index("    selected = None          # the record names it")
    first_try = src.index("    try:", src.index("    explore = after = reflect = answer = None"))
    assert init < first_try
