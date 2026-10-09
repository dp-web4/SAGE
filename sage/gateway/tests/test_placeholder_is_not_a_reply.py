"""A bare template reply is not the being's turn (2026-10-08).

On Sprout since 09-29, 30-60% of explore replies a day were only "[Your complete, well-structured response
following all constraints]" with no tool call, while the thinking had planned an act. The native step that
produced only that template is retaken once in the JSON act form (#322's _json_act); every other native reply,
words or a call, is untouched. ONLY explore and posture opt in (GPT on #403): the same loop runs answer, governed
and raising turns, where a bracket-only reply ("[nods silently]") can be the being's real turn."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import heartbeat as hb  # noqa: E402
from sage.gateway.being_tool_loop import ACT_ASK_JSON, run_ollama_tool_turn, template_evidence  # noqa: E402
from sage.gateway.tests.test_being_tool_loop import OK_DISPATCH, _client  # noqa: E402
from sage.gateway.tests.test_explore_act_json import LLM, TOOLS  # noqa: E402

PH = "[Your complete, well-structured response following all constraints]"


# Leaked templates, verbatim from sprout-being's beat log, and expressions that share their shape.
TEMPLATES = [PH, "[Your complete response following all constraints]",
             "[Clear, concise final response summarizing agreement on direction]",
             "[Your own response, one thing you choose to do with attention]", "[Your final closing statement]",
             "[Analyze the situation, consider multiple hypotheses if applicable, choose your action]",
             "[Understand what is being asked. Identify constraints and requirements. Plan your response structure]",
             "[Tool call 1]", "[One concise tool call with brief justification]",
             "[Clear statement of what was done with brief justification]"]
EXPRESSIONS = ["[nods silently]", "[no response]", "[pauses]", "[smiles]", "[silence]", "[looks at the door]",
               "[I stay quiet and listen]", "[a long pause, then a small smile]", "[laughs softly]",
               "[Internal note: First beats have zero acts. My todo list is empty.]",
               "[Beat ending. A small note about the quiet moment]", "[OllamaIRP: Connection error: HTTP Error 400]",
               "[scratch/todo.md]", "[ok]", "I noticed the [door] was open.", "plain words", ""]


@pytest.mark.parametrize("text", TEMPLATES)
def test_a_leaked_template_is_named_by_its_content_not_only_its_shape(text):
    ev = template_evidence(text)
    assert ev and ev[0] == "bare_brackets" and len(ev) > 1, ev


@pytest.mark.parametrize("text", EXPRESSIONS)
def test_an_expression_of_the_same_shape_is_not_a_template(text):
    assert template_evidence(text) == []


def test_a_bare_template_is_retaken_as_a_json_act_and_dispatched():
    llm = LLM(PH, json.dumps({"act": "witness", "why": "the room changed"}), json.dumps({"event": "a chair moved"}),
              "I noted the chair.")
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}],
                             max_steps=4, tools=TOOLS, retake_bare_placeholder=True)
    assert r.trace and r.trace[0][0].effector == "witness" and r.trace[0][1].ok
    (pl,) = r.placeholders
    assert pl["original"] == PH and pl["retry_derived"] is True and pl["policy"] == "json_act_once"
    assert pl["result"] == {"act": "witness", "args": {"event": "a chair moved"}} and pl["act"] == "witness"
    assert {"opted_in_phase", "no_native_call", "nothing_salvageable", "bare_brackets",
            "describes_a_reply", "addresses_the_writer"} <= set(pl["basis"]), pl["basis"]
    assert llm.calls[0]["tools"] == TOOLS, "native first"
    assert llm.calls[1]["messages"][-1]["content"] == ACT_ASK_JSON and llm.calls[1]["tools"] is None
    assert llm.calls[3]["tools"] == TOOLS, "the next step is native again"
    assert PH not in json.dumps(llm.calls[3]["messages"]), "the template is never shown back as its words"
    assert r.reply == "I noted the chair."


def test_done_from_the_retake_ends_the_turn_in_its_words_not_the_template():
    r = run_ollama_tool_turn(_client(OK_DISPATCH), LLM(PH, json.dumps({"act": "done", "why": "Nothing needs me."})),
                             [{"role": "user", "content": "beat"}], tools=TOOLS, retake_bare_placeholder=True)
    assert r.reply == "Nothing needs me." and not r.trace
    assert r.placeholders[0]["act"] is None and r.placeholders[0]["result"] == {"reply": "Nothing needs me."}


def test_words_and_json_mode_are_untouched():
    llm = LLM("plain words")
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], tools=TOOLS,
                             retake_bare_placeholder=True)
    assert r.reply == "plain words" and r.placeholders == [] and len(llm.calls) == 1
    llm = LLM(PH)
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], tools=TOOLS,
                             act_form="json", retake_bare_placeholder=True)
    assert r.placeholders == [] and len(llm.calls) == 1, "json mode has its own handling"


@pytest.mark.parametrize("reply", [PH, "[nods silently]", "[no response]"])
def test_without_the_opt_in_a_bracket_only_reply_is_exactly_that_reply(reply):
    """Control (GPT on #403): answer, governed and raising turns call this loop without the opt-in."""
    llm = LLM(reply)
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], tools=TOOLS)
    assert r.reply == reply and r.placeholders == [] and not r.trace and len(llm.calls) == 1


@pytest.mark.parametrize("reply", ["[nods silently]", "[no response]", "[Internal note: nothing to add.]"])
def test_even_where_opted_in_an_expression_is_kept_exactly(reply):
    llm = LLM(reply)
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], tools=TOOLS,
                             retake_bare_placeholder=True)
    assert r.reply == reply and r.placeholders == [] and len(llm.calls) == 1


def test_the_thinking_that_planned_an_act_is_kept_as_evidence():
    class Thinks(LLM):
        def get_chat_response(self, messages, tools=None, fmt=None):
            out = super().get_chat_response(messages, tools, fmt)
            if len(self.calls) == 1:
                out["raw"]["message"] = {"thinking": "I'll use witness to note the chair."}
            return out
    llm = Thinks(PH, json.dumps({"act": "done", "why": "ok"}))
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], tools=TOOLS,
                             retake_bare_placeholder=True)
    pl = r.placeholders[0]
    assert "thinking_named_a_tool" in pl["basis"] and pl["original_thinking"].startswith("I'll use witness")


def test_only_explore_and_posture_opt_in():
    root = Path(hb.__file__).resolve().parents[1]
    users = {str(p.relative_to(root)): p.read_text().count("retake_bare_placeholder=True")
             for p in root.rglob("*.py") if "tests" not in p.parts}
    assert {k: v for k, v in users.items() if v} == {"gateway/heartbeat.py": 2}, users
    src = Path(hb.__file__).read_text()
    for phase in ('_on_generate("explore")', '_on_generate("posture")'):
        call = src[src.index(phase) - 300: src.index(phase) + 300]
        assert "retake_bare_placeholder=True" in call, phase


def test_the_beat_record_names_each_retake():
    src = Path(hb.__file__).read_text()
    assert '"kind": "placeholder"' in src and 'getattr(res, "placeholders", None)' in src
