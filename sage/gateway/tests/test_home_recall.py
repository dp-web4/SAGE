"""Hermetic: recall over the being's own home files (journal entries, todo blocks, notes,
scratch). No model, no membot, temp dirs only."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.home_recall import index_home, render, search_home, _entries  # noqa: E402


def _home() -> Path:
    d = Path(tempfile.mkdtemp(prefix="home-"))
    (d / "journal.md").write_text(
        "2026-09-05 14:25 UTC — The beat is ending. I reviewed #39 and #40 and kept boundaries strict.\n\n"
        "2026-09-06 22:04 UTC — I asked legion about PR #49 and got no answer yet; silence is network, not verdict.\n\n"
        "2026-09-07 23:12 UTC — The distinction between hearing and listening had never been named before.\n")
    (d / "todo.md").write_text("2026-09-06 10:00 UTC\n- [ ] ask for reach on shared-context\n- [x] write journal\n")
    (d / "notes").mkdir()
    (d / "notes" / "relay.md").write_text("Relay from the seat: legion answered about the hub join.\n")
    (d / "scratch").mkdir()
    (d / "scratch" / "beat_summary.md").write_text("listening as a practice, not an attitude\n")
    return d


def test_entries_split_on_date_lines_and_keep_an_undated_head():
    e = _entries("intro text\n2026-09-05 14:25 UTC — one\n2026-09-06 22:04 UTC — two\n", "journal.md")
    assert [x["date"] for x in e] == ["", "2026-09-05 14:25", "2026-09-06 22:04"]
    assert e[2]["text"].startswith("2026-09-06") and "two" in e[2]["text"]
    assert _entries("", "x") == [] and _entries("no dates at all", "x")[0]["date"] == ""


def test_index_covers_journal_todo_notes_and_scratch():
    d = _home()
    srcs = sorted({u["source"] for u in index_home(d)})
    assert srcs == ["journal.md", "notes/relay.md", "scratch/beat_summary.md", "todo.md"]
    assert sum(1 for u in index_home(d) if u["source"] == "journal.md") == 3


def test_search_ranks_by_distinct_term_overlap_and_names_the_source_and_date():
    d = _home()
    r = search_home(d, "listening practice", top_k=3)
    assert r and r[0]["source"] in ("scratch/beat_summary.md", "journal.md")
    assert any(x["source"] == "journal.md" and x["date"] == "2026-09-07 23:12" for x in r)
    r2 = search_home(d, "legion answer hub", top_k=5)
    assert {x["source"] for x in r2} >= {"journal.md", "notes/relay.md"}
    # stopwords alone match nothing; an empty home matches nothing
    assert search_home(d, "the and of") == []
    assert search_home(Path(tempfile.mkdtemp(prefix="empty-")), "anything") == []


def test_snippets_are_bounded_and_render_is_readable():
    d = _home()
    (d / "notes" / "long.md").write_text("x " * 400 + "boundaries strict " + "y " * 400)
    r = search_home(d, "boundaries strict", top_k=2, snippet=120)
    long = [x for x in r if x["source"] == "notes/long.md"]
    assert long and len(long[0]["snippet"]) <= 130 and "boundaries" in long[0]["snippet"]
    text = render(r)
    assert text.startswith("From your own journal") and "[notes/long.md]" in text
    assert render([]) == ""


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")
