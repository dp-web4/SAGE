"""The SAGE-canonical toolset (sage/gateway/toolset.py): every being is offered every verb.

dp, 2026-09-29: "we need a sage-canonical toolset that every being is offered. not all will
choose to use every tool, and some may not be able to. but the tools should be there for all."
"""
import inspect
import json

from sage.gateway import toolset
from sage.gateway.being_gate_client import _REGISTRY, _TOOL_SCHEMAS


def test_every_registered_verb_is_in_the_canonical_toolset_and_rest_is_last():
    names = toolset.canonical_toolset()
    assert set(names) == set(_TOOL_SCHEMAS), "a verb with a schema that is not offered is a verb no being has"
    assert set(_REGISTRY) <= set(names), "every registry verb is offered"
    assert names[-1] == "rest" and len(names) == len(set(names))


def test_every_launcher_offers_the_same_toolset(tmp_path):
    from sage.gateway.governed_turn import offered_tools
    from sage.gateway.heartbeat import offered_explore_tools
    import sage.gateway.heartbeat as hb
    canon = toolset.canonical_toolset()
    assert offered_explore_tools(None) == canon and offered_explore_tools(None, "/wt") == canon
    inst = tmp_path / "i"; inst.mkdir()
    assert [t["function"]["name"] for t in offered_tools(None, inst)] == canon
    main = inspect.getsource(hb.main)
    assert main.count("tools=_explore_specs") == 2, "explore AND posture offer the canonical specs"
    assert '_explore_tools = [t["function"]["name"] for t in _explore_specs]' in main, \
        "the names used for the seed and the window measurement come FROM the offered specs"
    from pathlib import Path
    raising = (Path(hb.__file__).resolve().parents[1] / "raising" / "scripts" / "ollama_raising_session.py").read_text()
    assert "_toolset.specs(" in raising, "the raising sessions offer the canonical toolset too"


def test_an_unavailable_verb_is_offered_short_with_its_reason_and_still_callable():
    u = toolset.unavailable({"inventory": {"verbs": []}}, None, {})
    specs = {t["function"]["name"]: t["function"] for t in toolset.specs(u)}
    assert set(specs) == set(toolset.canonical_toolset())
    for v, why in u.items():
        f = specs[v]
        assert "CANNOT WORK" in f["description"] and why in f["description"]
        assert set(f["parameters"]["properties"]) == set(_TOOL_SCHEMAS[v][1]), "parameters kept: callable"
        assert f["parameters"]["required"] == _TOOL_SCHEMAS[v][2]
    avail = [v for v in specs if v not in u]
    assert avail and all(specs[v]["description"] == _TOOL_SCHEMAS[v][0] for v in avail), \
        "an available verb carries its full description"


def test_availability_is_measured_not_assumed():
    everything = toolset.unavailable({"inventory": {"verbs": list(toolset.BODY_VERBS)}}, "/wt", {"game_stepper": "/s"})
    assert everything == {}, everything
    nothing = toolset.unavailable({"inventory": {"verbs": []}}, None, {})
    assert set(nothing) == set(toolset.BODY_VERBS) | set(toolset.WORKTREE_VERBS) | {"game"}


def test_the_whole_toolset_costs_less_where_less_can_work():
    rich = len(json.dumps(toolset.specs({})))
    poor = len(json.dumps(toolset.specs(toolset.unavailable({"inventory": {"verbs": []}}, None, {}))))
    assert poor < rich, "unusable verbs are offered short"
