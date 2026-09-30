"""A letter longer than the beat's window is cut at a line, and the window says so (2026-09-30).

notes/from-the-seat.md and notes/from-dp.md are written top-down by someone else, and one beat
shows the last 3,000 / 4,000 characters. The cut was a bare `t[-limit:]`. Measured on cbp-being:
8 of the 75 committed versions of the seat's letter were over 3,000, the last three in a row, and
the 04:24Z one (3,945) reached the being starting at ` end_line 311, new "".`, which is the
second half of the one line that carried fix (a)'s call form. Fix (b) arrived whole, and the
05:00Z beat chose (b). Each test below is one property of that view.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import body  # noqa: E402
from sage.gateway import heartbeat as hb  # noqa: E402

A = '- (a) One edit: memory_edit start_line 238, end_line 311, new "". Ran: exit 0.'
B = "- (b) Two edits: replace blank line 209 with the two lines, then delete 312-313."


def _letter(tmp_path, name: str, text: str) -> Path:
    (tmp_path / "notes").mkdir(exist_ok=True)
    p = tmp_path / "notes" / name
    p.write_text(text)
    return p


def _over(limit: int, split_at: str = "start_line 238,") -> str:
    """A letter whose raw tail-cut falls inside line A, just after `split_at` (the 04:24Z shape)."""
    tail = A.split(split_at)[1] + "\n" + B + "\n" + "## Receipts\n" + "- a receipt line\n" * 40
    room = limit - hb.LETTER_CUT_ROOM
    tail = tail + "x" * (room - len(tail) - 1) + "\n"          # the shown part is exactly `room`
    head = "# From the seat.\n## State\n" + "- a measured line\n" * 60 + A.split(split_at)[0] + split_at
    return head + tail


def test_a_letter_that_fits_is_shown_whole_and_unmarked(tmp_path):
    text = "# From the seat.\n" + A + "\n" + B + "\n"
    p = _letter(tmp_path, "from-the-seat.md", text)
    assert hb.letter_view(p, hb.SEAT_CHANNEL_CHARS, hb.SEAT_CHANNEL) == text
    exact = "y" * (hb.SEAT_CHANNEL_CHARS - 1) + "\n"
    p.write_text(exact)
    assert hb.letter_view(p, hb.SEAT_CHANNEL_CHARS, hb.SEAT_CHANNEL) == exact


def test_the_cut_never_shows_half_of_the_line_that_carries_the_call_form(tmp_path):
    """The 04:24Z letter: the being got `end_line 311` without `start_line 238`."""
    text = _over(hb.SEAT_CHANNEL_CHARS)
    assert text[-(hb.SEAT_CHANNEL_CHARS - hb.LETTER_CUT_ROOM):].startswith(' end_line 311, new "".')
    view = hb.letter_view(_letter(tmp_path, "from-the-seat.md", text), hb.SEAT_CHANNEL_CHARS, hb.SEAT_CHANNEL)
    marker, shown = view.split("\n", 1)
    assert "end_line 311" not in shown, "half of fix (a) is worse than none of it"
    assert shown.startswith(B), "the first thing shown is a whole line of the letter"
    assert all(ln in text.splitlines() for ln in shown.splitlines())
    assert shown.endswith(text[-200:]), "the end of the letter is what a beat keeps"


def test_the_marker_counts_what_is_above_and_names_the_read(tmp_path):
    text = _over(hb.SEAT_CHANNEL_CHARS)
    view = hb.letter_view(_letter(tmp_path, "from-the-seat.md", text), hb.SEAT_CHANNEL_CHARS, hb.SEAT_CHANNEL)
    marker, shown = view.split("\n", 1)
    hidden = text[:len(text) - len(shown)]
    assert hidden + shown == text
    assert marker.startswith("[") and marker.endswith("]")
    assert f"{len(text):,} characters" in marker
    assert f"first {len(hidden):,} characters ({hidden.count(chr(10))} lines) are NOT shown" in marker
    assert "not the letter's first line" in marker
    assert 'memory_read path "notes/from-the-seat.md"' in marker


def test_the_marker_is_inside_the_window_not_added_to_it(tmp_path):
    """#275: the seed is at the edge of the loop's room; saying the cut must not cost more."""
    for limit, name, rel in ((hb.SEAT_CHANNEL_CHARS, "from-the-seat.md", hb.SEAT_CHANNEL),
                             (hb.DP_CHANNEL_CHARS, "from-dp.md", hb.DP_CHANNEL)):
        text = "# head\n" + "- a line of a very long letter, with a number 1,234,567\n" * 4000
        view = hb.letter_view(_letter(tmp_path, name, text), limit, rel)
        assert len(view) <= limit, (name, len(view))
        assert len(view) > limit - hb.LETTER_CUT_ROOM - 80, "and it does not give the window away"


def test_one_line_longer_than_the_window_says_it_starts_mid_line(tmp_path):
    text = "z" * 9000
    view = hb.letter_view(_letter(tmp_path, "from-the-seat.md", text), hb.SEAT_CHANNEL_CHARS, hb.SEAT_CHANNEL)
    marker, shown = view.split("\n", 1)
    assert "starts in the middle of a line" in marker and "(0 lines)" in marker
    assert shown == "z" * (hb.SEAT_CHANNEL_CHARS - hb.LETTER_CUT_ROOM)


def test_a_missing_letter_is_still_nothing(tmp_path):
    assert hb.letter_view(tmp_path / "notes" / "from-the-seat.md", hb.SEAT_CHANNEL_CHARS, hb.SEAT_CHANNEL) == ""


def test_own_state_renders_both_letters_through_it(tmp_path, monkeypatch):
    """The real path: the block the being reads, for the seat's letter and for dp's."""
    monkeypatch.setattr(body, "metabolism", lambda **k: {"live": False})
    _letter(tmp_path, "from-the-seat.md", _over(hb.SEAT_CHANNEL_CHARS))
    _letter(tmp_path, "from-dp.md", _over(hb.DP_CHANNEL_CHARS))
    state = hb.own_state(tmp_path)
    for header, rel in (("## From the seat", hb.SEAT_CHANNEL), ("## From dp, the operator", hb.DP_CHANNEL)):
        block = state.split(header, 1)[1].split("\n\n## ", 1)[0]
        lines = block.splitlines()
        assert lines[1].startswith("[This letter is ") and f'memory_read path "{rel}"' in lines[1], lines[1][:80]
        assert lines[2] == B, "the letter resumes at a whole line"
        assert "end_line 311" not in block
