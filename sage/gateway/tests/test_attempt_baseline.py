"""Cost coverage is not task success. Synthetic rows; no live being or provider."""
import json

import pytest

from sage.gateway.attempt_baseline import main, summarize


def attempt(n=7):
    return {"phase": "tools", "prompt_eval_count": 100, "eval_count": n}


def beat(generates, **phase):
    return {"schema": "heartbeat/v2", "explore": {"generates": generates, **phase}}


def report(*rows):
    return summarize(json.dumps(r) for r in rows)


def test_counts_all_attempts_not_final_counters_or_nested_results():
    r = beat([{"eval_count": 9999, "retried": 1, "attempts": [attempt(20), attempt(5)]}],
             trace=[{"ok": True, "result": {"generates": [{"attempts": [attempt(10000)]}]}}])
    out = report(r)["totals"]
    assert out["output_tokens_total"] == 25
    assert out["input_tokens_total"] == 200
    assert out["attempts"] == 2 and out["retried_generates"] == 1
    assert out["nonfinal_attempts"] == 1 and out["nonfinal_output_tokens_known"] == 20


@pytest.mark.parametrize("bad", [None, -1, True, "7", 1.5])
def test_missing_or_invalid_count_is_not_zero(bad):
    out = report(beat([{"attempts": [attempt(5), attempt(bad)]}]))["totals"]
    assert out["output_tokens_total"] is None
    assert out["output_tokens_known"] == 5 and out["output_counts_missing"] == 1


def test_legacy_is_separate_and_never_promoted_to_full_cost():
    out = report(beat([{"eval_count": 90, "retried": 1}]), beat([{"attempts": [attempt(0)]}]))
    assert out["coverage"] == {"complete_recorded": 1, "incomplete": 1, "no_generations": 0}
    assert out["totals"]["output_tokens_total"] is None
    assert out["totals"]["legacy_generates"] == 1
    assert out["cohorts"]["complete_recorded"]["output_tokens_total"] == 0


def test_all_six_phases_and_killed_beat():
    from sage.gateway.attempt_baseline import PHASES
    r = {"schema": "heartbeat/v2", **{p: {"generates": [{"attempts": [attempt()]}]} for p in PHASES}}
    assert report(r)["totals"]["output_tokens_total"] == 42
    r["killed"] = "timeout"
    assert not report(r)["totals"]["recorded_cost_complete"]


@pytest.mark.parametrize("gen", [None, {}, {"attempts": []}, {"attempts": "bad"}, {"attempts": [None]}])
def test_malformed_generations_fail_coverage(gen):
    assert report(beat([gen]))["coverage"]["incomplete"] == 1


def test_new_phase_and_phase_error_do_not_disappear():
    r = beat([{"attempts": [attempt()]}])
    r["future"] = {"generates": []}
    r["account"] = {"generates": [], "error": "call failed before publication"}
    out = report(r)
    assert out["totals"]["cost_issues"] == {"unknown_generation_phase": 1}
    assert out["totals"]["phase_errors"] == 1


def test_phase_error_does_not_discard_known_recorded_cost():
    r = {"schema": "heartbeat/v2", "account": {
        "generates": [{"attempts": [attempt(12)]}], "error": "save failed"}}
    out = report(r)
    assert out["coverage"]["complete_recorded"] == 1
    assert out["totals"]["output_tokens_total"] == 12
    assert out["phases"]["account"]["phase_errors"] == 1
    r["account"].pop("generates")
    assert report(r)["coverage"]["incomplete"] == 1


def test_retry_requires_at_least_one_more_attempt_than_retries():
    out = report(beat([{"retried": 1, "attempts": [attempt()]}]))
    assert out["totals"]["cost_issues"] == {"retry_attempts_missing": 1}
    assert out["totals"]["output_tokens_total"] is None


def test_receipts_not_success_scores_and_repeats_span_phases_not_beats():
    proposal = {"effector": "memory_read", "args": {"path": "PRIVATE PATH"}}
    rows = [{**proposal, "ok": True, "witness_id": "PRIVATE WITNESS"},
            {**proposal, "ok": False, "pending": True},
            {"ok": False, "refused": True}, {"ok": False}, {},
            {"ok": True, "pending": True}]
    r = beat([{"attempts": [attempt()]}], trace=rows)
    r["answer"] = {"generates": [], "trace": [{**proposal, "ok": True}]}
    out = report(r, r)
    totals = out["totals"]
    assert totals["repeated_proposals"] == 4
    assert totals["reported_ok"] == 4 and totals["reported_pending"] == 2
    assert totals["reported_refused"] == 2 and totals["reported_failed"] == 2
    assert totals["receipt_unknown"] == 2 and totals["receipt_conflicting"] == 2
    assert totals["witness_refs_present"] == 2
    assert "PRIVATE" not in json.dumps(out)


def test_repeat_transitions_follow_latest_receipt_and_split_memory_operations():
    def receipt(effector, ok):
        return {"effector": effector, "args": {"secret": "PRIVATE"}, "ok": ok}
    rows = [receipt("memory_edit", False), receipt("memory_edit", False),
            receipt("memory_edit", True), receipt("memory_edit", True),
            receipt("memory_read", True), receipt("memory_read", True),
            receipt("PRIVATE EFFECTOR", True), receipt("PRIVATE EFFECTOR", True)]
    out = report(beat([], trace=rows))
    assert out["totals"]["repeats_by_memory_operation_and_status"] == {
        "memory_write:failed->failed": 1, "memory_write:failed->ok": 1,
        "memory_write:ok->ok": 1, "memory_read:ok->ok": 1, "other:ok->ok": 1}
    assert out["totals"]["repeated_proposals"] == 5
    assert "PRIVATE" not in json.dumps(out)


def test_nonfinal_reasons_are_bounded_and_exclude_final_attempt():
    attempts = [{**attempt(), "done_reason": reason}
                for reason in ("length", "stop", "PRIVATE", None, "length")]
    out = report(beat([{"attempts": attempts}]))
    assert out["totals"]["nonfinal_by_done_reason"] == {
        "length": 1, "stop": 1, "other": 1, "missing": 1}
    assert "PRIVATE" not in json.dumps(out)


def test_malformed_input_and_empty_input_never_report_complete():
    assert summarize(["{bad", "null", "[]", " "])["malformed_rows"] == 3
    assert not summarize([])["totals"]["recorded_cost_complete"]
    assert report({"schema": "heartbeat/v2"})["coverage"]["no_generations"] == 1
    assert report({})["coverage"]["incomplete"] == 1


def test_transport_and_length_markers_are_not_total_failure_labels():
    a = {**attempt(), "transport_error": True, "done_reason": "length"}
    totals = report(beat([{"attempts": [a]}]))["totals"]
    assert totals["transport_errors"] == totals["length_stops"] == 1
    assert totals["reported_failed"] == 0


def test_cli_reads_file_without_mutating_it(tmp_path, capsys):
    import hashlib
    path = tmp_path / "beats.jsonl"
    text = json.dumps(beat([{"attempts": [attempt()]}])) + "\n"
    path.write_text(text)
    assert main([str(path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["totals"]["output_tokens_total"] == 7
    assert out["input_bytes_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert path.read_text() == text


@pytest.mark.parametrize("suffix", [b"\r\n", b"\r\n\xff\n", b'\n{"bad":"\xff"}\n'])
def test_cli_file_and_stdin_hash_raw_bytes_and_agree(tmp_path, suffix):
    import hashlib
    import subprocess
    import sys
    raw = json.dumps(beat([{"attempts": [attempt()]}])).encode() + suffix
    path = tmp_path / "beats.jsonl"
    path.write_bytes(raw)
    command = [sys.executable, "-m", "sage.gateway.attempt_baseline"]
    file_out = subprocess.run(command + [str(path)], capture_output=True, check=True)
    stdin_out = subprocess.run(command + ["-"], input=raw, capture_output=True, check=True)
    assert file_out.stdout == stdin_out.stdout
    out = json.loads(file_out.stdout)
    assert out["input_bytes_sha256"] == hashlib.sha256(raw).hexdigest()
    assert out["malformed_rows"] == (1 if b"\xff" in suffix else 0)
    assert path.read_bytes() == raw
