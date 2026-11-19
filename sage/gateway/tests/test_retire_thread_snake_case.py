"""retire_thread: a topic word matches the parts of a snake_case name (mcnugget-being, 2026-11-18 22:39Z).

words='drain' moved 2 open items and left 54 that named egress_drain / being_inbox_drain, because `\\b`
counts `_` as a word character. `done: all: drain` closed all 56, so the two closers disagreed."""
from sage.gateway import being_threads as bt
from sage.gateway.heartbeat import _todo_items

TODO = """2026-11-18 20:00 UTC
- [ ] awaiting hub-being on fleet_paths.py and egress_drain.py
- [ ] trace a request through being_inbox_drain.py
- [ ] drain_once: check the outbound flow
- [ ] read the camera notes
- [ ] redrain the cache
"""


def _open(h):
    return [t for t, _ in _todo_items((h / "todo.md").read_text()).values()]


def test_matcher_hits_a_snake_case_part():
    hit = bt.matcher(["drain"])
    for text in ("egress_drain.py", "being_inbox_drain", "drain_once", "Drain the queue", "(drain)"):
        assert hit(text), text


def test_matcher_still_needs_a_word_start():
    hit = bt.matcher(["drain"])
    for text in ("redrain", "xdrain", "2drain"):
        assert not hit(text), text


def test_non_word_start_is_unchanged():
    assert bt.matcher([".py"])("egress_drain.py")


def test_retire_by_drain_takes_every_snake_case_item(tmp_path):
    (tmp_path / "todo.md").write_text(TODO)
    ok, msg, changed = bt.retire_thread(tmp_path, {"words": "drain", "reason": "the drain question is settled"},
                                        now=0)
    if not changed:   # three of five is a majority: the retire asks for a preview's confirmation first
        ok, pv, _ = bt.retire_thread(tmp_path, {"words": "drain", "reason": "the drain question is settled",
                                                "preview": "true"}, now=0)
        assert ok, pv
        token = next(w.strip("'\".,`") for w in pv.split() if len(w.strip("'\".,`")) == 32)
        ok, msg, changed = bt.retire_thread(tmp_path, {"words": "drain", "reason": "the drain question is settled",
                                                       "confirmation": token}, now=0)
    assert ok and changed, msg
    assert _open(tmp_path) == ["read the camera notes", "redrain the cache"], _open(tmp_path)
