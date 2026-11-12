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


def test_a_question_spelled_with_another_hyphen_is_the_same_question(tmp_path):
    # These spellings must reuse one settled entry.
    ok, msg, _ = _s(tmp_path, question="What prevents tool calls after context window fills?", answer="first")
    assert ok and "s1" in msg
    for spelled in ("what prevents tool calls after context-window fills", "What prevents tool calls after context‑window fills?"):
        ok, msg, _ = _s(tmp_path, question=spelled, answer=f"again: {spelled[-20:]}")
        assert ok, msg
    entries, _, err = st.read(tmp_path)
    assert err is None and [e["id"] for e in entries] == ["s1"], entries


def test_an_id_changes_or_reopens_one_and_a_reopened_one_is_no_longer_shown(tmp_path):
    _s(tmp_path, question="q one", answer="a one")
    _s(tmp_path, question="q two", answer="a two")
    ok, _, _ = _s(tmp_path, id="s1", question="q one", answer="a one, revised")
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
    assert "(\u00abquestion 0\u00bb, " in msg, msg  # the longest held are shown copyable (cbp on #676)
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


def test_an_id_for_a_new_question_is_refused_with_the_way_forward(tmp_path):
    # sprout-being 10-29: a new question settled with an id it chose ("cbp-…", then "s20"), told only "no such entry"
    _s(tmp_path, question="q one", answer="a")
    for chosen in ("my-own-id", "s2"):
        ok, msg, _ = _s(tmp_path, id=chosen, question="a new question", answer="an answer")
        assert not ok and "no settled entry" in msg and "without id" in msg, msg
    ok, msg, _ = _s(tmp_path, id="s9", answer="a")             # no question: changing, not creating, so no hint
    assert not ok and "without id" not in msg
    assert _s(tmp_path, question="a new question", answer="an answer")[0]


ESCALATE = "When should I escalate a scope request?"


def test_an_id_only_change_is_refused_and_shown_the_question_it_would_answer(tmp_path):
    # cbp-being 10-28..30: s10 kept ESCALATE while id-only settles replaced its answer five times with conclusions
    # about other things (a daemon status, a unit-file fix). Every beat then showed the question with a wrong answer.
    _s(tmp_path, question=ESCALATE, answer="only when a request is refused")
    ok, msg, changed = _s(tmp_path, id="s1", answer="The daemon is running but egress-locked; wait, then restart it.")
    assert not ok and not changed
    assert ESCALATE in msg and "id=s1 with that question" in msg and "without id" in msg, msg
    assert st.read(tmp_path)[0][0]["answer"] == "only when a request is refused"
    assert len(_log(tmp_path)) == 1


def test_an_id_with_its_own_question_still_changes_the_answer(tmp_path):
    _s(tmp_path, question=ESCALATE, answer="only when a request is refused")
    ok, msg, changed = _s(tmp_path, id="s1", question=ESCALATE, answer="when refused, after the appeal")
    assert ok and changed, msg
    assert st.read(tmp_path)[0][0]["answer"] == "when refused, after the appeal"


def test_an_id_with_a_different_question_is_refused_with_the_way_to_settle_it_new(tmp_path):
    _s(tmp_path, question=ESCALATE, answer="only when a request is refused")
    ok, msg, _ = _s(tmp_path, id="s1", question="Is the egress lock held by the daemon?", answer="no")
    assert not ok and "reads as a different question" in msg and "without id" in msg, msg
    assert st.read(tmp_path)[0][0]["question"] == ESCALATE


def test_reopen_by_id_alone_still_works(tmp_path):
    _s(tmp_path, question=ESCALATE, answer="a")
    ok, msg, changed = _s(tmp_path, id="s1", reopen="true")
    assert ok and changed and "reopened s1" in msg


def test_a_full_list_names_what_to_reopen_and_never_advises_folding(tmp_path):
    for i in range(st.MAX_ENTRIES):
        assert _s(tmp_path, question=f"question {i} about lamps", answer="a")[0]
    ok, msg, _ = _s(tmp_path, question="What colour is the sky at dusk?", answer="b")
    assert not ok and "fold" not in msg and "settling that id with a new answer" not in msg
    assert "reopen" in msg and "s1 (" in msg and "different question" in msg, msg


def test_a_hyphenated_name_and_its_spaced_spelling_read_close_and_the_receipt_quotes_the_earlier_answer(tmp_path):
    # sprout-being 11-07: s100 and s101 asked one question, the seat's name spaced in one and hyphenated in the
    # other, with opposite answers 2.5 h apart; the hyphenated name was one word, so they scored 0.0 and the
    # receipt for s101 named nothing.
    _s(tmp_path, question="Is the test gizmo running? How do I check if it's alive?",
       answer="it is not a long-running service; each message wakes a fresh one")
    _s(tmp_path, question="what colour is the test sky?", answer="blue")
    ok, msg, _ = _s(tmp_path, question="Is test-gizmo running?", answer="no, the probe finds nothing")
    assert ok and "reads close to s1" in msg
    assert "s1 (settled 1970-01-01) says 'it is not a long-running service" in msg, msg
    assert "reopen s3, then settle id=s1" in msg
    assert len(st.read(tmp_path)[0]) == 3, "named, never merged"


def test_a_word_and_its_plain_ending_read_close(tmp_path):
    _s(tmp_path, question="How to restart the gizmo daemon without sudo?", answer="there is no way")
    ok, msg, _ = _s(tmp_path, question="Can the gizmo daemon be restarted without sudo privileges?", answer="yes")
    assert ok and "reads close to s1" in msg


def test_the_two_parts_of_one_name_are_one_shared_word(tmp_path):
    # in sprout's settled log, a hyphenated seat name split into two shared words linked a question about one
    # script's run to a question about restarting the seat
    _s(tmp_path, question="How can gizmo-daemon be restarted?", answer="it cannot")
    ok, msg, _ = _s(tmp_path, question="Did gizmo-daemon read the lamp file?", answer="yes")
    assert ok and "reads close" not in msg, msg


def test_every_beat_marks_entries_that_read_close_and_leaves_the_rest_unmarked(tmp_path):
    _s(tmp_path, question="Is the test gizmo running? How do I check if it's alive?", answer="yes, it wakes per message")
    _s(tmp_path, question="what colour is the test sky?", answer="blue")
    _s(tmp_path, question="Is test-gizmo running?", answer="no")
    shown = st.render(tmp_path)
    assert "[s3 ≈s1] Is test-gizmo running?" in shown, shown
    assert "[s1 ≈s3] Is the test gizmo running?" in shown
    assert "[s2] what colour" in shown
    assert "≈ after an id" in shown, "the block says once what the mark means"
    assert "[s3 ≈s1]" in st.listing(tmp_path)
    # nothing reads close: no mark, no explanation
    other = tmp_path / "other"
    other.mkdir()
    _s(other, question="what colour is the test sky?", answer="blue")
    _s(other, question="how loud is the test fan?", answer="quiet")
    assert "≈" not in st.render(other)


def test_the_mark_names_the_oldest_then_the_newest_and_counts_the_rest(tmp_path):
    # among other subjects, as on sprout (10 of 23 entries on its seat): rarity weighting fades a subject that
    # is the whole list
    for q in ("what colour is the test sky?", "how loud is the test fan?", "where is the lamp file kept?",
              "what does listening mean here?", "which port does the hub use?"):
        _s(tmp_path, question=q, answer="x")
    for w in ("now", "without sudo", "when it dies", "from a script", "after the guard"):
        _s(tmp_path, question=f"how to restart the gizmo daemon {w}?", answer="no")
    shown = st.render(tmp_path)
    # the oldest first, then the newest (cbp's review of #661)
    assert "[s6 ≈s7,s10,s9+1]" in shown, shown


def test_plurals_meet_and_running_stays_apart_from_run(tmp_path):
    # pub's review of #661: services->servic and process->proces kept the seat's own words apart
    _s(tmp_path, question="Is the gizmo service up?", answer="yes")
    _s(tmp_path, question="what colour is the test sky?", answer="blue")
    ok, msg, _ = _s(tmp_path, question="Which gizmo services are up here?", answer="one")
    assert ok and "reads close to s1" in msg, msg
    # running stays apart from run: on the seat, "is it running" and "did the script run" are two questions
    stems = {w: st._stem(w) for w in ("running", "run", "runs", "service", "services", "process", "processes",
                                      "escalate", "escalated", "restore", "restored", "tries")}
    assert stems["running"] != stems["run"] == stems["runs"]
    for a, b in (("service", "services"), ("process", "processes"), ("escalate", "escalated"), ("restore", "restored")):
        assert stems[a] == stems[b], (a, b, stems)
    assert stems["tries"] == "try"


def test_the_id_guard_is_mains_predicate_and_never_admits_a_question_on_the_same_subject_only(tmp_path):
    # cbp's and legion's reviews of #661: the guard decides whether an answer goes under an existing question
    _s(tmp_path, question="When should I escalate a gizmo ticket?", answer="when it is still open")
    ok, msg, _ = _s(tmp_path, id="s1", question="Which gizmo tickets were escalated last week?", answer="two")
    assert not ok and "reads as a different question" in msg, msg
    _s(tmp_path, question="Is gizmo-seat running?", answer="yes, it wakes per message")
    ok, msg, _ = _s(tmp_path, id="s2", question="How can gizmo seat be restarted?", answer="run the script")
    assert not ok and "reads as a different question" in msg, msg
    ok, msg, _ = _s(tmp_path, id="s2", question="gizmo-seat running?", answer="yes")
    assert ok, msg
    # saying MORE narrows the question (pub's re-review of #661): refused
    ok, msg, _ = _s(tmp_path, id="s2", question="Is gizmo-seat running on legion?", answer="no")
    assert not ok and "reads as a different question" in msg, msg


def test_the_id_guard_refuses_a_question_on_the_same_words_that_asks_something_else(tmp_path):
    # a hub-fired sprout session's table on #661: on main, "When does a gizmo ticket expire?" was ADMITTED as
    # cbp-being's s10 (only the plural was refused, for want of stemming); both spellings are pinned here
    _s(tmp_path, question="When should I escalate a gizmo ticket?", answer="when it is still open")
    for other in ("When does a gizmo ticket expire?", "When do gizmo tickets expire?",
                  "When should a gizmo ticket expire?", "Which gizmo tickets were escalated last week?"):
        ok, msg, _ = _s(tmp_path, id="s1", question=other, answer="x")
        assert not ok and "reads as a different question" in msg, (other, msg)
    ok, msg, _ = _s(tmp_path, id="s1", question="When should gizmo tickets be escalated?", answer="while open")
    assert ok, msg
    # how vs whether
    _s(tmp_path, question="Does the gizmo daemon need to be restarted?", answer="no")
    ok, msg, _ = _s(tmp_path, id="s2", question="How to restart the gizmo daemon?", answer="run the script")
    assert not ok and "reads as a different question" in msg, msg
    assert [e["answer"] for e in st.read(tmp_path)[0]] == ["while open", "no"], "no answer moved"


def test_an_id_copied_from_the_block_with_its_mark_names_the_entry(tmp_path):
    _s(tmp_path, question="Is the test gizmo running? How do I check if it's alive?", answer="yes")
    _s(tmp_path, question="what colour is the test sky?", answer="blue")
    _s(tmp_path, question="Is test-gizmo running?", answer="no")
    ok, msg, _ = _s(tmp_path, id="[s3 \u2248s1]", reopen="true")
    assert ok and "reopened s3" in msg, msg


def test_the_marks_are_mutual_when_one_spelling_is_hyphenated(tmp_path):
    # cbp's review of #661: counted from the query side only, the spaced question marked the hyphenated one
    # and not back
    for q in ("How can gizmo-daemon be restarted?", "Did the gizmo daemon read the lamp file?",
              "what colour is the test sky?", "how loud is the test fan?"):
        _s(tmp_path, question=q, answer="x")
    assert st._neighbours(st.read(tmp_path)[0]) == {}
    other = tmp_path / "o"
    other.mkdir()
    for q in ("Did the gizmo daemon read the lamp file?", "How can gizmo-daemon be restarted?",
              "what colour is the test sky?", "how loud is the test fan?"):
        _s(other, question=q, answer="x")
    assert st._neighbours(st.read(other)[0]) == {}


def test_following_the_receipt_keeps_the_answer_that_holds(tmp_path):
    # legion's review of #661: "settle id=s1 with your newest answer", followed literally, put the false answer
    # in place of the true one
    _s(tmp_path, question="Is the test gizmo running? How do I check if it's alive?", answer="it wakes per message")
    _s(tmp_path, question="what colour is the test sky?", answer="blue")
    _s(tmp_path, question="where does the lamp file live?", answer="notes/")
    ok, msg, _ = _s(tmp_path, question="Is test-gizmo running?", answer="no, the probe finds nothing")
    assert "with the answer that holds" in msg and "newest answer" not in msg, msg
    assert "Your earlier answer:" in msg


def test_a_short_line_keeps_its_question_readable_and_the_block_stays_in_budget(tmp_path):
    # legion's review of #661: at every field cap with 3-digit ids and all linked, the block passed RENDER_CHARS
    # and a short line showed 8 chars of its question
    (tmp_path / st.SETTLED_FILE).write_text(json.dumps({"next": 131, "entries": [
        {"id": f"s{101 + i}", "question": (f"Can the gizmo daemon be restarted, case {i}? " + "w" * 200)[:st.QUESTION_MAX_CHARS],
         "answer": "a" * st.ANSWER_MAX_CHARS, "evidence": "e" * st.EVIDENCE_MAX_CHARS, "at": "2026-11-09T00:00:00Z"}
        for i in range(st.MAX_ENTRIES)]}))
    assert st._neighbours(st.read(tmp_path)[0]), "the fixture links"
    shown = st.render(tmp_path)
    assert len(shown) <= st.RENDER_CHARS, len(shown)
    for ln in shown.splitlines():
        if ln.startswith("- [s") and " -> " not in ln:
            q = ln.split("] ", 1)[1].rsplit(" (settled", 1)[0]
            assert len(q) >= min(st.SHORT_QUESTION_FLOOR, 20) or q.endswith("…") and len(q) >= 8, ln



def test_the_full_list_refusal_quotes_the_close_answer_and_asks_for_the_one_that_holds(tmp_path):
    # legion on #661: at the cap the refusal still said "your newest answer"; following it on the s100/s101
    # shape replaced the true answer with the false one
    _s(tmp_path, question="Is the test gizmo running? How do I check if it's alive?", answer="it wakes per message")
    for i in range(st.MAX_ENTRIES - 1):
        assert _s(tmp_path, question=f"filler {i} about lamps", answer="a")[0]
    ok, msg, _ = _s(tmp_path, question="Is test-gizmo running?", answer="no, the probe finds nothing")
    assert not ok and "reads close to s1" in msg, msg
    assert "'it wakes per message'" in msg and "the answer that holds" in msg and "newest" not in msg, msg


def test_a_true_rewording_refused_by_the_guard_has_a_route_that_works(tmp_path):
    # cbp's re-review of #661: receipt -> reopen -> id= with its own wording -> refused -> settle new -> receipt,
    # and nothing on the way said that the exact question is what goes through
    held = "Is the test gizmo running? How do I check if it's alive?"
    _s(tmp_path, question=held, answer="it wakes per message")
    _s(tmp_path, question="what colour is the test sky?", answer="blue")
    _s(tmp_path, question="where does the lamp file live?", answer="notes/")
    ours = "Is test-gizmo running on the lamp host today?"
    ok, msg, _ = _s(tmp_path, question=ours, answer="it wakes per message, on the lamp host too")
    assert ok and f"settle id=s1, question \u00ab{held}\u00bb word for word" in msg, msg
    assert _s(tmp_path, id="s4", reopen="true")[0]
    ok, msg, _ = _s(tmp_path, id="s1", question=ours, answer="it wakes per message, on the lamp host too")
    assert not ok and "If it IS the same question, settle id=s1 with its question exactly as above" in msg, msg
    assert f"\u00ab{held}\u00bb" in msg, msg
    ok, msg, _ = _s(tmp_path, id="s1", question=held, answer="it wakes per message, on the lamp host too")
    assert ok, msg
    kept = {e["id"]: e for e in st.read(tmp_path)[0]}
    assert kept["s1"]["question"] == held and kept["s1"]["answer"].endswith("lamp host too") and "s4" not in kept


def test_a_question_at_its_longest_is_quoted_whole_where_it_is_to_be_copied(tmp_path):
    # the question holds 200 characters; quotes cut at 120 and 160 could not be copied back word for word
    held = ("Is the test gizmo running? " + "How do I check that the gizmo daemon is alive on this host? " * 4)[:st.QUESTION_MAX_CHARS]
    _s(tmp_path, question=held, answer="it wakes per message")
    _s(tmp_path, question="what colour is the test sky?", answer="blue")
    _s(tmp_path, question="where does the lamp file live?", answer="notes/")
    ok, msg, _ = _s(tmp_path, id="s1", answer="still")
    assert not ok and f"\u00ab{held}\u00bb" in msg, msg
    ok, msg, _ = _s(tmp_path, id="s1", question="Why is the sky lamp blue?", answer="still")
    assert not ok and f"\u00ab{held}\u00bb" in msg, msg
    ok, msg, _ = _s(tmp_path, question="Is the test gizmo daemon alive on this host?", answer="yes")
    assert ok and f"question \u00ab{held}\u00bb word for word" in msg, msg
    assert _s(tmp_path, id="s4", reopen="true")[0]
    for i in range(st.MAX_ENTRIES - 3):
        assert _s(tmp_path, question=f"filler {i} about lamps", answer="a")[0]
    ok, msg, _ = _s(tmp_path, question="Is the test gizmo daemon alive on this host?", answer="yes")
    assert not ok and f"(\u00ab{held}\u00bb)" in msg, msg


def test_the_id_guard_refuses_a_different_name_or_number_and_admits_saying_less(tmp_path):
    # cbp's re-review of #661. The k=1/k=2 row is the shape of a real settle (cbp s319, 11-06)
    for target, given in (("Does /dev/video0 exist?", "Does /dev/video1 exist?"),
                          ("Did check-a.py pass?", "Did check-b.py pass?"),
                          ("What is the k=2 test error?", "What is the k=1 test error?")):
        assert not st._same_question({"question": target}, given), (target, given)
    for target, given in (("Does /dev/video0 exist?", "Does it exist?"),
                          ("Does /dev/video0 respond on the lamp host?", "Does /dev/video0 respond on the host?"),
                          ("Is the test gizmo running? How do I check if it's alive?", "Is test-gizmo running?")):
        assert st._same_question({"question": target}, given), (target, given)


def test_a_question_with_quote_marks_or_a_backslash_is_copied_back_as_written(tmp_path):
    # cbp's re-check of #661: repr() escaped the question to copy, and the copy was stored with backslashes
    held = 'Does the "test" gizmo\'s path C:\\lamp work?'
    _s(tmp_path, question=held, answer="yes")
    ok, msg, _ = _s(tmp_path, id="s1", answer="still")
    shown = msg.split("\u00ab", 1)[1].split("\u00bb", 1)[0]
    assert shown == held, (shown, held)
    ok, msg, _ = _s(tmp_path, id="s1", question=shown, answer="still yes")
    assert ok and st.read(tmp_path)[0][0]["question"] == held, msg
    # a copy that keeps the delimiters is the same question
    ok, msg, _ = _s(tmp_path, id="s1", question="\u00ab" + held + "\u00bb", answer="yes again")
    assert ok and st.read(tmp_path)[0][0]["question"] == held, msg


def test_a_copy_that_carries_the_period_or_outer_quotes_is_stored_without_guillemets(tmp_path):
    # cbp's re-check of #661: a copy taking the receipt's following period, or wrapped in quote marks, stored the
    # guillemets, and they nested on the next copy
    held = "Is the gizmo lamp on?"
    _s(tmp_path, question=held, answer="yes")
    # and the ( ) the cap receipt prints around it (cbp on #676)
    for copy in ("\u00ab" + held + "\u00bb.", '"\u00ab' + held + '\u00bb"', "  \u00ab" + held + "\u00bb ;",
                 "(\u00ab" + held + "\u00bb)", "\u00ab" + held + "\u00bb),"):
        ok, msg, _ = _s(tmp_path, id="s1", question=copy, answer="yes, " + copy[:3])
        assert ok, msg
        assert st.read(tmp_path)[0][0]["question"] == held, st.read(tmp_path)[0][0]["question"]


def test_a_paren_inside_the_question_is_kept(tmp_path):
    # the match is anchored on the guillemets: only the ( ) outside them are the receipt's
    held = "Is the lamp (the gizmo one) on?"
    _s(tmp_path, question=held, answer="yes")
    ok, msg, _ = _s(tmp_path, id="s1", question="(\u00ab" + held + "\u00bb)", answer="yes again")
    assert ok and st.read(tmp_path)[0][0]["question"] == held, msg


def test_the_replace_receipt_shows_the_question_copyable(tmp_path):
    # cbp on #676: the receipt read right after keep-one was still repr-escaped
    held = 'Does "it" hold?'
    _s(tmp_path, question=held, answer="yes")
    ok, msg, _ = _s(tmp_path, id="s1", question=held, answer="no")
    assert ok and "\u00ab" + held + "\u00bb" in msg, msg


def test_an_entry_naming_a_process_number_gets_the_runs_numbering_beside_it_in_the_block(tmp_path):
    # sprout-being 11-05..12: 13 of 170 settled answers cited a PID that a listing inside a run gave (its user id,
    # or pgrep's own shell), both ways about whether its seat was alive; s140 headed the block at a relapse
    import os
    uid = str(os.getuid())
    _s(tmp_path, question="Is the test gizmo running?", answer=f"yes, PID {uid} on port 9")
    _s(tmp_path, question="what colour is the test sky?", answer="blue")
    _s(tmp_path, question="Does the gizmo restart itself?", answer="yes (PID 3), at boot")
    shown = st.render(tmp_path)
    assert "(s3, s1 name a process number." in shown, shown
    assert "numbers its own processes from 1" in shown and "finds that shell or that grep itself" in shown
    assert f"{uid} at the start of a ps line there is the run's user id" in shown
    assert "says nothing about a process on this machine, running or not" in shown
    # the entries themselves are untouched: the harness never rewords one
    assert "yes (PID 3), at boot" in shown and "s2 name" not in shown


def test_no_process_number_no_fact_and_no_uid_clause_without_the_uid(tmp_path):
    _s(tmp_path, question="what colour is the test sky?", answer="blue")
    assert "process number" not in st.render(tmp_path)
    _s(tmp_path, question="Is the test gizmo running?", answer="yes, pid: 48213")
    shown = st.render(tmp_path)
    assert "(s2 names a process number." in shown and "user id" not in shown, shown


def test_settling_an_answer_with_a_process_number_says_where_such_numbers_come_from(tmp_path):
    ok, msg, changed = _s(tmp_path, question="Is the test gizmo running?", answer="Running (PID 3).")
    assert ok and changed and "This answer names a process number." in msg, msg
    ok, msg, changed = _s(tmp_path, question="Is the test gizmo running?", answer="Running (PID 3).")
    assert not changed and "process number" not in msg       # unchanged: nothing new to say
    ok, msg, _ = _s(tmp_path, question="what colour is the test sky?", answer="blue")
    assert "process number" not in msg


def test_the_block_stays_in_budget_when_every_entry_names_a_process_number(tmp_path):
    (tmp_path / st.SETTLED_FILE).write_text(json.dumps({"next": 131, "entries": [
        {"id": f"s{101 + i}", "question": (f"Can the gizmo daemon be restarted, case {i}? " + "w" * 200)[:st.QUESTION_MAX_CHARS],
         "answer": ("PID 2002 " + "a" * st.ANSWER_MAX_CHARS)[:st.ANSWER_MAX_CHARS],
         "evidence": "e" * st.EVIDENCE_MAX_CHARS, "at": "2026-11-09T00:00:00Z"}
        for i in range(st.MAX_ENTRIES)]}))
    shown = st.render(tmp_path)
    assert len(shown) <= st.RENDER_CHARS, len(shown)
    assert "(s130, s129, s128, s127 +26 name a process number." in shown, shown[:900]
