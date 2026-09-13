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
    census, classify, join_probe, load_beats, load_sessions, main, read_generates,
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


# --- the binding generate is not the one with the least headroom -----------------------

def test_slack_and_headroom_name_different_generates():
    """headroom ranks by prompt length; what binds is the room the reply had to fit in.

    Both rows are real Sprout posture generates (2026-09-12). The long-prompt one publishes
    the smaller headroom, but the other one is closer to the wall, and a +660 JOIN truncates
    it first. Ranking by headroom.min reports the wrong generate as the tightest.
    """
    rows = read_generates([_beat("t1", posture=[_gen(6804, 865)]),
                           _beat("t2", posture=[_gen(5947, 1755)])])
    summary = census(rows)
    assert summary["headroom"]["min"] == 8192 - 6804      # the long prompt wins on headroom
    assert summary["slack"]["min"] == 8192 - 5947 - 1755  # but the other one binds
    assert summary["slack"]["binding"]["beat"] == 1       # the SECOND beat, not the first
    assert summary["slack"]["binding"]["phase"] == "posture"


def test_join_probe_asks_whether_the_reply_still_fits_not_whether_the_prompt_does():
    """`headroom - added >= 0` is the wrong test: it drops the reply from the comparison.

    Sprout's beat-9 posture generate has headroom 1388 and a landed reply of 865. A +660 JOIN
    leaves 728 of prompt room -- "still spare" by the headroom test -- while the reply that
    actually landed no longer fits. The probe counts the second thing.
    """
    rows = read_generates([_beat("t", posture=[_gen(6804, 865)])])
    assert 8192 - 6804 - 660 > 0                       # the prompt still fits
    probe = join_probe(rows, 660)
    assert probe["truncated"] == 1                     # the reply does not
    assert probe["worst"]["deficit"] == 8192 - (6804 + 660) - 865
    assert join_probe(rows, 465)["truncated"] == 0     # and it is not truncated at the midpoint


def test_join_probe_reports_per_phase_because_a_join_reaches_one_turn():
    """On an act-first instance the session->beat block is prepended to `posture` only, so a
    pooled rate is diluted by the phases the JOIN never enters."""
    rows = read_generates([_beat("t", posture=[_gen(6804, 865)],
                                 reflect=[_gen(900, 200)], explore=[_gen(3300, 400)])])
    probe = join_probe(rows, 660)
    assert probe["phases"]["posture"] == {"generates": 1, "truncated": 1}
    assert probe["phases"]["reflect"]["truncated"] == 0
    assert probe["phases"]["explore"]["truncated"] == 0
    assert probe["truncated"] == 1 and probe["generates"] == 3   # 1/3 pooled, 1/1 where it lands


# --- the raising channel, which is the one UPTAKE is read on ---------------------------

def _session_instance(sessions) -> Path:
    d = Path(tempfile.mkdtemp(prefix="wincensus-sess-"))
    (d / "sessions").mkdir()
    for rec in sessions:
        (d / "sessions" / f"session_{rec['session']:03d}.json").write_text(json.dumps(rec))
    return d


def _session(n, num_ctx=4096, generates=(), attempted=None, end="2026-09-12T10:00:00"):
    return {"session": n, "end": end,
            "window": {"num_ctx": num_ctx, "generates": list(generates),
                       "generates_attempted": len(generates) if attempted is None else attempted}}


def test_the_raising_channel_reads_through_the_same_reader_as_the_beats():
    d = _session_instance([_session(1, generates=[_gen(1200, 300), _gen(2400, 400)])])
    rows = read_generates(load_sessions(d, None, None))
    assert [r["phase"] for r in rows] == ["raising", "raising"]
    assert census(rows)["num_ctx"] == 4096          # not the beat channel's 8192


def test_a_session_written_before_the_window_block_yields_no_rows_and_fails_the_gate():
    """690 of Sprout's sessions are of this shape: the channel UPTAKE is pre-registered on had
    no counters at all. An unmeasured channel is not a cleared one."""
    d = _session_instance([{"session": 1, "end": "2026-09-12T10:00:00"}])
    assert load_sessions(d, None, None) == []
    assert main_rc(["--instance", str(d), "--sessions", "--gate"]) == 1


def test_a_raising_turn_whose_generate_did_not_land_is_a_counted_skip_not_a_free_window():
    """`generates_attempted` is padded out, so a dropped turn stays in the denominator and the
    gate fails on the partial range rather than clearing the rows that happened to survive."""
    d = _session_instance([_session(1, generates=[_gen(1200, 300)], attempted=3)])
    cov = {}
    rows = read_generates(load_sessions(d, None, None), cov)
    assert len(rows) == 1 and cov["generates_seen"] == 3 and cov["skipped"] == 2
    assert main_rc(["--instance", str(d), "--sessions", "--gate"]) == 1


def test_the_raising_gate_clears_a_measured_unbound_range():
    d = _session_instance([_session(1, generates=[_gen(1200, 300)])])
    assert main_rc(["--instance", str(d), "--sessions", "--gate"]) == 0


def test_the_raising_gate_fails_when_the_smaller_window_saturates():
    """The same prompt that is comfortable at 8192 saturates at the raising channel's 4096 --
    which is why censusing the beat channel cannot answer for this one."""
    beat_ok = read_generates([_beat("t", posture=[_gen(3900, 190)])])
    assert census(beat_ok)["saturated"] == 0          # 4090 of 8192: half the window spare
    d = _session_instance([_session(1, generates=[_gen(3900, 190)])])
    assert main_rc(["--instance", str(d), "--sessions", "--gate"]) == 1


# --- the account turn, which used to be written into no section at all -----------------

def test_the_account_turn_is_read_now_that_it_carries_counters():
    """Before 2026-09-12 the account generate had no `on_generate` and the record stored no
    `generates` for it, so the beat's LARGEST generate was invisible to the census, to shape
    discovery and to coverage.skipped alike -- not a skipped row, a row never written."""
    without = {"ts": "t", "num_ctx": 8192,
               "account": {"present": True, "sha256": "x", "reply": "..."},
               "posture": {"generates": [_gen(5947, 1755)]}}
    cov = {}
    assert len(read_generates([without], cov)) == 1
    assert cov["skipped"] == 0 and "account" not in cov["sections"]   # invisible, not skipped

    with_counters = dict(without, account={"present": True, "sha256": "x", "reply": "...",
                                           "generates": [_gen(7762, 300)]})
    cov2 = {}
    rows = read_generates([with_counters], cov2)
    assert len(rows) == 2 and "account" in cov2["sections"]
    assert census(rows)["slack"]["binding"]["phase"] == "account"     # and it is the tight one


def test_an_account_turn_that_produced_no_counters_is_an_empty_list_not_a_missing_key():
    """A reached-but-empty phase is already handled: it is not a skip and not a free window."""
    beat = {"ts": "t", "num_ctx": 8192,
            "account": {"present": False, "sha256": None, "reply": "", "generates": []},
            "posture": {"generates": [_gen(1000, 100)]}}
    cov = {}
    rows = read_generates([beat], cov)
    assert len(rows) == 1 and cov["skipped"] == 0
    assert "account" in cov["sections"]
