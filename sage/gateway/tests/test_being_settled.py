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


def test_a_full_list_names_the_entry_a_refused_question_reads_close_to(tmp_path):
    _s(tmp_path, question="Why can a regular user process not open the widget?", answer="a")
    for i in range(st.MAX_ENTRIES - 1):
        assert _s(tmp_path, question=f"filler {i} about lamps", answer="a")[0]
    ok, msg, _ = _s(tmp_path, question="Why does a regular user process fail to open the widget?", answer="b")
    assert not ok and "the most this list holds" in msg and "reads close to s1" in msg and "id=s1" in msg
    ok, msg, _ = _s(tmp_path, question="What colour is the sky at dusk?", answer="b")
    assert not ok and "reads close to" not in msg
    assert len(st.read(tmp_path)[0]) == st.MAX_ENTRIES


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
    assert "settle with no arguments shows them whole" in shown
    from sage.gateway.heartbeat import own_state
    assert "question number 29" in own_state(tmp_path, "sprout-being", body_reading={})


def test_no_entry_leaves_the_beat_even_at_every_maximum(tmp_path):
    """cbp's probe on #574: at realistic lengths only ~7 entries fit, so the oldest, the one settled once and
    never revisited, dropped out of the beat. Every id stays, and the newest keeps its answer."""
    for i in range(st.MAX_ENTRIES):
        _s(tmp_path, question=f"q{i} " + "w" * (st.QUESTION_MAX_CHARS - 5),
           answer="a" * st.ANSWER_MAX_CHARS, evidence="e" * st.EVIDENCE_MAX_CHARS)
    entries, _, _ = st.read(tmp_path)
    shown = st.render(tmp_path)
    assert len(shown) <= st.RENDER_CHARS
    for e in entries:
        assert f"[{e['id']}] " in shown, e["id"]
    assert f"[{entries[-1]['id']}] q29 " in shown and "aaaa" in shown.split("\n")[1]


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


def test_an_answer_shown_with_the_beat_is_shown_whole_and_on_one_line(tmp_path):
    """pub's review of #574: a 600-char answer was cut at 320, losing a conclusion at its end; and an
    answer's own newlines could draw a heading or a fake entry in the beat."""
    _s(tmp_path, question="does it work?", answer="x" * (st.ANSWER_MAX_CHARS - 15) + " THE CONCLUSION",
       evidence="e" * st.EVIDENCE_MAX_CHARS)
    _s(tmp_path, question="two\nlines?", answer="first\n## Fake heading\n- [s9] fake -> entry")
    shown = st.render(tmp_path)
    assert "THE CONCLUSION" in shown
    assert "\n## Fake" not in shown and "\n- [s9]" not in shown and "[s2] two lines? -> first ## Fake" in shown


def test_an_id_cannot_take_a_question_another_entry_holds(tmp_path):
    """pub's review of #574: settling s2 with s1's question left two entries with one question."""
    _s(tmp_path, question="Is the camera mine?", answer="yes")
    _s(tmp_path, question="what is the sky?", answer="blue")
    ok, msg, _ = _s(tmp_path, id="s2", question="is the camera mine", answer="no")
    assert not ok and "s1 already holds that question" in msg
    assert [e["question"] for e in st.read(tmp_path)[0]] == ["Is the camera mine?", "what is the sky?"]


def test_a_case_variant_of_a_verb_owned_file_is_refused_too():
    # macOS opens Settled.json as settled.json: an exact-case guard would let memory_write past the log there
    d, root = _disp()
    for name in ("Settled.json", "SETTLED_LOG.jsonl", "Self.json", "SELF_LOG.jsonl", "Tuned.json"):
        env = d(BeingIntent("memory_write", {"path": name, "content": "{}"}), _ALLOW)
        assert not env.ok and "changed only with" in env.error, (name, env)


def test_a_new_question_close_to_one_already_settled_is_kept_and_named(tmp_path):
    # sprout-being 10-28: "Do I need to install libv4l to use v4l2-ctl?" (s6), later "Does v4l2-ctl need libv4l
    # installed on the seat?" (s9): one conclusion settled twice, both shown every beat
    _s(tmp_path, question="Do I need to install the test gizmo driver to use gizmoctl?", answer="no")
    _s(tmp_path, question="what colour is the test sky?", answer="blue")
    ok, msg, changed = _s(tmp_path, question="Does gizmoctl need the test gizmo driver installed?", answer="no, it is there")
    assert ok and changed and "s3" in msg
    assert "reads close to s1" in msg and "settle id=s1" in msg and "reopen s3" in msg
    assert len(st.read(tmp_path)[0]) == 3, "named, never merged: the being decides whether they are one"
    ok, msg, _ = _s(tmp_path, question="how loud is the test fan?", answer="quiet")
    assert ok and "reads close" not in msg


def test_two_questions_about_one_device_are_not_named_close(tmp_path):
    # cbp's and mcnugget's reviews of #584: a shared device or file name scored 1.0, so on a camera being
    # nearly every new settle would have been told to keep one
    _s(tmp_path, question="what resolutions does /dev/video0 support?", answer="640x480")
    ok, msg, _ = _s(tmp_path, question="is /dev/video0 owned by the video group?", answer="yes")
    assert ok and "reads close" not in msg
    _s(tmp_path, question="why did capture_frame.py stop at line 16?", answer="no scratch dir")
    ok, msg, _ = _s(tmp_path, question="where does capture_frame.py write its jpg?", answer="scratch/")
    assert ok and "reads close" not in msg


def test_the_named_way_to_keep_one_works_in_its_order_even_with_the_newer_wording(tmp_path):
    # cbp's review of #584: settling s1 first with s3's wording as question was refused as a duplicate of s3
    _s(tmp_path, question="Do I need to install the test gizmo driver to use gizmoctl?", answer="no")
    _s(tmp_path, question="what colour is the test sky?", answer="blue")
    newer = "Does gizmoctl need the test gizmo driver installed?"
    ok, msg, _ = _s(tmp_path, question=newer, answer="no, it is there")
    assert "reopen s3, then settle id=s1" in msg
    ok, _, changed = _s(tmp_path, id="s3", reopen="true")
    assert ok and changed
    ok, msg, changed = _s(tmp_path, id="s1", question=newer, answer="no, it is there")
    assert ok and changed, msg
    assert sorted(e["id"] for e in st.read(tmp_path)[0]) == ["s1", "s2"]
