"""Hermetic: the window census over synthetic beats. No model, no live record, temp dirs only.

The cases that matter are the ones the old counting got wrong: a saturated generate that
reports `stop`, and a gate asked about a range with nothing in it.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.window_census import (  # noqa: E402
    census, classify, load_beats, main, read_generates,
)


def _beat(ts, num_ctx=8192, **phases):
    b = {"ts": ts, "num_ctx": num_ctx}
    for phase, generates in phases.items():
        b[phase] = {"generates": generates}
    return b


def _gen(prompt, evaluated, done_reason="stop", num_predict=6000):
    return {"prompt_eval_count": prompt, "eval_count": evaluated,
            "done_reason": done_reason, "num_predict": num_predict}


def main_rc(argv) -> int:
    """Run main() with argv, swallowing its stderr chatter, and return the exit code."""
    import contextlib, io
    old = sys.argv
    sys.argv = ["window_census", *argv]
    try:
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            return main()
    finally:
        sys.argv = old


def _instance(beats) -> Path:
    d = Path(tempfile.mkdtemp(prefix="wincensus-"))
    (d / "heartbeats.jsonl").write_text("".join(json.dumps(b) + "\n" for b in beats))
    return d


def test_saturation_is_not_the_same_as_a_length_stop():
    # The real case, Sprout 2026-09-07T01:11:12Z: 8114 + 78 == 8192, reported `stop`.
    assert "saturated" in classify(8192, 8114, 78, _gen(8114, 78, "stop"))
    assert "length" not in classify(8192, 8114, 78, _gen(8114, 78, "stop"))
    rows = read_generates([_beat("t", reflect=[_gen(8114, 78, "stop")])])
    assert census(rows)["saturated_not_length"] == 1
    assert census(rows)["length"] == 0


def test_classes_are_not_exclusive_and_a_clear_generate_says_so():
    both = classify(8192, 7000, 1192, _gen(7000, 1192, "length"))
    assert set(both) == {"saturated", "length", "budget_starved"}
    assert classify(8192, 100, 50, _gen(100, 50, "stop", num_predict=1024)) == ["clear"]


def test_budget_starved_is_about_the_declared_budget_not_truncation():
    # Nothing was truncated — the generate stopped on its own — but a 6000-token budget
    # could never have applied behind a 6002-token prompt in an 8192 window.
    row = classify(8192, 6002, 200, _gen(6002, 200, "stop", num_predict=6000))
    assert row == ["budget_starved"]


def test_a_generate_without_counters_is_skipped_not_defaulted():
    beats = [_beat("t", reflect=[{"done_reason": "stop"}, _gen(100, 10)])]
    assert len(read_generates(beats)) == 1


def test_beats_are_counted_by_position_not_timestamp():
    # Two beats can share a ts; deduping on it undercounts.
    beats = [_beat("same", reflect=[_gen(100, 10)]), _beat("same", reflect=[_gen(200, 10)])]
    assert census(read_generates(beats))["beats"] == 2


def test_since_and_last_narrow_the_range():
    beats = [_beat("2026-09-01", reflect=[_gen(100, 10)]),
             _beat("2026-09-09", reflect=[_gen(200, 10)])]
    d = _instance(beats)
    assert len(load_beats(d, since="2026-09-08", last=None)) == 1
    assert len(load_beats(d, since=None, last=1)) == 1
    assert len(load_beats(d, since=None, last=None)) == 2


def test_a_torn_last_line_is_the_live_timer_not_a_corrupt_record():
    d = _instance([_beat("2026-09-01", reflect=[_gen(100, 10)])])
    with (d / "heartbeats.jsonl").open("a") as fh:
        fh.write('{"ts": "2026-09-02", "num_c')
    assert len(load_beats(d, None, None)) == 1


def test_gate_fails_on_saturation_and_passes_on_a_clear_range(capsys):
    saturated = _instance([_beat("2026-09-01", reflect=[_gen(8114, 78, "stop")])])
    assert main_with(["--instance", str(saturated), "--gate"]) == 1
    clear = _instance([_beat("2026-09-01", reflect=[_gen(100, 10)])])
    assert main_with(["--instance", str(clear), "--gate"]) == 0


def test_gate_fails_closed_on_an_empty_range():
    """Absence of evidence is not a cleared window (PRD §2, fail-closed)."""
    d = _instance([_beat("2026-09-01", reflect=[_gen(100, 10)])])
    assert main_with(["--instance", str(d), "--since", "2027-01-01", "--gate"]) == 1
    # ... and a missing record is the same answer, not a crash.
    assert main_with(["--instance", str(d / "nope"), "--gate"]) == 1


def test_without_the_gate_an_empty_range_is_not_an_error():
    d = _instance([_beat("2026-09-01", reflect=[_gen(100, 10)])])
    assert main_with(["--instance", str(d), "--since", "2027-01-01"]) == 0


def main_with(argv) -> int:
    old = sys.argv
    sys.argv = ["window_census"] + argv
    try:
        return main()
    finally:
        sys.argv = old


if __name__ == "__main__":
    import traceback
    failed = 0
    for name, fn in sorted(list(globals().items())):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn() if fn.__code__.co_argcount == 0 else fn(None)
            print(f"  ok  {name}")
        except Exception:
            failed += 1
            print(f"FAIL  {name}")
            traceback.print_exc()
    print(f"\n{'FAILED' if failed else 'all green'} ({failed} failed)")
    raise SystemExit(1 if failed else 0)


# --- coverage, phase discovery and replay: cbp-claude's three blind spots, 2026-09-12 -----------

def test_a_skipped_generate_is_counted_so_coverage_is_visible():
    # The defect: every number below `generates` is computed over the rows that survived, and a
    # dropped row was invisible in all of them.
    cov = {}
    beats = [_beat("t", reflect=[{"done_reason": "stop"}, _gen(100, 10)])]
    rows = read_generates(beats, cov)
    assert len(rows) == 1
    assert cov["generates_seen"] == 2
    assert cov["skipped"] == 1
    assert cov["skipped_no_prompt_eval"] == 1
    assert census(rows, cov)["coverage"]["skipped"] == 1


def test_a_beat_without_num_ctx_skips_its_generates_under_its_own_reason():
    cov = {}
    beats = [{"ts": "t", "reflect": {"generates": [_gen(100, 10)]}}]      # no num_ctx
    assert read_generates(beats, cov) == []
    assert cov["skipped_no_num_ctx"] == 1
    assert cov["skipped_no_prompt_eval"] == 0


def test_a_beat_that_generated_nothing_is_not_a_skip():
    # 33 of Sprout's 349 beats are `gate_only` and generated nothing. Counting those as dropped
    # rows would make the gate fail on a fully-measured range.
    cov = {}
    beats = [_beat("a", reflect=[_gen(100, 10)]), {"ts": "b", "num_ctx": 8192, "gate_only": True}]
    assert len(read_generates(beats, cov)) == 1
    assert cov["skipped"] == 0
    assert cov["beats_without_generates"] == 1
    assert cov["beats_with_generates"] == 1


def test_gate_fails_on_a_partial_range_even_when_nothing_saturated():
    # Same instinct as the empty range, one line apart: a range that lost rows was not measured.
    d = _instance([_beat("t", reflect=[{"done_reason": "stop"}, _gen(100, 10)])])
    assert main_rc(["--instance", str(d), "--gate"]) == 1


def test_gate_still_clears_a_fully_measured_unbound_range():
    d = _instance([_beat("t", reflect=[_gen(100, 10)])])
    assert main_rc(["--instance", str(d), "--gate"]) == 0


def test_a_new_generating_phase_is_discovered_by_shape_not_by_name():
    # The reason PHASES is no longer the iteration set: a phase the record grows must not be
    # invisible to the census, because the gate would then pass a range it could not see.
    cov = {}
    beats = [_beat("t", posture=[_gen(100, 10)], dream=[_gen(8114, 78, "stop")])]
    rows = read_generates(beats, cov)
    assert len(rows) == 2
    assert "dream" in cov["sections"]
    assert census(rows, cov)["saturated_not_length"] == 1          # would have been 0 before


def test_sections_without_generates_are_not_mistaken_for_phases():
    cov = {}
    beats = [{"ts": "t", "num_ctx": 8192, "wake": {"by": "timer"},
              "posture": {"generates": [_gen(100, 10)]}}]
    read_generates(beats, cov)
    assert cov["sections"] == ["posture"]


def test_exported_counters_replay_to_the_same_census_and_carry_no_being_text():
    from sage.gateway.window_census import export_counters, load_counters
    beats = [_beat("t1", posture=[_gen(100, 10)], reflect=[_gen(200, 20)]),
             _beat("t1", posture=[_gen(300, 30)])]      # same ts on purpose: beats can share one
    cov = {}
    rows = read_generates(beats, cov)
    summary = census(rows, cov)
    dest = Path(tempfile.mkdtemp(prefix="wincensus-exp-")) / "counters.jsonl"
    assert export_counters(rows, dest, summary) == 3

    replayed = census(load_counters(dest), summary["coverage"])
    assert replayed == summary
    # beat identity survives the round trip even though both beats share a timestamp
    assert replayed["beats"] == 2

    body = dest.read_text()
    assert "generates" not in json.loads(body.splitlines()[1])     # rows are counters only
    for row in body.splitlines()[1:]:
        assert set(json.loads(row)) == {"beat", "ts", "phase", "num_ctx",
                                        "prompt_eval_count", "eval_count",
                                        "num_predict", "done_reason"}


def test_replayed_gate_fails_closed_on_an_export_that_recorded_skips():
    from sage.gateway.window_census import export_counters
    cov = {}
    rows = read_generates([_beat("t", reflect=[{"done_reason": "stop"}, _gen(100, 10)])], cov)
    dest = Path(tempfile.mkdtemp(prefix="wincensus-exp2-")) / "counters.jsonl"
    export_counters(rows, dest, census(rows, cov))
    # the skip is not re-derivable from the rows, so the export carries it and the replay honours it
    assert main_rc(["--counters", str(dest), "--gate"]) == 1
