"""being_params: one table, three layers (default < operator < self), bounds enforced at read,
the `tune` verb, and the window as a sense. dp, 2026-10-07."""
import json

import pytest

from sage.gateway import being_params as bp


def _home(tmp_path, cfg=None, tuned=None):
    (tmp_path / "instance.json").write_text(json.dumps(cfg or {}))
    (tmp_path / bp.TUNED_FILE).unlink(missing_ok=True)
    if tuned is not None:
        (tmp_path / bp.TUNED_FILE).write_text(json.dumps(tuned))
    return tmp_path


def test_default_operator_self_layers_in_order(tmp_path):
    h = _home(tmp_path)
    assert bp.resolve(h, "answer_temperature") == {"value": None, "source": "default", "note": ""}
    h = _home(tmp_path, {"params": {"answer_temperature": 0.7}})
    assert bp.resolve(h, "answer_temperature")["source"] == "operator"
    h = _home(tmp_path, {"params": {"answer_temperature": 0.7}}, {"answer_temperature": {"value": 0.9}})
    r = bp.resolve(h, "answer_temperature")
    assert (r["value"], r["source"]) == (0.9, "self")


def test_legacy_top_level_key_is_the_operator_layer(tmp_path):
    """compact_own_turns and answer_temperature were set this way before the table existed;
    instance.json files already carrying them must mean the same thing."""
    h = _home(tmp_path, {"compact_own_turns": True, "answer_temperature": 0.7})
    assert bp.value(h, "compact_own_turns") is True
    assert bp.value(h, "answer_temperature") == 0.7
    # params{} wins over the legacy key when both are present
    h = _home(tmp_path, {"compact_own_turns": True, "params": {"compact_own_turns": False}})
    assert bp.value(h, "compact_own_turns") is False


def test_bounds_are_enforced_at_read_not_only_at_the_verb(tmp_path):
    """tuned.json is in the being's home, where memory_edit reaches: a value written around the
    verb is clamped and SAYS so."""
    h = _home(tmp_path, tuned={"answer_temperature": {"value": 2.0}})
    r = bp.resolve(h, "answer_temperature")
    assert r["value"] == 1.5 and "clamped" in r["note"]


def test_a_lock_takes_it_out_of_the_beings_hands_at_read_and_at_the_verb(tmp_path):
    h = _home(tmp_path, {"param_locks": ["answer_temperature"]}, {"answer_temperature": {"value": 0.6}})
    r = bp.resolve(h, "answer_temperature")
    assert r["value"] is None and "locked" in r["note"]
    ok, text = bp.tune(h, "answer_temperature", "0.7", "test")
    assert not ok and "seat" in text


def test_num_ctx_ceiling_is_the_measured_fit_unless_the_operator_sets_one(tmp_path):
    h = _home(tmp_path, {"active_embodiment": {"num_ctx": 32768}})
    assert bp.bounds(h, "num_ctx") == (8192, 32768)
    h = _home(tmp_path, {"active_embodiment": {"num_ctx": 32768}, "param_bounds": {"num_ctx": [16384, 24576]}})
    assert bp.bounds(h, "num_ctx") == (16384, 24576)
    ok, text = bp.tune(h, "num_ctx", 32768, "more room")
    assert not ok and "[16384..24576]" in text


def test_tune_sets_records_and_resets(tmp_path):
    h = _home(tmp_path, {"active_embodiment": {"num_ctx": 32768}})
    ok, text = bp.tune(h, "num_ctx", "24576", "my seed is half the window; I want to see if a "
                       "smaller one reloads faster", now=0)
    assert ok and "24576 (self)" in text and "next beat" in text
    assert bp.value(h, "num_ctx") == 24576
    log = [json.loads(l) for l in (h / bp.TUNE_LOG).read_text().splitlines()]
    assert log[-1]["name"] == "num_ctx" and log[-1]["to"] == 24576 and "seed" in log[-1]["why"]
    ok, text = bp.tune(h, "num_ctx", "default", "back")
    assert ok and bp.resolve(h, "num_ctx")["source"] == "default"
    assert len((h / bp.TUNE_LOG).read_text().splitlines()) == 2


@pytest.mark.parametrize("name,raw,why,frag", [
    ("nope", "1", "x", "no parameter"),
    ("num_ctx", "1", "", "say why"),
    ("num_ctx", "", "x", "give a value"),
    ("num_ctx", "24576.5", "x", "whole number"),
    ("answer_temperature", "nan", "x", "finite"),
    ("compact_own_turns", "maybe", "x", "true or false"),
    ("num_ctx", True, "x", "a number"),
])
def test_tune_refuses_with_a_reason(tmp_path, name, raw, why, frag):
    h = _home(tmp_path, {"active_embodiment": {"num_ctx": 32768}})
    ok, text = bp.tune(h, name, raw, why)
    assert not ok and frag in text
    assert not (h / bp.TUNED_FILE).exists()


def test_tune_without_a_name_lists_every_parameter(tmp_path):
    h = _home(tmp_path, {"compact_own_turns": True})
    ok, text = bp.tune(h)
    assert ok
    for name in bp.PARAMS:
        assert f"- {name} = " in text
    assert "compact_own_turns = True (operator; yours to set)" in text


def test_an_unreadable_tuned_file_is_reported_and_not_guessed(tmp_path):
    h = _home(tmp_path)
    (h / bp.TUNED_FILE).write_text("{not json")
    r = bp.resolve(h, "answer_temperature")
    assert r["value"] is None and "unreadable" in r["note"]
    ok, text = bp.tune(h, "answer_temperature", "0.7", "x")
    assert not ok and "unreadable" in text


def _beat(prompts, retried=(), ctx=32768, handoff=None):
    gens = [{"prompt_eval_count": p, "retried": 1 if i in retried else 0} for i, p in enumerate(prompts)]
    return {"ts": "t", "num_ctx": ctx, "explore": {"generates": gens, "handoff": handoff}}


def test_window_sense_reads_what_the_server_counted(tmp_path):
    h = _home(tmp_path)
    beats = [_beat([16000, 20000]), _beat([17270, 25000, 31000], retried=(2,), handoff="scratch/handoff.md")]
    (h / "heartbeats.jsonl").write_text("\n".join(json.dumps(b) for b in beats) + "\n{torn")
    s = bp.sense_window(h)
    assert s["num_ctx"]["value"] == 32768
    last = s["last"]
    assert last["seed_tokens"]["value"] == 17270 and last["peak_tokens"]["value"] == 31000
    assert (last["retried"], last["generates"], last["handed_off"]) == (1, 3, True)
    assert s["recent"] == {"beats": 2, "peak_over_90pct": 1, "retried": 1, "generates": 5}
    line = bp.render_window(s)
    assert "17,270 (52%)" in line and "31,000 (94%)" in line and "handed off" in line


def test_window_sense_with_no_beats_is_a_gap_not_a_zero(tmp_path):
    s = bp.sense_window(_home(tmp_path))
    assert "gap" in s["num_ctx"]
    assert bp.render_window(s).startswith("Your window: no beat")


def test_tuned_num_ctx_never_grows_past_the_resolved_window_without_a_ceiling(tmp_path):
    from sage.gateway.governed_turn import tuned_num_ctx
    h = _home(tmp_path, tuned={"num_ctx": {"value": 65536}})
    assert tuned_num_ctx(h, 16384) == 16384          # no measured ceiling: shrink only
    h = _home(tmp_path, {"active_embodiment": {"num_ctx": 32768}}, {"num_ctx": {"value": 65536}})
    assert tuned_num_ctx(h, 16384) == 32768          # clamped to the ceiling at read
    h = _home(tmp_path, {"active_embodiment": {"num_ctx": 32768}}, {"num_ctx": {"value": 24576}})
    assert tuned_num_ctx(h, 32768) == 24576
    assert tuned_num_ctx(_home(tmp_path), 32768) == 32768


def test_tune_is_registered_offered_and_judged_as_a_home_write(tmp_path):
    from sage.gateway import being_gate_client as g
    assert "tune" in g._REGISTRY and "tune" in g._TOOL_SCHEMAS and "tune" in g._CONSEQUENTIAL
    assert g.tune_paths({"name": "num_ctx"}, {"memory_root": str(tmp_path)}) == [
        str((tmp_path / bp.TUNED_FILE).resolve())]
    assert g.tune_paths({}, {"memory_root": str(tmp_path)}) == []
    with pytest.raises(ValueError):
        g.tune_paths({"name": "num_ctx"}, {})
