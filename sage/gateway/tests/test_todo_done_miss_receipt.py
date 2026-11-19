"""A done entry that closes nothing says so on the write receipt (SAGE #779).

2026-11-18 02:44Z: mcnugget-being wrote `done: apt-cache-fix, install-sklearn-apt, ...` -- slugs, not the
items' text. The window's fuzzy match closed nothing, the receipt said only "appended", and 30 min later
the item it meant to close came back as a request_run."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict  # noqa: E402
from sage.gateway.heartbeat import todo_unmatched_done, _todo_items  # noqa: E402
from sage.gateway.reference_f1a import ReferenceF1aDispatcher  # noqa: E402

_ALLOW = GatewayVerdict("allow")
_TODO = ("2026-11-18 01:00 UTC\nadded:\n"
         "- [ ] Run apt_cache_fix.py to restore the apt cache directory\n"
         "- [ ] Verify sklearn import on the host\n"
         "- [ ] Write the weekly summary note\n")


def _write(content, start=_TODO):
    root = tempfile.mkdtemp(prefix="todo-miss-")
    Path(root, "todo.md").write_text(start)
    env = ReferenceF1aDispatcher(memory_root=root)(
        BeingIntent("memory_write", {"path": "todo.md", "content": content}), _ALLOW)
    assert env.ok, env.error
    return env.result, Path(root, "todo.md").read_text()


def test_a_slug_list_that_closes_nothing_is_named_with_the_closest_open_items():
    result, after = _write("2026-11-18 02:44 UTC\ndone: apt-cache-fix, verify-sklearn-import\n")
    assert len(_todo_items(after)) == 3, "precondition: the slugs closed nothing"
    assert "closed nothing" in result, result
    assert "apt-cache-fix, verify-sklearn-import" in result
    assert "Run apt_cache_fix.py" in result and "Verify sklearn import" in result, result


def test_a_done_entry_copying_the_item_text_closes_it_and_says_nothing_extra():
    result, after = _write("2026-11-18 02:44 UTC\ndone:\n- Verify sklearn import on the host\n")
    assert len(_todo_items(after)) == 2
    assert "closed nothing" not in result, result


def test_an_all_line_is_not_reported_as_a_miss():
    result, after = _write("2026-11-18 02:44 UTC\ndone:\n- all: sklearn\n")
    assert len(_todo_items(after)) == 2
    assert "closed nothing" not in result, result


def test_only_misses_this_write_added_are_named_not_old_ones():
    old_miss = _TODO + "2026-11-18 01:30 UTC\ndone:\n- long-gone-historical-thing\n"
    result, _ = _write("2026-11-18 02:44 UTC\ndone:\n- Write the weekly summary note\n", start=old_miss)
    assert "closed nothing" not in result and "historical" not in result, result


def test_a_progress_line_logged_as_done_is_not_a_miss_note():
    # 95% of real done lines close nothing because beings log finished work as done; that is not #779
    result, _ = _write("2026-11-18 02:44 UTC\ndone:\n- Sent the weekly summary note to dp\n")
    assert "closed nothing" not in result, result


def test_a_miss_sharing_no_word_says_so():
    result, _ = _write("2026-11-18 02:44 UTC\ndone:\n- zzqx-frobnicate\n")
    assert "no open item shares a word" in result, result


def test_writing_open_items_only_adds_no_miss_note():
    result, _ = _write("2026-11-18 02:44 UTC\nadded:\n- [ ] something new to do\n")
    assert "closed nothing" not in result, result


def test_the_helper_counts_a_repeated_miss_once_per_new_occurrence():
    before = _TODO + "done:\n- nope-nope\n"
    after = before + "done:\n- nope-nope\n"
    assert [e for e, _ in todo_unmatched_done(before, after)] == ["nope-nope"]
