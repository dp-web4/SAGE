"""Explore acts through closed JSON objects (opt-in, 2026-10-01).

On sprout-being's REAL explore seed (2B, 30 tools, nothing executed) the native tool-call channel made 0/6 acts
(all "[Your complete, well-structured response ...]"); act-from-an-enum, then that tool's own parameter schema,
made 6/6 well-formed acts. The act still goes through the gate as a normal intent."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import heartbeat as hb  # noqa: E402
from sage.gateway.being_tool_loop import run_ollama_tool_turn, ACT_ASK_JSON  # noqa: E402
from sage.gateway.tests.test_being_tool_loop import OK_DISPATCH, _client  # noqa: E402

TOOLS = [{"type": "function", "function": {"name": "witness", "parameters": {
            "type": "object", "required": ["event"], "properties": {"event": {"type": "string"}}}}},
         {"type": "function", "function": {"name": "rest", "parameters": {
            "type": "object", "properties": {"reason": {"type": "string"}}}}}]


class LLM:
    def __init__(self, *contents):
        self.contents, self.calls = list(contents), []

    def resolve_num_predict(self):
        return 6000

    def get_chat_response(self, messages, tools=None, fmt=None):
        self.calls.append({"messages": messages, "tools": tools, "fmt": fmt})
        c = self.contents.pop(0) if self.contents else json.dumps({"act": "done", "why": "that is all"})
        return {"content": c, "tool_calls": [],
                "raw": {"message": {}, "done_reason": "stop", "prompt_eval_count": 300, "eval_count": 30}}


def test_an_act_is_chosen_from_the_tools_then_its_arguments_fill_that_tools_schema():
    llm = LLM(json.dumps({"act": "witness", "why": "something moved"}),
              json.dumps({"event": "a chair moved"}),
              json.dumps({"act": "done", "why": "I noted the chair."}))
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}],
                             max_steps=4, tools=TOOLS, act_form="json")
    assert r.trace and r.trace[0][0].effector == "witness" and r.trace[0][0].args == {"event": "a chair moved"}
    assert r.trace[0][1].ok, "dispatched through the gate like any intent"
    assert r.reply == "I noted the chair."
    first, second = llm.calls[0], llm.calls[1]
    assert first["tools"] is None and first["fmt"]["properties"]["act"]["enum"] == ["witness", "rest", "done"]
    assert first["messages"][-1]["content"] == ACT_ASK_JSON
    assert second["fmt"] == TOOLS[0]["function"]["parameters"], "the chosen tool's own schema"


def test_done_or_an_unreadable_reply_ends_the_turn_in_words():
    r = run_ollama_tool_turn(_client(OK_DISPATCH), LLM(json.dumps({"act": "done", "why": "Nothing needs me."})),
                             [{"role": "user", "content": "beat"}], tools=TOOLS, act_form="json")
    assert r.reply == "Nothing needs me." and not r.trace
    r = run_ollama_tool_turn(_client(OK_DISPATCH), LLM("not json at all"),
                             [{"role": "user", "content": "beat"}], tools=TOOLS, act_form="json")
    assert r.reply == "not json at all" and not r.trace


def test_rest_chosen_as_json_ends_the_turn_as_rest_does():
    llm = LLM(json.dumps({"act": "rest", "why": "quiet room"}), json.dumps({"reason": "the room is quiet"}))
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}],
                             max_steps=4, tools=TOOLS, act_form="json")
    assert r.rested is not None


def test_native_tool_calls_stay_the_default():
    llm = LLM("plain words")
    run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], tools=TOOLS)
    assert llm.calls[0]["tools"] == TOOLS and llm.calls[0]["fmt"] is None


def test_the_explore_turn_mode_is_opt_in_and_wired(tmp_path):
    assert hb.explore_turn_mode(tmp_path) == "tools"
    (tmp_path / "instance.json").write_text('{"explore_turn": "json"}')
    assert hb.explore_turn_mode(tmp_path) == "json"
    src = Path(hb.__file__).read_text()
    assert src.count("act_form=explore_turn_mode(instance)") == 2, "explore and posture"
