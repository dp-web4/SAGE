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
            if (name, k) in toolset.LEAN_KEEP:
                assert v.get("description") == bp["properties"][k]["description"], \
                    f"{name}.{k}: a load-bearing line stays (cbp on #711)"
            elif name != toolset.DESCRIBE:
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
    # 0.80, not 0.75: the #708 rule keeps prose for parameters that act on existing state (about 800
    # chars). That trade is deliberate: lean is a saving, not a target, and safety lines outrank it.
    assert l < 0.80 * b, f"lean {l} vs brief {b}"


def test_every_load_bearing_pair_names_a_real_parameter():
    """A typo in LEAN_KEEP would silently drop the line it meant to keep."""
    for verb, param in toolset.LEAN_KEEP:
        assert verb in _TOOL_SCHEMAS and param in _TOOL_SCHEMAS[verb][1], (verb, param)


def test_every_optional_parameter_is_classified():
    """SAGE #708's rule: every optional parameter is either kept under lean (it acts on existing state,
    or its valid values are prose) or reviewed as safe to drop. A new optional parameter in neither set
    fails here, so it gets a decision instead of silently losing its prose."""
    optional = {(v, p) for v, (_d, props, req) in _TOOL_SCHEMAS.items() for p in props if p not in req}
    unclassified = optional - toolset.LEAN_KEEP - toolset.LEAN_DROP_REVIEWED
    assert not unclassified, f"classify these for lean (LEAN_KEEP or LEAN_DROP_REVIEWED): {sorted(unclassified)}"
    assert not (toolset.LEAN_KEEP & toolset.LEAN_DROP_REVIEWED), "a parameter cannot be both kept and dropped"
    for v, p in toolset.LEAN_DROP_REVIEWED:
        assert v in _TOOL_SCHEMAS and p in _TOOL_SCHEMAS[v][1], ("stale LEAN_DROP_REVIEWED entry", v, p)
