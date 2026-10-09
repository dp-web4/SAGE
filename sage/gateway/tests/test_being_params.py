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
    assert bp.resolve(h, "window_warn_at") == {"value": 0.80, "source": "default", "note": ""}
    h = _home(tmp_path, {"params": {"window_warn_at": 0.7}})
    assert bp.resolve(h, "window_warn_at")["source"] == "operator"
    h = _home(tmp_path, {"params": {"window_warn_at": 0.7}}, {"window_warn_at": {"value": 0.9}})
    r = bp.resolve(h, "window_warn_at")
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
    h = _home(tmp_path, tuned={"window_warn_at": {"value": 0.99}})
    r = bp.resolve(h, "window_warn_at")
    assert r["value"] == 0.95 and "clamped" in r["note"]


def test_a_lock_takes_it_out_of_the_beings_hands_at_read_and_at_the_verb(tmp_path):
    h = _home(tmp_path, {"param_locks": ["window_warn_at"]}, {"window_warn_at": {"value": 0.6}})
    r = bp.resolve(h, "window_warn_at")
    assert r["value"] == 0.80 and "locked" in r["note"]
    ok, text = bp.tune(h, "window_warn_at", "0.7", "test")
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
    ("window_warn_at", "nan", "x", "finite"),
    ("compact_own_turns", "maybe", "x", "true or false"),
    ("floor_handoff_after", True, "x", "a number"),
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
    r = bp.resolve(h, "window_warn_at")
    assert r["value"] == 0.80 and "unreadable" in r["note"]
    ok, text = bp.tune(h, "window_warn_at", "0.7", "x")
    assert not ok and "unreadable" in text


def _beat(prompts, retried=(), ctx=32768, handoff=None, causes=None):
    gens = [{"prompt_eval_count": p, "retried": 1 if i in retried else 0} for i, p in enumerate(prompts)]
    for i, c in (causes or {}).items():
        gens[i]["retry_cause"] = c
    return {"ts": "t", "num_ctx": ctx, "explore": {"generates": gens, "handoff": handoff}}


def test_window_sense_reads_what_the_server_counted(tmp_path):
    h = _home(tmp_path)
    beats = [_beat([16000, 20000], retried=(1,)),
             _beat([17270, 25000, 31000], retried=(1, 2), handoff="scratch/handoff.md",
                   causes={1: "window", 2: "output_budget"})]
    (h / "heartbeats.jsonl").write_text("\n".join(json.dumps(b) for b in beats) + "\n{torn")
    s = bp.sense_window(h)
    assert s["num_ctx"]["value"] == 32768
    last = s["last"]
    assert last["seed_tokens"]["value"] == 17270 and last["peak_tokens"]["value"] == 31000
    assert (last["retried"], last["generates"], last["handed_off"]) == (2, 3, True)
    assert last["retry_causes"] == {"window": 1, "output_budget": 1}
    assert s["recent"] == {"beats": 2, "peak_over_90pct": 1, "retried": 3, "generates": 5,
                           "retry_causes": {"window": 1, "output_budget": 1, "unrecorded": 1}}
    line = bp.render_window(s)
    assert "17,270 (52%)" in line and "31,000 (94%)" in line and "handed off" in line
    # the two limits are named apart, and an old record's cause is not guessed
    assert "2 of 3 generates retried (1 the window wall, 1 the output budget for one reply)" in line
    assert "1 cause not recorded" in line


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
        str((tmp_path / f).resolve()) for f in (bp.TUNED_TMP, bp.TUNED_FILE, bp.TUNE_LOG)]
    assert g.tune_paths({}, {"memory_root": str(tmp_path)}) == []
    with pytest.raises(ValueError):
        g.tune_paths({"name": "num_ctx"}, {})


def _snapshot(d):
    return {str(p.resolve()): p.read_bytes() for p in d.rglob("*") if p.is_file()}


def test_a_successful_tune_writes_only_what_the_gate_judged(tmp_path):
    """Review of #387 (2026-10-09): tune_paths declared tuned.json while a successful tune also
    appended tune_log.jsonl, a durable write outside the judged act. Every byte a tune changes
    must be at a path tune_paths declared."""
    from sage.gateway import being_gate_client as g
    h = _home(tmp_path, {"active_embodiment": {"num_ctx": 32768}})
    declared = set(g.tune_paths({"name": "num_ctx"}, {"memory_root": str(h)}))
    for value in ("24576", "28672", "default"):
        before = _snapshot(h)
        ok, text = bp.tune(h, "num_ctx", value, "why")
        assert ok, text
        after = _snapshot(h)
        changed = {p for p in set(before) | set(after) if before.get(p) != after.get(p)}
        assert changed and changed <= declared, (changed - declared)


def test_an_audit_write_failure_cannot_return_success(tmp_path):
    """Review of #387: the log append swallowed its failure and the act still returned success.
    Now a change that cannot be recorded is undone, and the act says so."""
    h = _home(tmp_path, {"active_embodiment": {"num_ctx": 32768}},
              tuned={"num_ctx": {"value": 24576}})
    before = (h / bp.TUNED_FILE).read_bytes()
    (h / bp.TUNE_LOG).mkdir()                       # appending to a directory raises OSError
    ok, text = bp.tune(h, "num_ctx", "28672", "why")
    assert not ok and "undone" in text and "nothing changed" in text
    assert (h / bp.TUNED_FILE).read_bytes() == before
    assert bp.value(h, "num_ctx") == 24576
    # first-ever tune: the undo removes the file it created
    h2 = tmp_path / "h2"; h2.mkdir()
    _home(h2, {"active_embodiment": {"num_ctx": 32768}})
    (h2 / bp.TUNE_LOG).mkdir()
    ok, _ = bp.tune(h2, "num_ctx", "24576", "why")
    assert not ok and not (h2 / bp.TUNED_FILE).exists()


def test_if_even_the_undo_fails_the_being_is_told_what_state_it_is_in(tmp_path, monkeypatch):
    import pathlib
    h = _home(tmp_path, {"active_embodiment": {"num_ctx": 32768}}, tuned={"num_ctx": {"value": 24576}})
    (h / bp.TUNE_LOG).mkdir()
    def boom(self, *a, **k):
        raise OSError("read-only")
    monkeypatch.setattr(pathlib.Path, "write_bytes", boom)
    ok, text = bp.tune(h, "num_ctx", "28672", "why")
    assert not ok and "could not be undone" in text and "num_ctx=28672" in text
