"""The answer turn is a JSON turn (2026-09-27): 1 of 69 tool-call answer turns delivered on Sprout;
an offline A/B on the being's own model gave 0/8 (tool call) vs 8/8 (JSON, only the pending turn).
The being still decides, and its answer goes through the gate as its own say."""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import heartbeat as hb  # noqa: E402
from sage.gateway.being_gate_client import ResultEnvelope  # noqa: E402

TURN = {"ts": "2026-09-27T04:25:13Z", "seq": 67, "from": "dp",
        "text": "my beat never ends. the bluetooth speaker may not always be on, but when it is i hear you. did you hear me?"}


class LLM:
    """Replies in order; the last one repeats. A (content, done_reason) pair sets the reason."""
    def __init__(self, *contents):
        self.contents, self.calls = list(contents), []

    def resolve_num_predict(self):
        return 6000

    def get_chat_response(self, messages, tools=None, fmt=None):
        self.calls.append({"messages": messages, "tools": tools, "fmt": fmt})
        c = self.contents[min(len(self.calls), len(self.contents)) - 1]
        content, reason = c if isinstance(c, tuple) else (c, "stop")
        return {"content": content, "tool_calls": [],
                "raw": {"message": {"thinking": "dp asked if I heard"}, "done_reason": reason,
                        "prompt_eval_count": 300, "eval_count": 60}}


class Client:
    def __init__(self, ok=True, error=None):
        self.sent, self.ok, self.error = [], ok, error

    def dispatch(self, intent):
        self.sent.append(intent)
        return ResultEnvelope(ok=self.ok, error=self.error, result={"seq": 68} if self.ok else None)


def _run(*contents, client=None, acts=""):
    sel = hb.SelectedTurn("dp", TURN)
    llm, client = LLM(*contents), client or Client()
    res = hb.answer_turn_json(client, llm, sel, name="sprout", machine="sprout", member="sprout-being",
                              acts=acts)
    return res, llm, client


def test_an_answer_is_dispatched_as_the_beings_own_say():
    res, llm, client = _run(json.dumps({"answer": True, "message": "Yes, I heard you. Thank you."}))
    assert [(i.effector, i.args) for i in client.sent] == [("say", {"to": "dp", "text": "Yes, I heard you. Thank you."})]
    f = res.answer_form
    assert (f["parsed"], f["answer"], f["sent"], f["retried"]) == (True, True, True, 0)
    assert res.generates[0]["num_predict"] == 6000
    assert res.reply == "Yes, I heard you. Thank you." and res.thinking == ["dp asked if I heard"]


def test_silence_is_a_choice_and_sends_nothing():
    res, _, client = _run(json.dumps({"answer": False, "message": ""}))
    assert client.sent == [] and res.answer_form["answer"] is False and res.answer_form["why"] == "chose silence"


def test_an_unparsed_reply_sends_nothing_and_is_counted():
    res, _, client = _run("Yes I heard you")
    assert client.sent == [] and res.answer_form["parsed"] is False
    assert res.answer_form["why"] == "reply was not the JSON asked for"


def test_a_refused_say_is_recorded_as_refused_not_sent():
    res, _, client = _run(json.dumps({"answer": True, "message": "[Your reply to dp]"}),
                          client=Client(ok=False, error="that text reads as a placeholder"))
    assert len(client.sent) == 1, "the gate decides, not the turn"
    assert res.answer_form["sent"] is False and "placeholder" in res.answer_form["refused"]


def test_the_prompt_is_only_the_pending_turn_and_the_ask():
    """Arm B's failures came from what else was in view: prior words became fiction, the tool
    record became a message about tools (SMALL_MODEL_LEGIBILITY 1.9, 1.14)."""
    _, llm, _ = _run(json.dumps({"answer": False, "message": ""}))
    call = llm.calls[0]
    assert call["fmt"] == hb.ANSWER_SCHEMA and call["tools"] is None
    user = call["messages"][-1]["content"]
    assert "did you hear me?" in user
    for plumbing in ("Earlier this beat", "Record of what you did", "called no tools", "tool", "say"):
        assert plumbing not in user, plumbing


def test_the_heartbeat_uses_it_and_counts_every_firing():
    src = open(os.path.join(os.path.dirname(__file__), "..", "heartbeat.py")).read()
    assert "answer = answer_turn_json(client, llm, selected" in src
    assert '"kind": "answer_json"' in src


def test_one_retry_on_an_empty_or_cut_reply_like_the_tool_loop():
    ok = json.dumps({"answer": True, "message": "Yes."})
    for first in ("", ("{\"answer\": tr", "length"), "[OllamaIRP: Connection error: x]"):
        res, llm, client = _run(first, ok)
        assert len(llm.calls) == 2 and res.answer_form["retried"] == 1 and res.answer_form["sent"], first
    res, llm, _ = _run("", "")
    assert len(llm.calls) == 2 and res.answer_form["why"] == "empty reply", "one retry, not a loop"


def test_acts_are_shown_only_when_passed():
    _, llm, _ = _run(json.dumps({"answer": False, "message": ""}), acts="Record of what you did this beat:\n- memory_write ok")
    assert llm.calls[0]["messages"][-1]["content"].startswith("Record of what you did this beat")
    _, llm, _ = _run(json.dumps({"answer": False, "message": ""}))
    assert "Record of what you did" not in llm.calls[0]["messages"][-1]["content"]


def test_it_is_opt_in_per_instance(tmp_path):
    assert hb.answer_turn_mode(tmp_path) == "tool", "no instance.json: today's path"
    (tmp_path / "instance.json").write_text(json.dumps({"answer_turn": "json"}))
    assert hb.answer_turn_mode(tmp_path) == "json"
    (tmp_path / "instance.json").write_text(json.dumps({"answer_turn": "something"}))
    assert hb.answer_turn_mode(tmp_path) == "tool"


def test_the_heartbeat_gates_it_and_keeps_the_tool_path():
    src = open(os.path.join(os.path.dirname(__file__), "..", "heartbeat.py")).read()
    i = src.index('if answer_turn_mode(instance) == "json":')
    assert src.index("answer = answer_turn_json(client, llm, selected", i) > i
    assert src.index("answer = run_ollama_tool_turn(", i) > i, "the tool path stays the default"
    assert 'endswith("-claude")' in src[i:i + 900], "acts only for a seat's question"


def test_an_answer_to_the_room_is_asked_short_and_capped_at_speak_length():
    """2026-09-30: 11 room answers at 451-2,196 chars were refused by speak's 400 cap, unseen by the
    being. Offline: telling it the answer is spoken gave 6/6 speakable; the cap alone cut mid-sentence."""
    from sage.gateway import body
    room_turn = {"ts": "2026-09-30T22:38:05Z", "seq": 7, "from": "voice", "via": "voice",
                 "text": "What do you think is behind your consciousness?"}
    llm = LLM(json.dumps({"answer": False, "message": ""}))
    hb.answer_turn_json(Client(), llm, hb.SelectedTurn("room", room_turn), name="s", machine="s", member="s")
    call = llm.calls[0]
    assert "spoken aloud" in call["messages"][-1]["content"] and "under 400 characters" in call["messages"][-1]["content"]
    assert call["fmt"]["properties"]["message"]["maxLength"] == body.SPEAK_MAX_CHARS
    assert "maxLength" not in hb.ANSWER_SCHEMA["properties"]["message"], "the shared schema is not mutated"


def test_a_written_answer_is_not_shortened():
    llm = LLM(json.dumps({"answer": False, "message": ""}))
    hb.answer_turn_json(Client(), llm, hb.SelectedTurn("dp", TURN), name="s", machine="s", member="s")
    call = llm.calls[0]
    assert "spoken aloud" not in call["messages"][-1]["content"]
    assert call["fmt"] == hb.ANSWER_SCHEMA


def test_the_retry_keeps_the_spoken_cap():
    from sage.gateway import body
    room_turn = {"ts": "2026-09-30T22:38:05Z", "seq": 7, "from": "voice", "text": "Can you hear me?"}
    llm = LLM("", json.dumps({"answer": False, "message": ""}))
    hb.answer_turn_json(Client(), llm, hb.SelectedTurn("room", room_turn), name="s", machine="s", member="s")
    assert len(llm.calls) == 2 and llm.calls[1]["fmt"]["properties"]["message"]["maxLength"] == body.SPEAK_MAX_CHARS
