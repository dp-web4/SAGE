"""#779: an unknown header must end the section above it, and a known section in markdown or bold shape is
still that section.

Before: `section` was reset only by a dated block or a known `open:/added:/done:/completed:` header. An item
under `blocked:` / `notes:` / `## Context` inherited the section above it, so after a `done:` it closed
silently (the issue's parser probe, last row), and `## done` / `**done:**` -- shapes mcnugget-being's todo.md
holds -- were not recognised, so their items took the section above them instead.
"""
from sage.gateway.heartbeat import _canonical_todo, _parse_todo


def _open(text):
    return sorted(t for t, _ in _parse_todo(_canonical_todo(text)).values())


def test_issue_probe_unknown_header_after_done_does_not_close():
    text = ("2026-11-18 02:00 UTC\n- [open] Install sklearn in the run box\n"
            "done:\n- something finished\nblocked:\n- Install sklearn in the run box\n")
    assert _open(text) == ["Install sklearn in the run box"]


def test_items_under_unknown_header_are_not_opened():
    text = "2026-11-18 02:00 UTC\nopen:\n- real goal\nnotes:\n- a note, not a goal\n"
    assert _open(text) == ["real goal"]


def test_markdown_and_bold_known_sections_are_sections():
    for done_hdr in ("## done", "**done:**", "### Done:", "__completed__:"):
        text = ("2026-11-18 02:00 UTC\n## still open\n- first goal\n- second goal\n"
                f"{done_hdr}\n- first goal\n")
        assert _open(text) == ["second goal"], done_hdr


def test_bold_still_open_opens():
    text = "2026-11-18 02:00 UTC\n**still open:**\n- a goal\n"
    assert _open(text) == ["a goal"]


def test_list_items_ending_in_colon_are_still_items():
    # a dash makes it an item, never a header: `- Step 1:` under open: stays a goal
    text = "2026-11-18 02:00 UTC\nopen:\n- Step one of the plan:\n- next\n"
    assert _open(text) == ["Step one of the plan:", "next"]


def test_header_reset_keeps_explicit_tags_working():
    text = ("2026-11-18 02:00 UTC\n- [open] goal A\nnext steps:\n- [done] goal A\n"
            "context:\n- [open] goal B\n")
    assert _open(text) == ["goal B"]


def test_inline_done_line_is_still_a_closing_not_a_header():
    # `done: <item>` (content after the colon) is the _BARE_DONE closing act, untouched by the header rule
    text = "2026-11-18 02:00 UTC\n- [open] goal A\ndone: goal A\n"
    assert _open(text) == []
