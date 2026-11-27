"""Hermetic: SG4's conversation slice. A window cut leaves an openable line, not a count.

Measured on cbp-being 2026-11-26. It asked the operator four questions in one turn (seq 1248), then
followed up five times, the last a one-line pointer asking for the answer to seq 1248 (seq 1256). The
operator answered at seq 1257, handing the decisions back to the being. The beat ran at the sparsest
context-fit rung, 2 turns per conversation at 700 chars, so the being saw its pointer and the answer
but not the questions, and the reflect line said only that the operator "replied to what you asked
for". Its reply did not take up the questions, and the next three beats went to an unrelated script.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv  # noqa: E402
from sage.gateway.heartbeat import pending_selection, turn_expects_reply  # noqa: E402

ME = "cbp-being"
QUESTIONS = ("Before I go on: 1. Which folder? 2. All entries or only the old ones? "
             "3. Which script? 4. Should the seat run it? " + "Some context. " * 20 + "TAIL-MARK")


def _inst(directory=None) -> Path:
    inst = Path(tempfile.mkdtemp(prefix="sg4-"))
    if directory:
        (inst / "instance.json").write_text(json.dumps({"conversation_directory": directory}))
    conv.create(inst, "dp", title=f"dp and {ME}", participants=["dp", ME], writable_by=["dp", ME], summary="")
    return inst


def _say(inst, who, text, cid="dp"):
    return conv.append(inst, cid, speaker=who, text=text)


def _seqs(inst, cid="dp"):
    return [t["seq"] for t in conv.recent(inst, cid, 100)]


def _the_1126_case(directory=None, answer_parity=0):
    inst = _inst(directory)
    _say(inst, "dp", "how is it going?")
    _say(inst, ME, QUESTIONS)
    q = _seqs(inst)[-1]
    _say(inst, ME, "I'm waiting for your decision.")
    if answer_parity == 0:
        _say(inst, ME, "Still holding.")
    _say(inst, ME, f"What is the answer to dp seq {q}?")
    _say(inst, "dp", "you decide; it is your call.")
    assert _seqs(inst)[-1] % 2 == answer_parity
    return inst, q


def _render(inst, per_conv=2, turn_chars=700, directory="gist"):
    return conv.render_for_being(inst, ME, per_conv=per_conv, turn_chars=turn_chars, mark=False,
                                 asks=turn_expects_reply, directory=directory)


def test_the_sparse_rung_lists_the_questions_with_the_read_that_opens_them():
    inst, q = _the_1126_case()
    out = _render(inst)
    line = [l for l in out.splitlines() if l.startswith(f"- seq {q} ")]
    assert line, "the off-window ask the answer replies to has a line"
    assert "cbp-being (you)" in line[0] and "names it" in line[0]
    assert f"memory_read path conversations/dp.jsonl start_line {q} end_line {q}" in line[0]
    assert "Which folder?" in line[0], "its first words"
    assert "TAIL-MARK" not in out, "gist arm: a line, never the turn spliced in"


def test_the_full_arm_also_shows_the_chain_verbatim():
    inst, q = _the_1126_case()
    out = _render(inst, directory="full")
    assert f"- seq {q} " in out and "TAIL-MARK" in out


def test_ab_assigns_by_the_reply_seq_parity_and_records_it():
    for parity, arm in ((0, "gist"), (1, "full")):
        inst, q = _the_1126_case(answer_parity=parity)
        conv.LAST_DIRECTORY.clear()
        out = _render(inst, directory="ab")
        rec = conv.LAST_DIRECTORY[(2, 700)]
        assert rec[0]["arm"] == arm and rec[0]["cid"] == "dp"
        assert q in [e["seq"] for e in rec[0]["listed"]]
        assert ("TAIL-MARK" in out) == (arm == "full")


def test_off_by_default_and_at_a_full_rung():
    inst, _q = _the_1126_case()
    plain = conv.render_for_being(inst, ME, per_conv=2, turn_chars=700, mark=False)
    assert _render(inst, directory=None) == plain, "no setting, byte-identical block"
    full = conv.render_for_being(inst, ME, per_conv=12, turn_chars=None, mark=False)
    assert _render(inst, per_conv=12, turn_chars=None) == full, "nothing cut, nothing listed"


def test_unanswered_turns_off_the_window_get_lines():
    inst = _inst()
    _say(inst, ME, "ok")
    for i in range(4):
        _say(inst, "dp", f"question number {i}?")
    out = _render(inst)
    assert "- seq 2 " in out and "- seq 3 " in out, "the two dp turns above the window"
    assert "no turn of yours has answered it" in out


def test_lines_are_capped():
    inst = _inst()
    _say(inst, ME, "ok")
    for i in range(12):
        _say(inst, "dp", f"question number {i}?")
    assert sum(l.startswith("- seq ") for l in _render(inst).splitlines()) == conv.DIRECTORY_MAX


def test_the_reflect_block_and_the_answer_turn_list_the_chain():
    inst, q = _the_1126_case(directory="gist")
    _line, block, first, target, sel = pending_selection(inst, ME)
    assert target == "dp" and sel is not None
    assert "dp replied to what you asked for" in first
    assert f"- seq {q} " in block, "the reflect turn has no conversation block; the line rides here"
    assert f"start_line {q}" in sel.render()
    from sage.gateway import heartbeat as hb
    assert hb.LAST_ANSWER_CONTEXT["arm"] == "gist" and q in hb.LAST_ANSWER_CONTEXT["listed"]


def test_reflect_is_unchanged_without_the_setting():
    inst, q = _the_1126_case()
    _line, block, _first, _target, sel = pending_selection(inst, ME)
    assert f"seq {q}" not in block.replace(f"dp seq {q}", "") and sel.context == ""


def test_a_being_turn_that_asked_nothing_has_no_chain():
    inst = _inst()
    _say(inst, ME, "I finished the census today.")
    _say(inst, "dp", "nice work")
    assert conv.what_it_answers(inst, "dp", ME, conv.recent(inst, "dp", 1)[-1], turn_expects_reply) == []


def test_a_request_run_result_has_no_chain():
    inst = _inst()
    _say(inst, ME, "Can you look at seq 1?")
    _say(inst, "dp", "[request_run] scratch/x.py exited 0")
    assert conv.what_it_answers(inst, "dp", ME, conv.recent(inst, "dp", 1)[-1], turn_expects_reply) == []


def test_a_seq_named_for_another_conversation_is_not_resolved_here():
    inst = _inst()
    conv.create(inst, "cbp-claude", title="seat", participants=["cbp-claude", ME],
                writable_by=["cbp-claude", ME], summary="")
    _say(inst, "dp", "first")
    _say(inst, ME, "What did cbp-claude seq 1 mean?")
    _say(inst, "dp", "ask the seat")
    ctx = conv.what_it_answers(inst, "dp", ME, conv.recent(inst, "dp", 1)[-1], turn_expects_reply)
    assert [t["text"] for t in ctx] == ["What did cbp-claude seq 1 mean?"]


def test_a_seq_older_than_the_recent_window_is_still_found():
    inst = _inst()
    _say(inst, ME, "Old questions: which folder?")
    q = _seqs(inst)[-1]
    for i in range(210):
        _say(inst, "dp", f"filler {i}")
    _say(inst, ME, f"What is the answer to seq {q}?")
    _say(inst, "dp", "your call")
    assert f"- seq {q} " in _render(inst)
