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
    assert "replies to" not in out, "adjacency is not a reply; nothing asserts one"
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
    ac = hb.LAST_ANSWER_CONTEXT
    assert ac["arm"] == "gist" and q in [e["seq"] for e in ac["listed"]]
    assert ac["linked"] is False and ac["chars"] <= hb.ANSWER_CONTEXT_CHARS
    assert ac["delivered_reflect"] is False and ac["delivered_answer"] is False, "set only where sent"


def test_reflect_is_unchanged_without_the_setting():
    inst, q = _the_1126_case()
    _line, block, _first, _target, sel = pending_selection(inst, ME)
    assert f"seq {q}" not in block.replace(f"dp seq {q}", "") and sel.context == ""


def _pa(inst, cid="dp"):
    return conv.prior_ask(inst, cid, ME, conv.recent(inst, cid, 1)[-1], turn_expects_reply)


def test_a_being_turn_that_asked_nothing_has_no_prior_ask():
    inst = _inst()
    _say(inst, ME, "I finished the census today.")
    _say(inst, "dp", "nice work")
    assert _pa(inst) is None


def test_a_request_run_result_has_no_prior_ask():
    inst = _inst()
    _say(inst, ME, "Can you look at seq 1?")
    _say(inst, "dp", "[request_run] scratch/x.py exited 0")
    assert _pa(inst) is None


def test_an_unrelated_statement_is_listed_as_adjacent_never_as_a_reply():
    inst = _inst("gist")
    _say(inst, "dp", "hi")
    _say(inst, ME, "Which folder should I use? " + "x " * 80)
    _say(inst, ME, "ping")
    _say(inst, ME, "Any answer to seq 2?")
    _say(inst, "dp", "fyi the server restarts tonight")
    pa = _pa(inst)
    assert pa is not None and pa["linked"] is False
    out = _render(inst)
    assert "- seq 2 " in out and "your seq 4 names it" in out and "replies to" not in out
    ents = conv.prior_ask_entries(pa, 5)
    assert ents[0]["why"] == "your last ask before seq 5", "adjacency, said as adjacency"


def test_an_explicit_answers_link_is_said_as_one():
    inst = _inst()
    _say(inst, ME, "Which folder?")
    conv.append(inst, "dp", speaker="dp", text="the archive one", extra={"answers": [1]})
    pa = _pa(inst)
    assert pa is not None and pa["linked"] is True
    assert "names it as answered" in conv.prior_ask_entries(pa, 2)[0]["why"]


def test_a_voice_line_gets_nothing_in_either_path():
    inst, _q = _the_1126_case(directory="gist")
    conv.append(inst, "dp", speaker="dp", text="tv noise about decisions", via="voice")
    assert _pa(inst) is None
    out = _render(inst)
    assert "your last ask before" not in out
    _line, block, _first, _target, _sel = pending_selection(inst, ME)
    assert "your last ask before" not in block


def test_a_third_speaker_in_between_breaks_adjacency():
    inst = Path(tempfile.mkdtemp(prefix="sg4-3p-"))
    conv.create(inst, "room", title="three", participants=["dp", "cbp-claude", ME],
                writable_by=["dp", "cbp-claude", ME], summary="")
    _say(inst, ME, "Which folder should I use?", cid="room")
    _say(inst, "cbp-claude", "I ran the census.", cid="room")
    _say(inst, "dp", "your call", cid="room")
    assert _pa(inst, "room") is None, "the seat spoke first; nothing says whose question dp takes up"


def test_the_full_arm_is_verbatim():
    inst = _inst()
    body = "Line one:\n  1. Which folder?\n\n  2. Which   script?\n" + "pad " * 40
    _say(inst, ME, body)
    _say(inst, ME, "x")
    _say(inst, ME, "Answer to seq 1?")
    _say(inst, "dp", "decide")
    out = _render(inst, directory="full")
    stored = conv.recent(inst, "dp", 10)[0]["text"]      # the store trims the turn's outer whitespace
    assert "  2. Which   script?" in stored
    assert "\n".join("    " + ln for ln in stored.split("\n")) in out, "the stored turn, nothing collapsed"


def test_reflect_context_is_held_under_its_ceiling():
    from sage.gateway import heartbeat as hb
    inst = _inst("full")
    _say(inst, ME, "A " + "very long question " * 200 + "?")
    a = _seqs(inst)[-1]
    _say(inst, ME, "B " + "another long one " * 200 + "?")
    b = _seqs(inst)[-1]
    _say(inst, ME, f"Answers to seq {a} and seq {b}?")
    _say(inst, "dp", "decide")      # seq 4, even -> but mode is full, not ab
    _line, block, _f, _t, sel = pending_selection(inst, ME)
    ac = hb.LAST_ANSWER_CONTEXT
    assert ac["chars"] <= hb.ANSWER_CONTEXT_CHARS and len(sel.context) == ac["chars"]
    assert ac["verbatim_cap"] < conv.CITED_TURN_CHARS, "the verbatim cut stepped down, the lines stayed"
    assert f"start_line {a}" in sel.context and f"start_line {b}" in sel.context


def test_delivery_is_what_reached_the_prompt():
    rec = [{"cid": "dp", "arm": "gist", "listed": [{"seq": 7, "line": 3, "kind": "cited"},
                                                   {"seq": 9, "line": 5, "kind": "unanswered"}]}]
    sent = "... " + conv.open_handle("dp", 3) + " ..."
    marked = conv.mark_delivered(rec, sent)
    assert [e["delivered"] for e in marked[0]["listed"]] == [True, False]
    assert [e["delivered"] for e in conv.mark_delivered(rec, "")[0]["listed"]] == [False, False]


def test_a_seq_named_for_another_conversation_is_not_resolved_here():
    inst = _inst()
    conv.create(inst, "cbp-claude", title="seat", participants=["cbp-claude", ME],
                writable_by=["cbp-claude", ME], summary="")
    _say(inst, "dp", "first")
    _say(inst, ME, "What did cbp-claude seq 1 mean?")
    _say(inst, "dp", "ask the seat")
    pa = _pa(inst)
    assert pa["ask"]["text"] == "What did cbp-claude seq 1 mean?" and pa["cited"] == []


def test_a_seq_older_than_the_recent_window_is_still_found():
    inst = _inst()
    _say(inst, ME, "Old questions: which folder?")
    q = _seqs(inst)[-1]
    for i in range(210):
        _say(inst, "dp", f"filler {i}")
    _say(inst, ME, f"What is the answer to seq {q}?")
    _say(inst, "dp", "your call")
    assert f"- seq {q} " in _render(inst)


# ---- NOVA's third review of #836 ----------------------------------------------------------------------

def _rolled_back_case():
    """Seqs 1-5, the file truncated to its first line (the store keeps its seq high-water mark), then the
    being's questions, its pointer and the operator's answer: physical seqs [1, 6, 7, 8] on lines 1-4."""
    inst = _inst("gist")
    for i in range(5):
        _say(inst, "dp" if i % 2 == 0 else ME, f"turn {i}")
    log = inst / "conversations" / "dp.jsonl"
    log.write_text(log.read_text().splitlines(keepends=True)[0])
    _say(inst, ME, QUESTIONS)
    _say(inst, ME, "What is the answer to dp seq 6?")
    _say(inst, "dp", "your call")
    return inst, log


def test_a_read_handle_names_the_physical_line_after_a_rollback():
    inst, log = _rolled_back_case()
    seqs = [t["seq"] for t in conv.recent(inst, "dp", 100)]
    if seqs != [1, 6, 7, 8]:
        import pytest
        pytest.skip(f"this store build did not keep the high-water mark here: {seqs}")
    out = _render(inst)
    assert "- seq 6 " in out, out
    assert conv.open_handle("dp", 2) in out, "seq 6 is on line 2"
    assert "start_line 6" not in out, "a seq is not a line: line 6 is past the end of a 4-line file"
    lines = log.read_text().splitlines()
    assert json.loads(lines[2 - 1])["seq"] == 6
    rec = conv.LAST_DIRECTORY[(2, 700)]
    assert rec[0]["listed"][0]["seq"] == 6 and rec[0]["listed"][0]["line"] == 2


def test_the_reflect_block_handle_is_the_physical_line_too():
    inst, _log = _rolled_back_case()
    if [t["seq"] for t in conv.recent(inst, "dp", 100)] != [1, 6, 7, 8]:
        import pytest
        pytest.skip("no high-water mark in this build")
    from sage.gateway import heartbeat as hb
    _line, _block, _f, _t, sel = pending_selection(inst, ME)
    assert conv.open_handle("dp", 3) in sel.context, "the being's pointer (seq 7) is on line 3"
    assert hb.LAST_ANSWER_CONTEXT["listed"][0] == {"seq": 7, "line": 3, "kind": "prior_ask"}


def test_a_digit_leading_foreign_conversation_id_is_not_resolved_here():
    assert conv._cited_seqs("What did 4-lab seq 1 mean?", "dp", {"4-lab"}, 10) == []
    assert conv._cited_seqs("What did 4-Lab seq 1 mean?", "dp", {"4-lab"}, 10) == [], "case-insensitive"
    assert conv._cited_seqs("What did cbp-claude seq 1 mean?", "dp", {"cbp-claude"}, 10) == []
    assert conv._cited_seqs("the answer to dp seq 1?", "dp", {"4-lab"}, 10) == [1], "this conversation's own"
    inst = _inst()
    conv.create(inst, "4-lab", title="lab", participants=["lab", ME], writable_by=["lab", ME], summary="")
    _say(inst, "dp", "first")
    _say(inst, ME, "What did 4-lab seq 1 mean?")
    _say(inst, "dp", "ask the lab")
    assert _pa(inst)["cited"] == []


def test_a_short_multiline_ask_is_verbatim_in_the_full_arm():
    inst = _inst()
    body = "Before I continue:\n  1. Which folder?\n\n  2. Which   script?"
    _say(inst, ME, body)
    _say(inst, ME, "x")
    _say(inst, ME, "Answer to seq 1?")
    _say(inst, "dp", "decide")
    out = _render(inst, directory="full")
    stored = conv.recent(inst, "dp", 10)[0]["text"]
    assert len(" ".join(stored.split())) <= conv.GIST_CHARS, "short enough to fit the gist"
    assert "\n".join("    " + ln for ln in stored.split("\n")) in out, "its line breaks and spacing kept"
    flat = "Before I continue: 1. Which folder? 2. Which script? done"
    inst2 = _inst()
    _say(inst2, ME, flat)
    _say(inst2, ME, "x")
    _say(inst2, ME, "Answer to seq 1?")
    _say(inst2, "dp", "decide")
    out2 = _render(inst2, directory="full")
    assert "    " + flat not in out2, "a short one-line turn loses nothing in the gist, so it isn't repeated"


def test_prompt_reached_model_is_what_the_server_answered():
    from types import SimpleNamespace as NS
    from sage.gateway.heartbeat import prompt_reached_model as reached
    assert not reached(None), "a phase that never ran"
    assert not reached(NS(seed_measured=None, generates=[])), "yielded before its first generate"
    assert not reached(NS(seed_measured=None, generates=[{"window_full": "preflight", "estimated_prompt": 9}]))
    assert not reached(NS(seed_measured=None, generates=[{"window_full": "server_cut", "prompt_eval_count": 4000}]))
    assert reached(NS(seed_measured=(9000, 30000), generates=[]))
    assert reached(NS(seed_measured=None, generates=[{"done_reason": "stop", "prompt_eval_count": None}]))
