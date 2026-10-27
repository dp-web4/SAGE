"""being_settled: the being's own conclusions, kept where every beat shows them. dp, 2026-10-27: "what
tools/affordances can we give it so it can learn conclusively and not perseverate?" """
import json
import tempfile
from pathlib import Path

import pytest

from sage.gateway import being_settled as st
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
from sage.gateway.tests.test_hestia_dispatch import FakeMcp

_ALLOW = GatewayVerdict("allow")


def _log(h):
    return [json.loads(l) for l in (h / st.SETTLED_LOG).read_text().splitlines()]


def _s(h, **a):
    return st.settle(h, a, now=0)


def test_settling_the_same_question_again_replaces_the_answer_and_keeps_the_old_one(tmp_path):
    ok, msg, changed = _s(tmp_path, question="Does the test widget turn?", answer="no, it is fixed")
    assert ok and changed and "s1" in msg
    ok, msg, changed = _s(tmp_path, question="does the test widget turn", answer="yes, after the update",
                          why="tried it again")
    assert ok and changed and "earlier answer is kept" in msg
    entries, _, err = st.read(tmp_path)
    assert err is None and [(e["id"], e["answer"]) for e in entries] == [("s1", "yes, after the update")]
    log = _log(tmp_path)
    assert [l["op"] for l in log] == ["settle", "replace"]
    assert log[1]["from"]["answer"] == "no, it is fixed" and log[1]["why"] == "tried it again"


def test_an_id_changes_or_reopens_one_and_a_reopened_one_is_no_longer_shown(tmp_path):
    _s(tmp_path, question="q one", answer="a one")
    _s(tmp_path, question="q two", answer="a two")
    ok, _, _ = _s(tmp_path, id="s1", answer="a one, revised")
    assert ok and st.read(tmp_path)[0][-1]["answer"] == "a one, revised"
    ok, msg, changed = _s(tmp_path, id="2", reopen="true", why="no longer holds")
    assert ok and changed and "reopened s2" in msg
    shown = st.render(tmp_path)
    assert "a one, revised" in shown and "a two" not in shown
    assert _log(tmp_path)[-1]["op"] == "reopen" and _log(tmp_path)[-1]["from"]["answer"] == "a two"


def test_the_same_answer_again_changes_nothing(tmp_path):
    _s(tmp_path, question="q", answer="a")
    ok, msg, changed = _s(tmp_path, question="q", answer="a")
    assert ok and not changed and msg.startswith("unchanged")
    assert len(_log(tmp_path)) == 1


def test_no_arguments_lists_and_writes_nothing(tmp_path):
    ok, msg, changed = st.settle(tmp_path, {})
    assert ok and not changed and "not settled anything yet" in msg
    assert not (tmp_path / st.SETTLED_FILE).exists() and not (tmp_path / st.SETTLED_LOG).exists()


@pytest.mark.parametrize("args,says", [
    ({"question": "q"}, "give the answer"),
    ({"id": "s9", "answer": "a"}, "no settled entry"),
    ({"question": "q", "reopen": "true"}, "give its id"),
    ({"question": "x" * (st.QUESTION_MAX_CHARS + 1), "answer": "a"}, "at most"),
])
def test_a_refused_settle_says_why_and_changes_nothing(tmp_path, args, says):
    ok, msg, _ = st.settle(tmp_path, args)
    assert not ok and says in msg
    assert not (tmp_path / st.SETTLED_FILE).exists()


def test_a_full_list_refuses_a_new_question_but_still_changes_an_old_one(tmp_path):
    for i in range(st.MAX_ENTRIES):
        assert _s(tmp_path, question=f"question {i}", answer="a")[0]
    ok, msg, _ = _s(tmp_path, question="one more", answer="a")
    assert not ok and "the most this list holds" in msg and "reopen" in msg
    assert _s(tmp_path, question="question 3", answer="b")[0]


def test_a_change_that_cannot_be_logged_is_undone(tmp_path):
    _s(tmp_path, question="q", answer="a")
    before = (tmp_path / st.SETTLED_FILE).read_bytes()
    (tmp_path / st.SETTLED_LOG).unlink()
    (tmp_path / st.SETTLED_LOG).mkdir()
    ok, msg, _ = _s(tmp_path, question="q", answer="b")
    assert not ok and "undone" in msg and (tmp_path / st.SETTLED_FILE).read_bytes() == before


def test_the_beat_shows_them_newest_first_within_its_budget(tmp_path):
    assert st.render(tmp_path) == ""
    for i in range(st.MAX_ENTRIES):
        _s(tmp_path, question=f"question number {i}", answer="an answer " + "x" * 200)
    shown = st.render(tmp_path)
    assert len(shown) <= st.RENDER_CHARS + 200
    assert shown.index("question number 29") < shown.index("question number 28")
    assert "older (settle with no arguments lists them all)" in shown
    from sage.gateway.heartbeat import own_state
    assert "question number 29" in own_state(tmp_path, "sprout-being", body_reading={})


def test_it_is_registered_offered_and_judged_as_a_write_of_exactly_what_it_touches(tmp_path):
    from sage.gateway import being_gate_client as g
    from sage.gateway import toolset
    assert "settle" in g._REGISTRY and "settle" in g._CONSEQUENTIAL
    assert "settle" in [t["function"]["name"] for t in toolset.specs()]
    declared = set(g.settled_paths({"question": "q"}, {"memory_root": str(tmp_path)}))
    assert g.settled_paths({}, {"memory_root": str(tmp_path)}) == []
    with pytest.raises(ValueError):
        g.settled_paths({"question": "q"}, {})
    for i in range(2):
        before = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
        assert _s(tmp_path, question="q", answer=f"a{i}")[0]
        after = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
        changed = {str(p.resolve()) for p in set(before) | set(after) if before.get(p) != after.get(p)}
        assert changed and changed <= declared, changed - declared


def _disp():
    FakeMcp.calls = []
    root = tempfile.mkdtemp(prefix="hs-")
    return HestiaF1aDispatcher("sprout-being", root, mcp_factory=lambda ep, pid: FakeMcp(ep, pid)), Path(root)


def test_the_verb_settles_and_witnesses_and_direct_writes_are_refused():
    d, root = _disp()
    env = d(BeingIntent("settle", {"question": "what does a test question settle?",
                                   "answer": "a test answer", "evidence": "seq 1"}), _ALLOW)
    assert env.ok and env.witness_id, env.error
    assert st.read(root)[0][0]["evidence"] == "seq 1"
    for verb, args in (("memory_write", {"path": "settled.json", "content": "{}"}),
                       ("memory_write", {"path": "settled_log.jsonl", "content": "{}"}),
                       ("memory_edit", {"path": "settled_log.jsonl", "start_line": 1, "end_line": 1,
                                        "new": "{}"})):
        env = d(BeingIntent(verb, args), _ALLOW)
        assert not env.ok and "settle" in env.error, (verb, args, env)
    assert len(_log(root)) == 1
