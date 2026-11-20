"""`answer_think`: a waiting person is answered without thinking first, when the instance opts in (SAGE #788).

Measured on McNugget 2026-11-19 07:52Z (gemma4:12b, preempt + answer_turn "json" on): the answer turn's first
generate spent all 3000 tokens of num_predict thinking about a one-sentence question and was cut at the length
limit with no reply; the retry answered in 30 tokens. 410 s in the answer phase. The opt-in turns thinking off
for the answer generate (and its retry) alone, and restores it, so explore and reflect still think."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import heartbeat as hb  # noqa: E402
from sage.gateway.tests.test_answer_turn_json import LLM, Client  # noqa: E402

ME = "mcnugget-being"
TURN = hb.SelectedTurn("mcnugget-claude", {"seq": 139, "from": "mcnugget-claude",
                                          "text": "in one sentence, what is the next thing you plan to look at?"})


class ThinkLLM(LLM):
    think = True

    def __init__(self, *replies):
        super().__init__(*replies)
        self.seen_think = []

    def get_chat_response(self, messages, tools=None, fmt=None):
        self.seen_think.append(self.think)
        return super().get_chat_response(messages, tools, fmt)


def _answer(llm, **kw):
    return hb.answer_turn_json(Client(), llm, TURN, name="mcnugget", machine="mcnugget", member=ME, **kw)


def test_think_off_applies_to_the_answer_generate_and_is_restored():
    llm = ThinkLLM(json.dumps({"answer": True, "message": "The gate's drain logic."}))
    res = _answer(llm, think=False)
    assert llm.seen_think == [False]
    assert llm.think is True, "the beat's own setting is restored for reflect and the next phase"
    assert res.answer_form["think"] is False, "recorded beside the answer"


def test_the_retry_runs_with_the_same_setting():
    llm = ThinkLLM("", json.dumps({"answer": True, "message": "ok"}))   # empty first reply: retried once
    res = _answer(llm, think=False)
    assert llm.seen_think == [False, False] and res.answer_form["retried"] == 1
    assert llm.think is True


def test_unset_changes_nothing():
    llm = ThinkLLM(json.dumps({"answer": False, "message": ""}))
    res = _answer(llm)
    assert llm.seen_think == [True] and llm.think is True
    assert "think" not in res.answer_form


def test_restored_even_when_the_generate_raises():
    class Boom(ThinkLLM):
        def get_chat_response(self, messages, tools=None, fmt=None):
            self.seen_think.append(self.think)
            raise RuntimeError("ollama went away")
    llm = Boom()
    try:
        _answer(llm, think=False)
    except RuntimeError:
        pass
    assert llm.seen_think and llm.seen_think[0] is False
    assert llm.think is True


def test_a_model_without_a_think_setting_is_left_alone():
    llm = LLM(json.dumps({"answer": False, "message": ""}))
    assert not hasattr(llm, "think")
    res = _answer(llm, think=False)
    assert not hasattr(llm, "think") and "think" not in res.answer_form


def test_the_opt_in_reads_a_boolean_only(tmp_path):
    assert hb.answer_think(tmp_path) is None
    (tmp_path / "instance.json").write_text('{"answer_think": false}')
    assert hb.answer_think(tmp_path) is False
    (tmp_path / "instance.json").write_text('{"answer_think": true}')
    assert hb.answer_think(tmp_path) is True
    (tmp_path / "instance.json").write_text('{"answer_think": "no"}')
    assert hb.answer_think(tmp_path) is None, "not a boolean: no change rather than a guess"
    src = Path(hb.__file__).read_text()
    assert "think=answer_think(instance)" in src, "the beat passes the opt-in to the answer turn"
