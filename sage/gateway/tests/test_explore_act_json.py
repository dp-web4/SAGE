"""Explore acts through closed JSON objects (opt-in, 2026-10-01).

On sprout-being's REAL explore seed (2B, 30 tools, nothing executed) the native tool-call channel made 0/6 acts
(all "[Your complete, well-structured response ...]"); act-from-an-enum, then that tool's own parameter schema,
made 6/6 well-formed acts. The act still goes through the gate as a normal intent."""
import json

import pytest
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
    assert first["tools"] is None and first["fmt"]["properties"]["act"]["enum"] == ["done", "witness", "rest"]
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
    assert src.count("act_form=explore_turn_mode(instance)") == 3, "explore, posture and the act after an answer"


def test_closed_value_sets_are_enums_in_the_spec():
    from sage.gateway.being_gate_client import ollama_tools
    props = {t["function"]["name"]: t["function"]["parameters"]["properties"] for t in ollama_tools(["gaze", "git_read"])}
    assert props["gaze"]["mode"]["enum"] == ["open", "avert", "dwell", "closed"]
    assert "cat" in props["git_read"]["op"]["enum"]
    assert "one of" in props["gaze"]["mode"]["description"], "the prose stays"


def test_the_ask_says_what_it_already_did_this_turn():
    llm = LLM(json.dumps({"act": "witness", "why": "x"}), json.dumps({"event": "e"}),
              json.dumps({"act": "done", "why": "ok"}))
    run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}],
                         max_steps=4, tools=TOOLS, act_form="json")
    assert "already done" not in llm.calls[0]["messages"][-1]["content"]
    assert "This turn you have already done: witness." in llm.calls[2]["messages"][-1]["content"]


def test_the_json_form_has_its_own_small_step_budget(tmp_path):
    assert hb.explore_json_steps(tmp_path, 8) == 3
    (tmp_path / "instance.json").write_text('{"explore_json_steps": 5}')
    assert hb.explore_json_steps(tmp_path, 8) == 5
    assert hb.explore_json_steps(tmp_path, 4) == 4, "never above the beat's own cap"
    src = Path(hb.__file__).read_text()
    assert "max_steps=_explore_steps" in src and src.count("max_steps=_explore_steps") == 2


def test_the_argument_ask_is_the_act_name_and_json_only():
    """Sprout trial 2026-10-03 + E21: the description in the ask became the message ("Say is a tool that lets you
    write messages...", "Add a turn to the conversation with dp: ..."), and slot meanings did too ("What do you
    want to say?"). LEGIBILITY 1.14: no prose in a prompt that produces a message."""
    say = {"type": "function", "function": {"name": "say", "description": "Add a turn to your conversation.",
           "parameters": {"type": "object", "required": ["to", "text"], "properties": {
               "to": {"type": "string", "description": "the conversation id"},
               "text": {"type": "string", "description": "what you want to say"}}}}}
    llm = LLM(json.dumps({"act": "say", "why": "x"}), json.dumps({"to": "dp", "text": "hello"}))
    run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], max_steps=1,
                         tools=[say], act_form="json")
    ask = llm.calls[1]["messages"][-1]["content"]
    assert ask == "say. As JSON.", ask


# --- GPT on #311: arguments that fail are not an act; a grounded subset in the JSON form -------------------

PEER = [{"type": "function", "function": {"name": "peer_ask", "description": "Ask a sibling.", "parameters": {
            "type": "object", "required": ["to", "body"],
            "properties": {"to": {"type": "string", "enum": ["legion-being", "cbp-being"]}, "body": {"type": "string"}}}}},
        {"type": "function", "function": {"name": "pr_open", "parameters": {"type": "object", "properties": {}}}}]


def test_bad_arguments_get_one_more_identical_draw_then_act():
    """GPT on #336: the retry must not carry the validator's words into the message-producing prompt."""
    llm = LLM(json.dumps({"act": "peer_ask", "why": "ask legion"}),
              json.dumps({"to": "legion-being", "body": "Hey [name], how are you?"}),
              json.dumps({"to": "legion-being", "body": "How did your last beat go?"}),
              json.dumps({"act": "done", "why": "asked"}))
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}],
                             max_steps=3, tools=PEER, act_form="json")
    assert llm.calls[2]["messages"][-1]["content"] == "peer_ask. As JSON.", "the identical minimal prompt"
    assert llm.calls[2]["messages"] == llm.calls[1]["messages"], "no validator prose, no failed draw in view"
    assert r.trace and r.trace[0][0].args == {"to": "legion-being", "body": "How did your last beat go?"}
    assert not r.json_arg_failures


def test_two_failures_end_the_step_with_no_act_never_empty_arguments():
    llm = LLM(json.dumps({"act": "peer_ask", "why": "ask"}), "not json", json.dumps({"to": "me", "body": "hi"}))
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}],
                             max_steps=1, tools=PEER, act_form="json")
    assert not r.trace, "no intent was dispatched"
    assert r.json_arg_failures and "must be one of" in r.json_arg_failures[0]["problem"]
    assert "Nothing was done" in r.reply


def test_the_json_form_offers_only_the_grounded_subset():
    from sage.gateway.being_tool_loop import JSON_ACT_EXCLUDE
    llm = LLM(json.dumps({"act": "done", "why": "ok"}))
    run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], tools=PEER, act_form="json")
    assert llm.calls[0]["fmt"]["properties"]["act"]["enum"] == ["done", "peer_ask"]
    assert {"pr_open", "patch_apply", "channel_egress", "mesh", "request_scope"} <= JSON_ACT_EXCLUDE


def test_check_args():
    from sage.gateway.being_tool_loop import _check_args
    sch = PEER[0]["function"]["parameters"]
    assert _check_args('{"to": "cbp-being", "body": "hi"}', sch) == ({"to": "cbp-being", "body": "hi"}, None)
    assert "required" in _check_args('{"to": "cbp-being", "body": ""}', sch)[1]
    assert "placeholder" in _check_args('{"to": "cbp-being", "body": "[topic]"}', sch)[1]
    assert "JSON" in _check_args("nope", sch)[1]


def test_say_is_closed_over_writable_conversations_in_the_beat():
    src = Path(hb.__file__).read_text()
    assert '_enums[("say", "to")] = _writable' in src and '"kind": "json_arg_failure"' in src



def test_the_validator_checks_types_unexpected_keys_and_nesting():
    """GPT on #322: a required string slot satisfied by [] passed (str([]) is non-empty)."""
    from sage.gateway.being_tool_loop import _check_args
    sch = PEER[0]["function"]["parameters"]
    assert "must be a string" in _check_args('{"to": "cbp-being", "body": []}', sch)[1]
    assert "must be a string" in _check_args('{"to": "cbp-being", "body": {"a": 1}}', sch)[1]
    assert "not an argument" in _check_args('{"to": "cbp-being", "body": "hi", "extra": 1}', sch)[1]
    nested = {"type": "object", "required": ["items"], "properties": {"items": {"type": "array", "items": {
        "type": "object", "required": ["n"], "properties": {"n": {"type": "integer"}}}}}}
    assert _check_args('{"items": [{"n": 1}, {"n": 2}]}', nested)[1] is None
    assert "must be a integer" in _check_args('{"items": [{"n": 1}, {"n": "two"}]}', nested)[1]
    assert "required" in _check_args('{"items": [{}]}', nested)[1]
    assert "must be a integer" in _check_args('{"items": [{"n": true}]}', nested)[1], "a bool is not an integer"


def test_the_ask_is_a_format_with_done_first():
    from sage.gateway.being_tool_loop import ACT_ASK_JSON
    assert ACT_ASK_JSON.startswith("Reply as JSON") and '"done"' in ACT_ASK_JSON
    assert "Choose ONE thing to do now" not in ACT_ASK_JSON


class RetryLLM:
    """First reply is a transport error or a think-only empty turn; then JSON. Records every call's form."""
    num_predict_override = None
    num_ctx = 16384

    def __init__(self, first):
        self.first, self.calls = first, []

    def resolve_num_predict(self):
        return 3000

    def get_chat_response(self, messages, tools=None, fmt=None):
        self.calls.append({"tools": tools, "fmt": fmt})
        if len(self.calls) == 1:
            return self.first
        if fmt and "act" in (fmt.get("properties") or {}):
            return {"content": json.dumps({"act": "done", "why": "nothing more"}), "tool_calls": [],
                    "raw": {"done_reason": "stop", "message": {}}}
        return {"content": "native words", "tool_calls": [], "raw": {"done_reason": "stop", "message": {}}}


@pytest.mark.parametrize("first", [
    {"content": "[OllamaIRP: HTTP 500 invalid tool call arguments]", "tool_calls": [], "raw": {}},
    {"content": "", "tool_calls": [], "raw": {"done_reason": "stop", "eval_count": 300,
                                              "message": {"thinking": "I should gaze at the room", "content": ""}}},
], ids=["transport-error", "think-only"])
def test_a_json_turns_retry_stays_json(first):
    """GPT on #322: both retries fell back to native tool calling, switching the trial's arm mid-step."""
    llm = RetryLLM(first)
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], max_steps=1,
                             tools=TOOLS, act_form="json")
    assert len(llm.calls) >= 2, "there was a retry"
    assert all(c["tools"] is None and c["fmt"] for c in llm.calls), "every attempt, retries included, was JSON"
    assert r.reply == "nothing more"


def test_native_retries_stay_native():
    llm = RetryLLM({"content": "[OllamaIRP: HTTP 500]", "tool_calls": [], "raw": {}})
    run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], max_steps=1, tools=TOOLS)
    assert len(llm.calls) == 2 and all(c["tools"] == TOOLS and c["fmt"] is None for c in llm.calls)


def test_a_say_retry_prompt_is_still_exactly_the_act_and_json():
    """GPT's pin on #336: first args invalid for say; the second generate's final user message is exactly
    "say. As JSON." and contains neither the validator error nor schema/slot prose."""
    say = {"type": "function", "function": {"name": "say", "description": "Add a turn to your conversation.",
           "parameters": {"type": "object", "required": ["to", "text"], "properties": {
               "to": {"type": "string", "enum": ["dp"], "description": "the conversation id"},
               "text": {"type": "string", "description": "what you want to say"}}}}}
    llm = LLM(json.dumps({"act": "say", "why": "x"}), json.dumps({"to": "nowhere", "text": "hi"}),
              json.dumps({"to": "dp", "text": "hello"}))
    run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], max_steps=1,
                         tools=[say], act_form="json")
    second = llm.calls[2]["messages"][-1]["content"]
    assert second == "say. As JSON.", second
