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
