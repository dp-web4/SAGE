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
    def __init__(self, content):
        self.content, self.calls = content, []

    def get_chat_response(self, messages, tools=None, fmt=None):
        self.calls.append({"messages": messages, "tools": tools, "fmt": fmt})
        return {"content": self.content, "tool_calls": [],
                "raw": {"message": {"thinking": "dp asked if I heard"}, "done_reason": "stop",
                        "prompt_eval_count": 300, "eval_count": 60}}


class Client:
    def __init__(self, ok=True, error=None):
        self.sent, self.ok, self.error = [], ok, error

    def dispatch(self, intent):
        self.sent.append(intent)
        return ResultEnvelope(ok=self.ok, error=self.error, result={"seq": 68} if self.ok else None)


def _run(content, client=None):
    sel = hb.SelectedTurn("dp", TURN)
    llm, client = LLM(content), client or Client()
    res = hb.answer_turn_json(client, llm, sel, name="sprout", machine="sprout", member="sprout-being")
    return res, llm, client


def test_an_answer_is_dispatched_as_the_beings_own_say():
    res, llm, client = _run(json.dumps({"answer": True, "message": "Yes, I heard you. Thank you."}))
    assert [(i.effector, i.args) for i in client.sent] == [("say", {"to": "dp", "text": "Yes, I heard you. Thank you."})]
    assert res.answer_form == {"parsed": True, "answer": True, "sent": True}
    assert res.reply == "Yes, I heard you. Thank you." and res.thinking == ["dp asked if I heard"]


def test_silence_is_a_choice_and_sends_nothing():
    res, _, client = _run(json.dumps({"answer": False, "message": ""}))
    assert client.sent == [] and res.answer_form == {"parsed": True, "answer": False, "sent": False}


def test_an_unparsed_reply_sends_nothing_and_is_counted():
    res, _, client = _run("Yes I heard you")
    assert client.sent == [] and res.answer_form["parsed"] is False


def test_a_refused_say_is_recorded_as_refused_not_sent():
    res, _, client = _run(json.dumps({"answer": True, "message": "[Your reply to dp]"}),
                          Client(ok=False, error="that text reads as a placeholder"))
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
