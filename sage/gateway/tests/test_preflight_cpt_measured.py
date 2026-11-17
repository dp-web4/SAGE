"""The step-1 preflight calibrates from this being's own measured counts (SAGE #582 part 2).

Declared ratios (2.9 default, llama3.1 3.6, gemma4 3.3) over-counted the server by 12-49%, so a seed near
the edge lost context, or the whole beat, to an estimate. Each explore step-1 generate now records
`prompt_chars` beside `prompt_eval_count`; the next beat divides by the lowest recent ratio less a margin.
Hermetic: temp instance dirs, fake LLMs, no model.
"""
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import being_tool_loop as btl  # noqa: E402
from sage.gateway.being_tool_loop import run_ollama_tool_turn, preflight_cpt  # noqa: E402
from sage.gateway.heartbeat import (measured_preflight_cpt, MEASURED_CPT_MIN_SAMPLES,  # noqa: E402
                                    MEASURED_CPT_MARGIN)


def _beat(model, chars, toks, **g):
    return {"model": model, "explore": {"generates": [dict({"prompt_chars": chars, "prompt_eval_count": toks}, **g)]}}


def _home(tmp_path, records):
    with open(tmp_path / "heartbeats.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return tmp_path


def test_enough_samples_give_the_lowest_ratio_less_the_margin(tmp_path):
    recs = [_beat("m:1", 36000 + 100 * i, 10000) for i in range(8)]
    cal = measured_preflight_cpt(_home(tmp_path, recs), "m:1")
    assert cal["samples"] == 8
    assert cal["value"] == round(3.6 * MEASURED_CPT_MARGIN, 3)
    assert cal["value"] < cal["min"], "errs high against every count it was taken from"


def test_too_few_samples_keep_the_declared_ratio(tmp_path):
    recs = [_beat("m:1", 36000, 10000)] * (MEASURED_CPT_MIN_SAMPLES - 1)
    assert measured_preflight_cpt(_home(tmp_path, recs), "m:1")["value"] is None


def test_another_models_beats_do_not_count(tmp_path):
    """A body switch starts uncalibrated, then calibrates from its own beats."""
    recs = [_beat("old:8b", 40000, 10000)] * 10
    assert measured_preflight_cpt(_home(tmp_path, recs), "new:4b")["samples"] == 0


def test_cut_counts_records_without_chars_and_garbage_are_skipped(tmp_path):
    recs = ([_beat("m:1", 36000, 10000, server_cut={"counted": 5000})] * 3
            + [{"model": "m:1", "explore": {"generates": [{"prompt_eval_count": 9000}]}}] * 3
            + [_beat("m:1", 36000, 1)] * 3          # 36,000 chars/token: implausible (a cache-reuse count)
            + [{"model": "m:1", "explore": None}, "not a dict"])
    path = _home(tmp_path, recs)
    with open(path / "heartbeats.jsonl", "a") as f:
        f.write("{truncated\n")
    assert measured_preflight_cpt(path, "m:1")["samples"] == 0


def test_no_file_is_no_calibration(tmp_path):
    assert measured_preflight_cpt(tmp_path, "m:1") == {"value": None, "samples": 0}


def test_a_measured_ratio_wins_over_the_declared_one_and_none_falls_back():
    llm = SimpleNamespace(_adapter=SimpleNamespace(capabilities=SimpleNamespace(preflight_chars_per_token=3.3)))
    assert preflight_cpt(llm) == 3.3
    llm.preflight_cpt_measured = 3.45
    assert preflight_cpt(llm) == 3.45
    for bad in (None, True, 0.4, 20.0, "3.5"):
        llm.preflight_cpt_measured = bad
        assert preflight_cpt(llm) == 3.3, bad


# --- the loop records what it sent, in the preflight's units ---------------------------------------

class _LLM:
    num_ctx = 16384

    def __init__(self, count):
        self.count = count

    def get_chat_response(self, messages, tools=None, **kw):
        return {"content": "done", "tool_calls": [], "raw": {"prompt_eval_count": self.count, "eval_count": 3}}


class _Client:
    def dispatch(self, intent):
        raise AssertionError


TOOLS = [{"type": "function", "function": {"name": "witness", "description": "d" * 300,
                                           "parameters": {"type": "object", "properties": {}}}}]
SEED = [{"role": "system", "content": "s" * 3000}, {"role": "user", "content": "u" * 20000}]


def test_the_first_generate_records_the_chars_the_preflight_counted():
    r = run_ollama_tool_turn(_Client(), _LLM(6000), SEED, max_steps=1, tools=TOOLS)
    g = r.generates[0]
    assert g["prompt_chars"] == btl._convo_chars(SEED) + btl.uncounted_chars(TOOLS, "native")
    assert g["prompt_eval_count"] == 6000


def test_the_json_form_records_none_because_it_sends_something_else():
    r = run_ollama_tool_turn(_Client(), _LLM(6000), SEED, max_steps=1, tools=TOOLS, act_form="json")
    assert all("prompt_chars" not in g for g in r.generates)


def test_round_trip_a_recorded_beat_calibrates_the_next(tmp_path):
    """What the loop writes is what the heartbeat reads."""
    gens = [run_ollama_tool_turn(_Client(), _LLM(6400), SEED, max_steps=1, tools=TOOLS).generates[0]
            for _ in range(MEASURED_CPT_MIN_SAMPLES)]
    recs = [{"model": "m:1", "explore": {"generates": [g]}} for g in gens]
    cal = measured_preflight_cpt(_home(tmp_path, recs), "m:1")
    assert cal["value"] == round(gens[0]["prompt_chars"] / 6400 * MEASURED_CPT_MARGIN, 3)
