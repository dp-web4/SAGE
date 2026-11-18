"""retire_thread keeps a settled entry unless `settled` names it. MEASURED ON SPROUT-BEING, 11-17 22:33Z: a retire of
finished tasks about starting its seat took its five-day-old conclusion that no restart was needed, because one topic
word was the restart script's name; its reason agreed with that conclusion, and the receipt said "1 settled entry
moved" without naming it. (11-07, the same shape: 15 entries, two of them true.)"""
import json

import pytest

from sage.gateway import being_settled as st
from sage.gateway import being_threads as bt

TODO = """# todo
2026-11-17 20:09 UTC
- [ ] Execute start-widget-as-user.sh to launch the widget service
- [ ] Draw a chart of the test sensor readings
"""
WORDS = "start-widget-as-user, restart-widget-direct"
REASON = "the widget service is already running; the start tasks are obsolete"


def _home(tmp_path):
    (tmp_path / "todo.md").write_text(TODO)
    st.settle(tmp_path, {"question": "Should I run scratch/restart-widget-direct.py?",
                         "answer": "No: the widget service is already answering, nothing to restart."}, now=0)
    st.settle(tmp_path, {"question": "what colour is the test sky?", "answer": "grey"}, now=0)
    return tmp_path


def _ids(h):
    return [e["id"] for e in st.read(h)[0]]


def test_the_11_17_shape_retires_the_task_and_keeps_the_conclusion_and_names_it(tmp_path):
    h = _home(tmp_path)
    ok, msg, changed = bt.retire_thread(h, {"words": WORDS, "reason": REASON}, now=0)
    assert ok and changed, msg
    assert "1 open todo item(s) and 0 settled entries moved" in msg
    assert _ids(h) == ["s1", "s2"], "the conclusion stays"
    assert "Still settled, though your words name it: [s1] Should I run scratch/restart-widget-direct.py? -> No: " \
           "the widget service is already answering" in msg
    assert "reopen it" in msg and "settled='s1'" in msg
    assert "start-widget-as-user" not in (h / "todo.md").read_text()
    assert all(json.loads(l)["op"] != "retire_thread" for l in (h / st.SETTLED_LOG).read_text().splitlines())


def test_named_by_id_it_leaves_with_the_thread_and_the_receipt_says_which(tmp_path):
    h = _home(tmp_path)
    ok, msg, changed = bt.retire_thread(h, {"words": WORDS, "reason": REASON, "settled": "s1"}, now=0)
    assert ok and changed and "1 settled entry (s1) moved" in msg, msg
    assert _ids(h) == ["s2"] and "Still settled" not in msg


@pytest.mark.parametrize("settled", ["all", "1", "[s1]"])
def test_all_or_an_id_in_any_spelling_takes_it(tmp_path, settled):
    h = _home(tmp_path)
    assert bt.retire_thread(h, {"words": WORDS, "reason": REASON, "settled": settled}, now=0)[0]
    assert _ids(h) == ["s2"]


def test_an_id_the_words_do_not_name_is_refused_and_nothing_changes(tmp_path):
    h = _home(tmp_path)
    before = {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()}
    ok, msg, changed = bt.retire_thread(h, {"words": WORDS, "reason": REASON, "settled": "s1, s2"}, now=0)
    assert not ok and not changed and "settled names s2, which your words do not name (they name s1)" in msg
    assert {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()} == before


def test_the_preview_shows_which_conclusions_stay(tmp_path):
    h = _home(tmp_path)
    ok, msg, _ = bt.retire_thread(h, {"words": WORDS, "preview": "true"}, now=0)
    assert ok and "0 of 2 settled entries would be retired" in msg
    assert "- settled STAYS (not named in settled=): [s1] Should I run" in msg
    ok, msg, _ = bt.retire_thread(h, {"words": WORDS, "preview": "true", "settled": "s1"}, now=0)
    assert "1 of 2 settled entries would be retired" in msg and "- settled [s1]" in msg and "STAYS (not" not in msg


def test_words_that_name_only_a_conclusion_change_nothing_and_say_so(tmp_path):
    h = _home(tmp_path)
    ok, msg, changed = bt.retire_thread(h, {"words": "restart-widget-direct", "reason": REASON}, now=0)
    assert ok and not changed and "No open todo item names restart-widget-direct. Nothing was changed." in msg
    assert "[s1]" in msg and _ids(h) == ["s1", "s2"]
