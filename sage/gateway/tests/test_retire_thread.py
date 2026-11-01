"""retire_thread: close a whole line of work at once (being_threads). dp, 2026-11-01, to cbp-being: "retire
the whole hestia thread and work on something different" -- 550 of its 584 open todo items and 29 of its
30 settled entries were on that thread, and retire_note / settle could only move one at a time."""
import json
import tempfile
from pathlib import Path

from sage.gateway import being_settled as st
from sage.gateway import being_threads as bt
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict, thread_paths
from sage.gateway.heartbeat import _todo_items
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
from sage.gateway.home_recall import search_home
from sage.gateway.tests.test_hestia_dispatch import FakeMcp

_ALLOW = GatewayVerdict("allow")

TODO = """2026-10-30 09:00 UTC
- [ ] Restart the widget daemon on port 9911
- [ ] Install the widget package with apt
- [x] Read the widget docs
2026-10-31 10:00 UTC
- [ ] Build a small neural net and test it on the sine data
- [ ] Ask about the widget installer again
- [ ] Explore what a living document could be
"""


def _home(tmp_path):
    (tmp_path / "todo.md").write_text(TODO)
    for q, a in (("Is the widget daemon running?", "no, port 9911 is closed"),
                 ("Why does the net overfit?", "too few samples; more data fixed it"),
                 ("How do I install the widget?", "apt, but the seat declines it")):
        assert st.settle(tmp_path, {"question": q, "answer": a}, now=0)[0]
    return tmp_path


def _open(h):
    return [t for t, _ in _todo_items((h / "todo.md").read_text()).values()]


def test_a_thread_leaves_the_todo_and_the_settled_list_and_the_rest_stays(tmp_path):
    h = _home(tmp_path)
    ok, msg, changed = bt.retire_thread(h, {"words": "widget, daemon", "reason": "dp: drop it"}, now=0)
    assert ok and changed, msg
    assert "3 open todo item(s) and 2 settled entries" in msg and "Still open: 2" in msg
    assert _open(h) == ["Build a small neural net and test it on the sine data",
                        "Explore what a living document could be"]
    assert [e["question"] for e in st.read(h)[0]] == ["Why does the net overfit?"]
    arch = (h / "todo.retired-1970-01-01-thread.md").read_text()
    assert "Topic words: widget, daemon" in arch and "No longer current: dp: drop it" in arch
    assert "- [ ] Install the widget package with apt (since 2026-10-30 09:00 UTC)" in arch
    assert "Is the widget daemon running? -> no, port 9911 is closed" in arch
    assert arch.endswith(TODO), "the replaced todo.md is kept whole"
    log = [json.loads(l) for l in (h / st.SETTLED_LOG).read_text().splitlines()]
    assert log[-1]["op"] == "retire_thread" and log[-1]["ids"] == ["s1", "s3"]
    assert log[-1]["to"] == "todo.retired-1970-01-01-thread.md" and len(log[-1]["from"]) == 2


def test_open_items_keep_the_date_they_were_opened(tmp_path):
    h = _home(tmp_path)
    before = {t: s for t, s in _todo_items(TODO).values()}
    bt.retire_thread(h, {"words": "widget", "reason": "r"}, now=0)
    after = {t: s for t, s in _todo_items((h / "todo.md").read_text()).values()}
    assert after and all(before[t] == s for t, s in after.items())


def test_recall_still_finds_what_was_retired(tmp_path):
    h = _home(tmp_path)
    bt.retire_thread(h, {"words": "widget", "reason": "r"}, now=0)
    hits = search_home(h, "widget installer")
    assert any(r["source"].startswith("todo.retired-") for r in hits), hits


def test_a_preview_changes_nothing_and_says_what_would_move(tmp_path):
    h = _home(tmp_path)
    before = {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()}
    ok, msg, changed = bt.retire_thread(h, {"words": "widget", "preview": "true"}, now=0)
    assert ok and not changed and msg.startswith("PREVIEW, nothing was changed")
    assert "3 of 5 open todo item(s) and 2 of 3 settled entries would be retired" in msg
    assert "STAYS: Build a small neural net" in msg
    assert {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()} == before


def test_a_word_matches_at_the_start_of_a_word_only(tmp_path):
    hit = bt.matcher(bt.words_of("install, api, port 99"))
    assert hit("the installer") and hit("API down") and hit("on port 9911")
    assert not hit("reinstalled") and not hit("rapid growth") and not hit("support 9911")
    assert bt.matcher(["/proc"])("read /proc/1/cmdline")


def test_refusals_change_nothing(tmp_path):
    h = _home(tmp_path)
    before = {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()}
    for args, said in (({}, "needs 'words'"), ({"words": "ab, widget", "reason": "r"}, "at least 3"),
                       ({"words": "widget"}, "needs a 'reason'")):
        ok, msg, changed = bt.retire_thread(h, args, now=0)
        assert not ok and not changed and said in msg, (args, msg)
    ok, msg, changed = bt.retire_thread(h, {"words": "zebra", "reason": "r"}, now=0)
    assert ok and not changed and "Nothing names zebra" in msg
    assert {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()} == before


def test_a_second_retire_the_same_day_gets_its_own_file(tmp_path):
    h = _home(tmp_path)
    bt.retire_thread(h, {"words": "daemon", "reason": "r"}, now=0)
    bt.retire_thread(h, {"words": "widget", "reason": "r"}, now=0)
    assert (h / "todo.retired-1970-01-01-thread.md").exists()
    assert (h / "todo.retired-1970-01-01-thread-2.md").exists()


def test_the_gate_is_told_every_file_it_writes(tmp_path):
    h = _home(tmp_path)
    declared = set(thread_paths({"words": "widget", "reason": "r"}, {"memory_root": str(h)}))
    assert thread_paths({"words": "widget", "preview": "true"}, {"memory_root": str(h)}) == []
    before = {p: p.read_bytes() for p in h.iterdir() if p.is_file()}
    bt.retire_thread(h, {"words": "widget", "reason": "r"})
    after = {p: p.read_bytes() for p in h.iterdir() if p.is_file()}
    changed = {str(p.resolve()) for p in set(before) | set(after) if before.get(p) != after.get(p)}
    assert changed and changed <= declared, changed - declared


def test_the_verb_retires_and_witnesses():
    FakeMcp.calls = []
    root = Path(tempfile.mkdtemp(prefix="rt-"))
    d = HestiaF1aDispatcher("sprout-being", str(root), mcp_factory=lambda ep, pid: FakeMcp(ep, pid))
    _home(root)
    env = d(BeingIntent("retire_thread", {"words": "widget", "reason": "finished"}), _ALLOW)
    assert env.ok and env.witness_id, env.error
    assert "Build a small neural net" in (root / "todo.md").read_text()
    assert "widget" not in (root / "todo.md").read_text().split("UTC:", 1)[-1].lower()
