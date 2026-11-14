"""Lean tool descriptions, opt-in per instance (SAGE #708; dp, 2026-11-14: "name + describe is the right shape").

Measured on nomad-being 11-14: brief specs were 22,236 chars, and the parameter blocks were 13,856 of them.
Lean is brief, plus each parameter's prose behind `describe`; names, required keys and enums stay.
"""
import json

from sage.gateway import toolset
from sage.gateway.being_gate_client import _TOOL_SCHEMAS


def test_lean_is_opt_in_and_named_exactly():
    assert toolset.tool_descriptions_mode({}) == "full"
    assert toolset.tool_descriptions_mode({"tool_descriptions": "lean"}) == "lean"
    assert toolset.tool_descriptions_mode({"tool_descriptions": " LEAN "}) == "lean"
    assert toolset.tool_descriptions_mode({"tool_descriptions": "brief"}) == "brief"
    assert toolset.tool_descriptions_mode({"tool_descriptions": "leaner"}) == "full"


def test_lean_keeps_what_makes_a_call_well_formed_and_drops_the_prose():
    lean = {s["function"]["name"]: s["function"] for s in toolset.specs({}, {}, lean=True)}
    brief = {s["function"]["name"]: s["function"] for s in toolset.specs({}, {}, brief=True)}
    assert set(lean) == set(brief), "every verb is still offered"
    for name, fn in lean.items():
        bp, lp = brief[name]["parameters"], fn["parameters"]
        assert set(lp["properties"]) == set(bp["properties"]), f"{name}: parameter names stay"
        assert lp["required"] == bp["required"], f"{name}: required keys stay"
        for k, v in lp["properties"].items():
            assert bp["properties"][k].get("enum") == v.get("enum"), f"{name}.{k}: a closed value set stays"
            if name != toolset.DESCRIBE:
                assert "description" not in v, f"{name}.{k}: parameter prose moves behind describe"
        if lp["properties"] and name != toolset.DESCRIBE:
            assert fn["description"].endswith(f"({toolset.DESCRIBE} {name}: what each parameter means.)")
            assert "(Full text:" not in fn["description"], "one pointer, not two"


def test_what_lean_leaves_out_is_one_describe_away():
    for name, (_desc, props, _req) in _TOOL_SCHEMAS.items():
        text = toolset.full_text(name)
        for k in props:
            assert f"  {k}" in text, f"describe {name} still explains {k}"


def test_lean_is_materially_smaller_than_brief():
    b = len(json.dumps(toolset.specs({}, {}, brief=True)))
    l = len(json.dumps(toolset.specs({}, {}, lean=True)))
    assert l < 0.75 * b, f"lean {l} vs brief {b}"
