"""Hermetic: an answer arrives with the question it answers.

Measured on cbp-being 2026-11-26. It asked the operator four questions in one turn (seq 1248), then
followed up five times, the last a one-line pointer asking for the answer to seq 1248 (seq 1256). The
operator answered at seq 1257, handing the decisions back to the being. The beat ran at the sparsest
context-fit rung, 2 turns per conversation at 700 chars, so the being saw its pointer and the answer
but not the questions, and the reflect line said only that the operator "replied to what you asked
for". Its reply did not take up the questions, and the next three beats went to an unrelated script.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv  # noqa: E402
from sage.gateway.heartbeat import pending_selection, turn_expects_reply  # noqa: E402

ME = "cbp-being"
QUESTIONS = ("Before I go on: 1. Which folder? 2. All entries or only the old ones? "
             "3. Which script? 4. Should the seat run it?")


def _inst() -> Path:
    inst = Path(tempfile.mkdtemp(prefix="answer-ask-"))
    conv.create(inst, "dp", title=f"dp and {ME}", participants=["dp", ME], writable_by=["dp", ME], summary="")
    return inst


def _say(inst, who, text, cid="dp"):
    return conv.append(inst, cid, speaker=who, text=text)


def _seqs(inst, cid="dp"):
    return [t["seq"] for t in conv.recent(inst, cid, 100)]


def _the_1126_case():
    inst = _inst()
    _say(inst, "dp", "how is the inbox going?")
    _say(inst, ME, QUESTIONS)
    q = _seqs(inst)[-1]
    _say(inst, ME, "I'm waiting for your decision on the inbox policy.")
    _say(inst, ME, "Still holding the inbox scripts.")
    _say(inst, ME, f"What is the answer to dp seq {q}?")
    _say(inst, "dp", "you decide; it is your call.")
    return inst, q


def test_the_sparse_rung_shows_the_questions_the_answer_replies_to():
    inst, q = _the_1126_case()
    out = conv.render_for_being(inst, ME, per_conv=2, turn_chars=700, mark=False, asks=turn_expects_reply)
    assert "Which script?" in out, "the questions dp answered are in view at the sparsest rung"
    assert f"which pointed at seq {q}" in out
    assert "**cbp-being (you)**" in out, "the being's own words are labelled as its own"


def test_without_the_asks_test_nothing_is_added():
    inst, _q = _the_1126_case()
    out = conv.render_for_being(inst, ME, per_conv=2, turn_chars=700, mark=False)
    assert "Which script?" not in out, "callers that do not pass asks see the block unchanged"


def test_a_full_rung_pays_nothing():
    inst, _q = _the_1126_case()
    full = conv.render_for_being(inst, ME, per_conv=12, turn_chars=None, mark=False, asks=turn_expects_reply)
    plain = conv.render_for_being(inst, ME, per_conv=12, turn_chars=None, mark=False)
    assert full == plain, "when the ask and what it cites are already shown, nothing is repeated"


def test_the_reflect_block_and_the_answer_turn_carry_the_ask():
    inst, q = _the_1126_case()
    _line, block, first, target, sel = pending_selection(inst, ME)
    assert target == "dp" and sel is not None
    assert "dp replied to what you asked for" in first
    assert "Which script?" in block, "the reflect turn has no conversation block; the ask rides here"
    assert f"What is the answer to dp seq {q}?" in sel.render()
    assert "Which script?" in sel.render(), "the answer phase sees what it is answering"


def test_a_being_turn_that_asked_nothing_pulls_nothing_in():
    inst = _inst()
    _say(inst, ME, "I finished the census today.")
    _say(inst, "dp", "nice work")
    assert conv.what_it_answers(inst, "dp", ME, conv.recent(inst, "dp", 1)[-1], turn_expects_reply) == []


def test_a_request_run_result_pulls_nothing_in():
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


def test_a_long_cited_turn_is_capped_with_where_to_read_it():
    inst = _inst()
    _say(inst, ME, "Questions: " + "x" * 3000 + "?")
    q = _seqs(inst)[-1]
    _say(inst, ME, f"Any answer to seq {q}?")
    _say(inst, "dp", "yes")
    out = conv.render_for_being(inst, ME, per_conv=2, turn_chars=700, mark=False, asks=turn_expects_reply)
    assert "memory_read conversations/dp.jsonl" in out
    assert "x" * (conv.CITED_TURN_CHARS + 50) not in out


def test_a_seq_older_than_the_recent_window_is_still_found():
    inst = _inst()
    _say(inst, ME, "Old questions: which folder?")
    q = _seqs(inst)[-1]
    for i in range(210):
        _say(inst, "dp", f"filler {i}")
    _say(inst, ME, f"What is the answer to seq {q}?")
    _say(inst, "dp", "your call")
    ctx = conv.what_it_answers(inst, "dp", ME, conv.recent(inst, "dp", 1)[-1], turn_expects_reply)
    assert [t["seq"] for t in ctx][1:] == [q]
