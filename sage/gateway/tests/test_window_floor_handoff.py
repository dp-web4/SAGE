"""The automatic window reset (dp, 2026-10-06): at the floor the being is told once, and
FLOOR_HANDOFF_AFTER steps later the harness writes a handoff note and ends the turn so the next
beat starts with an empty window. legion-being 10-05/06: the longest beats retried 30% of their
generates against prompts of 32,1xx-32,7xx of 32,768."""
import os
import time
from types import SimpleNamespace

from sage.gateway import being_tool_loop as btl
from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_being_tool_loop import _client, OK_DISPATCH


def _gen(floor_from=0, steps_out=None):
    n = {"i": 0}

    def gen(convo):
        i = n["i"]; n["i"] += 1
        if steps_out is not None and i >= steps_out:
            return {"content": "done", "intents": []}
        return {"content": f"step {i}", "intents": [BeingIntent("witness", {"event": f"e{i}"})],
                "window": {"prompt": 32000, "num_ctx": 32768, "pressure": 0.97, "left": 768,
                           "floor": i >= floor_from}}
    return gen


def test_at_the_floor_the_being_is_told_once_then_the_harness_hands_off(tmp_path):
    c = _client(OK_DISPATCH)
    c.memory_root = str(tmp_path)
    r = btl.run_tool_turn(c, _gen(floor_from=3), [{"role": "user", "content": "go"}], max_steps=50)
    floor = [i for i in r.interjected if i.get("nudge") == "floor"]
    assert len(floor) == 1 and floor[0]["step"] == 3, r.interjected
    assert r.handoff == btl.HANDOFF_NOTE and r.steps == 3 + btl.FLOOR_HANDOFF_AFTER
    assert r.stay_awake and "floor" in r.stay_awake and btl.HANDOFF_NOTE in r.stay_awake
    note = (tmp_path / btl.HANDOFF_NOTE).read_text()
    assert note.startswith("# Handoff written by the harness, not by you")
    assert "witness" in note and "NOT run" in note and "e5" in note      # the pending call is named


def test_no_floor_no_handoff(tmp_path):
    c = _client(OK_DISPATCH)
    c.memory_root = str(tmp_path)
    r = btl.run_tool_turn(c, _gen(floor_from=10**9, steps_out=6), [{"role": "user", "content": "go"}], max_steps=50)
    assert r.handoff is None and r.reply == "done"
    assert not (tmp_path / btl.HANDOFF_NOTE).exists()


def test_the_beings_own_stay_awake_reason_is_kept(tmp_path):
    c = _client(OK_DISPATCH)
    c.memory_root = str(tmp_path)
    n = {"i": 0}

    def gen(convo):
        i = n["i"]; n["i"] += 1
        intent = BeingIntent("stay_awake", {"reason": "mine"}) if i == 1 else BeingIntent("witness", {"event": f"e{i}"})
        return {"content": "", "intents": [intent],
                "window": {"prompt": 32000, "num_ctx": 32768, "pressure": 0.97, "left": 768, "floor": True}}
    r = btl.run_tool_turn(c, gen, [{"role": "user", "content": "go"}], max_steps=50)
    assert r.handoff and r.stay_awake == "mine"


def test_a_note_that_cannot_be_written_still_ends_the_turn():
    c = _client(OK_DISPATCH)
    c.memory_root = None
    r = btl.run_tool_turn(c, _gen(floor_from=0), [{"role": "user", "content": "go"}], max_steps=50)
    assert r.handoff is None and r.stay_awake and "floor" in r.stay_awake
    assert any("handoff" in i for i in r.interjected)


def test_the_next_beat_sees_a_fresh_note_and_not_a_stale_one(tmp_path):
    from sage.gateway.heartbeat import handoff_view, HANDOFF_SHOW_S
    assert handoff_view(tmp_path) == ""
    p = tmp_path / btl.HANDOFF_NOTE
    p.parent.mkdir(parents=True)
    p.write_text("# Handoff written by the harness, not by you\nlast acts")
    v = handoff_view(tmp_path)
    assert v.startswith("## Where your last beat stopped") and "last acts" in v and "retire_note" in v
    old = time.time() - HANDOFF_SHOW_S - 60
    os.utime(p, (old, old))
    assert handoff_view(tmp_path) == ""


def test_generate_marks_the_floor_from_the_servers_own_count(tmp_path):
    """End to end through run_ollama_tool_turn: once the measured prompt cannot leave the answer
    reserve, the window carries floor=True and the turn hands off."""
    seen = []

    class LLM:
        num_ctx = btl._ANSWER_RESERVE + 2000
        max_response_tokens = 1000
        num_predict_override = None
        think = False

        def get_chat_response(self, messages, tools=None):
            seen.append(len(messages))
            return {"content": "", "tool_calls": [{"function": {"name": "witness", "arguments": {"event": f"x{len(seen)}"}}}],
                    "raw": {"done_reason": "stop", "prompt_eval_count": btl._ANSWER_RESERVE + 1990,
                            "eval_count": 5, "message": {}}}
    c = _client(OK_DISPATCH)
    c.memory_root = str(tmp_path)
    r = btl.run_ollama_tool_turn(c, LLM(), [{"role": "user", "content": "go " + "x" * 400}], max_steps=20)
    assert any(i.get("nudge") == "floor" for i in r.interjected), r.interjected
    assert r.handoff == btl.HANDOFF_NOTE, r.interjected
    assert len(seen) <= 6
