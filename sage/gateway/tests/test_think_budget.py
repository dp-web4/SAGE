"""think_budget: unset changes nothing; set, it is the first attempt's num_predict; the being may tune it."""
import json
from sage.gateway import being_params as bp
from sage.gateway.heartbeat import apply_think_budget


class _LLM:
    num_predict_override = None


def _inst(tmp_path, params):
    (tmp_path / "instance.json").write_text(json.dumps({"params": params}))
    return tmp_path


def test_unset_leaves_the_config_value(tmp_path):
    llm = _LLM()
    assert apply_think_budget(llm, _inst(tmp_path, {})) is None
    assert llm.num_predict_override is None


def test_set_becomes_the_override(tmp_path):
    llm = _LLM()
    assert apply_think_budget(llm, _inst(tmp_path, {"think_budget": 5000})) == 5000
    assert llm.num_predict_override == 5000


def test_bounds_hold_and_the_being_may_tune_it(tmp_path):
    inst = _inst(tmp_path, {})
    ok, _ = bp.tune(inst, "think_budget", "999999", "testing the ceiling")
    assert not ok
    ok, _ = bp.tune(inst, "think_budget", "5000", "waste less per cut")
    assert ok and bp.value(inst, "think_budget") == 5000
