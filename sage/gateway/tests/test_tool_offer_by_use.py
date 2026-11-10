"""Verbs offered by use, opt-in per instance (dp, 2026-11-10: "try by-name verbs on legion").

Measured on legion-being: the opening prompt left ~6k of 32.8k tokens for a beat's work, the verb schemas
were its largest block, and 29 of 41 verbs had not been called in 74 beats. In this mode a verb not called
lately keeps its name, one line and its parameter names: still offered, still callable, one `describe` from
its full text, and back in full from the next beat once described.
"""
import inspect
import json
import re

from sage.gateway import toolset


def _write(home, recs):
    with open(home / "heartbeats.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


def _beat(i, *acts):
    return {"ts": f"2026-11-10T{i // 60:02d}:{i % 60:02d}:00Z",
            "explore": {"reply": "", "trace": [dict({"ok": True}, **a) for a in acts]}}


def _act(effector, **args):
    return {"effector": effector, "args": args}


def _by_name(specs):
    return {t["function"]["name"]: t["function"] for t in specs}


def test_off_by_default_and_only_by_use_turns_it_on(tmp_path):
    assert toolset.tool_offer_mode({}) == "full" and toolset.tool_offer_mode(None) == "full"
    assert toolset.tool_offer_mode({"tool_offer": "names"}) == "full"
    assert toolset.tool_offer_mode({"tool_offer": "by_use"}) == "by_use"
    _write(tmp_path, [_beat(i, _act("memory_read")) for i in range(20)])
    assert toolset.by_name_verbs(tmp_path, {}) is None, "an instance that has not opted in is untouched"
    assert toolset.offer_by_name(toolset.specs(), None) == toolset.specs()


def test_a_verb_not_called_lately_keeps_its_name_its_parameter_names_and_its_required_keys(tmp_path):
    _write(tmp_path, [_beat(i, _act("memory_read"), _act("game")) for i in range(20)])
    names = toolset.by_name_verbs(tmp_path, {"tool_offer": "by_use"})
    assert "pr_open" in names and "memory_read" not in names and "game" not in names
    full = _by_name(toolset.specs(brief=True))
    cut = _by_name(toolset.offer_by_name(toolset.specs(brief=True), names))
    assert set(cut) == set(full), "every verb is still offered (dp, 2026-09-29)"
    for name in names:
        assert set(cut[name]["parameters"]["properties"]) == set(full[name]["parameters"]["properties"]), name
        assert cut[name]["parameters"]["required"] == full[name]["parameters"]["required"], name
        assert cut[name]["description"].endswith(f"(describe {name})"), name
        assert len(cut[name]["description"]) <= toolset.BY_NAME_DESC_CHARS + len(f" (describe {name})"), name
    for name in ("memory_read", "game"):
        assert cut[name] == full[name], "a verb in use is offered exactly as before"
    assert len(json.dumps(list(cut.values()))) < 0.85 * len(json.dumps(list(full.values())))


def test_describe_stay_awake_and_rest_are_never_cut_and_describe_says_how_the_rest_comes_back(tmp_path):
    _write(tmp_path, [_beat(i, _act("memory_read")) for i in range(20)])
    names = toolset.by_name_verbs(tmp_path, {"tool_offer": "by_use"})
    assert not set(names) & toolset.ALWAYS_FULL
    cut = _by_name(toolset.offer_by_name(toolset.specs(brief=True), names))
    full = _by_name(toolset.specs(brief=True))
    assert cut["rest"] == full["rest"] and cut["stay_awake"] == full["stay_awake"]
    assert "back in full from your next beat" in cut["describe"]["description"]
    assert cut["describe"]["parameters"] == full["describe"]["parameters"]


def test_describing_a_verb_brings_it_back_and_so_does_a_refused_call(tmp_path):
    recs = [_beat(i, _act("memory_read")) for i in range(20)]
    recs.append(_beat(21, _act("describe", verb="pr_open"), dict(_act("appeal"), ok=False, refused=True)))
    _write(tmp_path, recs)
    names = toolset.by_name_verbs(tmp_path, {"tool_offer": "by_use"})
    assert "pr_open" not in names, "a verb the being asked about is in full from the next beat"
    assert "appeal" not in names, "a refused call is still a verb it reached for"
    assert "pr_amend" in names


def test_beats_with_no_act_do_not_use_up_the_window(tmp_path):
    """An outage (the model never answered) is many beats and no use: 163 mute beats on Legion, 11-02 to
    11-09, would otherwise have filed every verb as unused."""
    recs = [_beat(i, _act("game"), _act("memory_read")) for i in range(15)]
    recs += [{"ts": f"2026-11-11T00:{i % 60:02d}:00Z", "explore": {"reply": "", "trace": []}} for i in range(300)]
    _write(tmp_path, recs)
    assert "game" not in toolset.by_name_verbs(tmp_path, {"tool_offer": "by_use"})


def test_a_verb_last_called_before_the_window_goes_by_name(tmp_path):
    recs = [_beat(0, _act("pr_open"))] + [_beat(i + 1, _act("memory_read")) for i in range(toolset.OFFER_WINDOW_BEATS)]
    _write(tmp_path, recs)
    assert "pr_open" in toolset.by_name_verbs(tmp_path, {"tool_offer": "by_use"})


def test_a_short_or_missing_record_offers_everything_in_full(tmp_path):
    assert toolset.by_name_verbs(tmp_path, {"tool_offer": "by_use"}) is None, "no record"
    _write(tmp_path, [_beat(i, _act("memory_read")) for i in range(toolset.OFFER_MIN_BEATS - 1)])
    assert toolset.by_name_verbs(tmp_path, {"tool_offer": "by_use"}) is None, "too short to say what is unused"


def test_a_verb_that_cannot_work_here_keeps_its_reason():
    specs = toolset.specs({"camera": "no camera on this machine"}, brief=True)
    cut = _by_name(toolset.offer_by_name(specs, ["camera", "pr_open"]))
    assert "no camera on this machine" in cut["camera"]["description"]


def test_the_heartbeat_sends_measures_and_records_the_cut_specs():
    from sage.gateway import heartbeat as hb
    src = re.sub(r"\s+", " ", inspect.getsource(hb.main))
    assert "_by_name = _toolset.by_name_verbs(instance, instance_config(instance))" in src
    assert "_explore_specs = _toolset.offer_by_name(_explore_specs, _by_name)" in src
    assert "_schema_measured = len(json.dumps(_explore_specs))" in src, "the fitter budgets what is sent"
    assert '"tool_offer": {"mode": "by_use", "by_name": list(_by_name)} if _by_name else None' in src
