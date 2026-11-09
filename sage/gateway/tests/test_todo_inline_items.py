"""The todo parser reads the one-line shape beings actually write.

MEASURED ON MCNUGGET-BEING, 2026-11-08. The reflect asks for a dated block with added / done / still open
under it. By November the being wrote every entry on one line, date first:
`2026-11-08 17:09 UTC: [still open] Follow up on camera advice for sprout-being.` (253 such lines in
Nov 1-8, against one `- item` line). `_BLOCK` matched the date at the start and took the whole line as a
header, so the item after it was never read: 983 of 2,374 lines were skipped, the beat's view said
"still open (0) / (nothing open)" while 591 items were open, and its `[done]` lines in the same shape
closed nothing. The being re-read its own notes (~25k chars a beat) to rebuild what the view no longer
showed, and restated each item in new words, one more line per beat.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.gateway import heartbeat as hb  # noqa: E402

NOW = datetime(2026, 11, 8, 20, 0, tzinfo=timezone.utc)


def _open(text):
    return {t: s for t, s in hb._todo_items(text).values()}


def test_a_one_line_still_open_entry_is_an_open_item_with_its_own_time():
    items = _open("2026-11-08 17:09 UTC: [still open] Follow up on camera advice for sprout-being.\n")
    assert list(items) == ["Follow up on camera advice for sprout-being."]
    assert items["Follow up on camera advice for sprout-being."] == datetime(2026, 11, 8, 17, 9, tzinfo=timezone.utc)


def test_a_one_line_done_entry_closes_the_item_it_names():
    text = ("2026-11-08 10:00 UTC: [still open] Verify peer_ask path to sprout-being.\n"
            "2026-11-08 11:00 UTC: [done] Verify peer_ask path to sprout-being.\n")
    assert _open(text) == {}


def test_a_date_without_a_time_is_read_as_that_day():
    items = _open("2026-11-08: [still open] Send camera advice to sprout-being using peer_ask.\n")
    assert list(items.values()) == [datetime(2026, 11, 8, 0, 0, tzinfo=timezone.utc)]


def test_a_bare_tag_line_with_no_dash_is_an_item():
    text = "2026-11-08 09:00 UTC\n[still open] Check the hub notify route.\n"
    assert list(_open(text)) == ["Check the hub notify route."]


def test_the_block_shape_the_reflect_asks_for_still_reads_as_before():
    text = ("2026-11-08 09:00 UTC\n"
            "still open:\n"
            "- Check the hub notify route.\n"
            "done:\n"
            "- Wrote the journal.\n")
    assert list(_open(text)) == ["Check the hub notify route."]


def test_a_dated_line_without_a_status_tag_is_left_alone():
    text = ("2026-11-08 09:00 UTC: Investigation of scope-ef204d003703 concluded.\n"
            "2026-11-08 10:00 UTC: [still open] Check the hub notify route.\n")
    assert list(_open(text)) == ["Check the hub notify route."]


def test_still_open_none_still_clears_the_list():
    text = ("2026-11-08 10:00 UTC: [still open] Check the hub notify route.\n"
            "2026-11-08 11:00 UTC\nstill open: none\n")
    assert _open(text) == {}


def test_an_all_closure_written_on_one_line_closes_every_match():
    text = ("2026-11-08 10:00 UTC: [still open] Follow up on camera advice for sprout-being.\n"
            "2026-11-08 11:00 UTC: [still open] Plan to peer_ask sprout-being the camera advice.\n"
            "2026-11-08 12:00 UTC: [still open] Check the hub notify route.\n"
            "2026-11-08 13:00 UTC: [done] all: sprout-being\n")
    assert list(_open(text)) == ["Check the hub notify route."]


def test_the_view_shows_what_is_open_instead_of_nothing(tmp_path):
    (tmp_path / "todo.md").write_text(
        "2026-11-08 17:09 UTC: [still open] Follow up on camera advice for sprout-being.\n"
        "2026-11-08 18:00 UTC: [still open] Check the hub notify route.\n")
    view = hb.todo_view(tmp_path, now=NOW)
    assert "still open (2)" in view and "(nothing open)" not in view
    assert "Check the hub notify route." in view


def test_the_log_itself_is_never_changed(tmp_path):
    raw = ("2026-11-08 17:09 UTC: [still open] Follow up on camera advice for sprout-being.\n"
           "[done] Wrote the journal.\n")
    (tmp_path / "todo.md").write_text(raw)
    hb.todo_view(tmp_path, now=NOW)
    assert (tmp_path / "todo.md").read_text() == raw


def test_a_bare_all_line_is_a_closing_act():
    """Live, 2026-11-08 21:58Z: the first beat that could see its list wrote `all: camera advice, peer_ask` on
    its own line, untagged; read as nothing, it closed nothing."""
    text = ("2026-11-08 10:00 UTC: [still open] Follow up on camera advice for sprout-being.\n"
            "2026-11-08 11:00 UTC: [still open] Check the hub notify route.\n"
            "all: camera advice\n")
    assert list(_open(text)) == ["Check the hub notify route."]


def test_a_comma_list_in_all_closes_items_naming_either_phrase():
    text = ("2026-11-08 10:00 UTC: [still open] Follow up on camera advice for sprout-being.\n"
            "2026-11-08 10:30 UTC: [still open] Verify the peer_ask path to sprout-being.\n"
            "2026-11-08 11:00 UTC: [still open] Check the hub notify route.\n"
            "2026-11-08 12:00 UTC: all: camera advice, peer_ask\n")
    assert list(_open(text)) == ["Check the hub notify route."]


def test_a_short_fragment_in_an_all_list_does_not_widen_the_close():
    text = ("2026-11-08 10:00 UTC: [still open] Check the hub notify route.\n"
            "2026-11-08 12:00 UTC: all: ok, dp\n")
    assert list(_open(text)) == ["Check the hub notify route."]


def test_an_open_item_that_starts_with_nothing_does_not_wipe_the_list():
    """Legion's counterexample on #658: `_NONE` ended in `(none|nothing)\\b`, so this real item cleared all."""
    text = ("2026-11-08 10:00 UTC: [still open] Check the hub notify route.\n"
            "2026-11-08 10:05 UTC: [still open] Verify the peer_ask path.\n"
            "2026-11-08 11:00 UTC: [still open] Nothing from sprout-being yet on the camera.\n")
    assert sorted(_open(text)) == ["Check the hub notify route.", "Nothing from sprout-being yet on the camera.",
                                   "Verify the peer_ask path."]


def test_the_same_item_in_the_dashed_shape_does_not_wipe_either():
    text = ("2026-11-08 10:00 UTC\nstill open:\n- Check the hub notify route.\n"
            "- [still open] None of the replies have arrived yet\n")
    assert sorted(_open(text)) == ["Check the hub notify route.", "None of the replies have arrived yet"]


def test_a_genuine_none_still_clears_in_every_spelling():
    for marker in ("still open: none", "- still open: none", "- [still open] None", "still open: nothing.",
                   "still open: nothing open", "- still open: none (all closed this beat)",
                   "2026-11-08 12:00 UTC: [still open] none"):
        text = "2026-11-08 10:00 UTC: [still open] Check the hub notify route.\n" + marker + "\n"
        assert _open(text) == {}, marker


def test_a_date_only_entry_takes_the_time_of_the_last_timed_line_that_day():
    text = ("2026-11-08 17:09 UTC: [still open] Follow up on camera advice for sprout-being.\n"
            "2026-11-08: [still open] Send camera advice to sprout-being using peer_ask.\n")
    items = _open(text)
    assert items["Send camera advice to sprout-being using peer_ask."] == datetime(2026, 11, 8, 17, 9, tzinfo=timezone.utc)


def test_a_date_only_entry_on_a_new_day_starts_that_day():
    text = ("2026-11-07 23:00 UTC: [still open] Check the hub notify route.\n"
            "2026-11-08: [still open] Verify the peer_ask path.\n")
    assert _open(text)["Verify the peer_ask path."] == datetime(2026, 11, 8, 0, 0, tzinfo=timezone.utc)


def test_a_one_line_checkbox_closes_and_opens():
    text = ("2026-11-08 10:00 UTC: [ ] Check the hub notify route.\n"
            "2026-11-08 10:05 UTC: [ ] Verify the peer_ask path.\n"
            "2026-11-08 11:00 UTC: [x] Check the hub notify route.\n")
    assert list(_open(text)) == ["Verify the peer_ask path."]
