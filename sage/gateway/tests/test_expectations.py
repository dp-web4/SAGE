"""expect: a prediction on an act, checked by the harness against the stepper's own result."""
import pytest

from sage.gateway import expectations as ex

PAYLOAD = {  # the shape being_board_step.py returns (legion-being trace, 2026-10-10)
    "game": "ar25-0c556536",
    "probes": [{"move": 36, "action": "ACTION3", "cells_changed": 670},
               {"move": 37, "action": "ACTION3", "cells_changed": 0}],
    "looks": [{"window": {"x": [18, 30], "y": [15, 27]},
               "rows": ["y=15:  9  9  5  9  9  9  9  9  9  9  9  9 10",
                        "y=16:  9  9  9  9  9  9  9  9  9  9  9  9 10"]}],
    "state_after": {"state": "GameState.NOT_FINISHED", "levels_completed": 1},
}


def outcomes(preds):
    return [c["outcome"] for c in ex.check_game(ex.parse(preds), PAYLOAD)]


def test_each_predicate_kind_is_checked_against_the_result():
    assert outcomes([{"probe": 1, "changes": True}, {"probe": 2, "changes": True},
                     {"levels_completed": 1}, {"levels_completed": 2},
                     {"state": "NOT_FINISHED"}, {"state": "WIN"},
                     {"cell": [20, 15], "value": 5}, {"cell": [20, 15], "value": 9}]) == [
        "confirmed", "contradicted", "confirmed", "contradicted",
        "confirmed", "contradicted", "confirmed", "contradicted"]


def test_what_cannot_be_checked_is_said_not_guessed():
    got = ex.check_game(ex.parse([{"cell": [2, 2], "value": 5}, {"probe": 9, "changes": True},
                                  {"vibe": "good"}]), PAYLOAD)
    assert [c["outcome"] for c in got] == ["unverifiable", "unverifiable", "unrecognized"]
    assert "no LOOK" in got[0]["observed"]


def test_the_summary_names_every_contradiction():
    s = ex.summary(ex.check_game(ex.parse('[{"probe": 2, "changes": true}, {"levels_completed": 1}]'), PAYLOAD))
    assert s.startswith("Your expectations: 1 confirmed, 1 CONTRADICTED") and "0 cells changed" in s


@pytest.mark.parametrize("raw", ["not json", "[1, 2]", '"text"', "[" + ",".join(['{"state":"WIN"}'] * 17) + "]"])
def test_malformed_expect_is_refused_with_a_reason(raw):
    with pytest.raises(ValueError):
        ex.parse(raw)


def test_the_game_schema_offers_expect_and_the_trial_can_withdraw_it():
    from sage.gateway import toolset
    specs = toolset.specs({}, None)
    game = [s for s in specs if s["function"]["name"] == "game"][0]
    assert "expect" in game["function"]["parameters"]["properties"]
    # a fresh call is unaffected by a pop on an earlier one (the trial removes it per beat)
    game["function"]["parameters"]["properties"].pop("expect")
    again = [s for s in toolset.specs({}, None) if s["function"]["name"] == "game"][0]
    assert "expect" in again["function"]["parameters"]["properties"]


def test_main_records_the_arm_and_strips_expect_off_arm():
    import inspect
    from sage.gateway import heartbeat
    src = inspect.getsource(heartbeat.main)
    assert 'trial_arm(instance, instance / "heartbeats.jsonl", "expect_trial")' in src
    assert 'record["expect_trial"] = _expect_arm' in src and '.pop("expect", None)' in src


def test_phase_b_closes_game_source_but_never_the_game(tmp_path):
    import json
    from sage.gateway.being_gate_client import trial_game_source_refusal, BeingIntent
    (tmp_path / "instance.json").write_text(json.dumps({"params": {"game_source": "closed"}}))
    src = "/home/dp/ai-workspace/SAGE/environment_files/ar25/0c556536/ar25.py"
    for eff, args in (("memory_read", {"path": src}), ("search", {"pattern": "def x", "path": src}),
                      ("run", {"path": "scratch/sim.py", "data": src})):
        assert "closed until the expect trial ends" in trial_game_source_refusal(BeingIntent(eff, args), str(tmp_path))
    assert trial_game_source_refusal(BeingIntent("game", {"game": "ar25", "probes": "[]"}), str(tmp_path)) is None
    assert trial_game_source_refusal(BeingIntent("memory_read", {"path": "notes/established.md"}), str(tmp_path)) is None
    (tmp_path / "instance.json").write_text(json.dumps({"params": {"game_source": "open"}}))
    assert trial_game_source_refusal(BeingIntent("memory_read", {"path": src}), str(tmp_path)) is None


def test_the_being_cannot_reopen_the_source_itself(tmp_path):
    import json
    from sage.gateway import being_params as bp
    (tmp_path / "instance.json").write_text(json.dumps({"params": {"game_source": "closed"}}))
    ok, text = bp.tune(tmp_path, "game_source", "open", "I want to read it")
    assert not ok and "seat" in text


def test_the_gate_refuses_before_the_law_when_closed(tmp_path):
    import json
    from sage.gateway import being_gate_client as g
    (tmp_path / "instance.json").write_text(json.dumps({"params": {"game_source": "closed"}}))
    c = g.BeingGateClient.__new__(g.BeingGateClient)
    c.memory_root = str(tmp_path)
    v = c.gate(g.BeingIntent("memory_read", {"path": "/x/environment_files/ar25/0c556536/ar25.py"}))
    assert v.decision == "deny" and v.stage == "trial" and "not by the law" in v.reason


def test_the_closure_never_refuses_the_beings_own_writing_for_its_words(tmp_path):
    """2026-10-11: the first Phase B beat had its own handoff note refused for mentioning the path."""
    import json
    from sage.gateway.being_gate_client import trial_game_source_refusal, BeingIntent
    (tmp_path / "instance.json").write_text(json.dumps({"params": {"game_source": "closed"}}))
    note = BeingIntent("memory_write", {"path": "scratch/handoff.md",
                                        "content": "the seat closed environment_files/ for the trial"})
    assert trial_game_source_refusal(note, str(tmp_path)) is None
    edit = BeingIntent("memory_edit", {"path": "notes/established.md", "new": "see environment_files/ar25"})
    assert trial_game_source_refusal(edit, str(tmp_path)) is None
