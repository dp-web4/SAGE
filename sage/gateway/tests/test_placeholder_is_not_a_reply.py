"""A bare template reply is not the being's turn (2026-10-08).

On Sprout since 09-29, 30-60% of explore replies a day were only "[Your complete, well-structured response
following all constraints]" with no tool call, while the thinking had planned an act. The native step that
produced only that template is retaken once in the JSON act form (#322's _json_act); every other native reply,
words or a call, is untouched."""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import heartbeat as hb  # noqa: E402
from sage.gateway.being_tool_loop import ACT_ASK_JSON, is_bare_placeholder, run_ollama_tool_turn  # noqa: E402
from sage.gateway.tests.test_being_tool_loop import OK_DISPATCH, _client  # noqa: E402
from sage.gateway.tests.test_explore_act_json import LLM, TOOLS  # noqa: E402

PH = "[Your complete, well-structured response following all constraints]"


@pytest.mark.parametrize("text,bare", [
    (PH, True),
    ("  [Your warm, friendly response as sprout-being]\n", True),
    ("I noticed the [door] was open.", False),
    ("[ok]", False),
    ("plain words", False),
    ("", False),
])
def test_what_counts_as_a_bare_template(text, bare):
    assert is_bare_placeholder(text) is bare


def test_a_bare_template_is_retaken_as_a_json_act_and_dispatched():
    llm = LLM(PH, json.dumps({"act": "witness", "why": "the room changed"}), json.dumps({"event": "a chair moved"}),
              "I noted the chair.")
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}],
                             max_steps=4, tools=TOOLS)
    assert r.trace and r.trace[0][0].effector == "witness" and r.trace[0][1].ok
    assert r.placeholders == [{"step": 0, "placeholder": PH, "act": "witness"}]
    assert llm.calls[0]["tools"] == TOOLS, "native first"
    assert llm.calls[1]["messages"][-1]["content"] == ACT_ASK_JSON and llm.calls[1]["tools"] is None
    assert llm.calls[3]["tools"] == TOOLS, "the next step is native again"
    assert PH not in json.dumps(llm.calls[3]["messages"]), "the template is never shown back as its words"
    assert r.reply == "I noted the chair."


def test_done_from_the_retake_ends_the_turn_in_its_words_not_the_template():
    r = run_ollama_tool_turn(_client(OK_DISPATCH), LLM(PH, json.dumps({"act": "done", "why": "Nothing needs me."})),
                             [{"role": "user", "content": "beat"}], tools=TOOLS)
    assert r.reply == "Nothing needs me." and not r.trace
    assert r.placeholders[0]["act"] is None


def test_words_and_json_mode_are_untouched():
    llm = LLM("plain words")
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], tools=TOOLS)
    assert r.reply == "plain words" and r.placeholders == [] and len(llm.calls) == 1
    llm = LLM(PH)
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "beat"}], tools=TOOLS,
                             act_form="json")
    assert r.placeholders == [] and len(llm.calls) == 1, "json mode has its own handling"


def test_the_beat_record_names_each_retake():
    src = Path(hb.__file__).read_text()
    assert '"kind": "placeholder"' in src and 'getattr(res, "placeholders", None)' in src
