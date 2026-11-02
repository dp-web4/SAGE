"""Distilled failure shapes; actual-log replay is separate from these synthetic tests."""
import json

import pytest

from sage.gateway.edit_grounding_probe import main, observed_window, probe


def episode():
    read = {"effector": "memory_read", "ok": True, "args": {"path": "PRIVATE.md"},
            "result": "[lines 20-22 of 40 in 'PRIVATE.md']\n"
                      "heading\n- [still open] Verify result\nleave this alone\n"
                      "\n[end of the range you asked for: lines 20-22 of 40.]"}
    edit = {"effector": "memory_edit", "ok": False, "args": {"path": "PRIVATE.md",
            "old": "- [ ] Verify result (invented timestamp)", "new": "- [x] Verify result"}}
    return read, edit


def test_recorded_miss_grounded_success_and_stale_refusal(monkeypatch):
    from sage.gateway.reference_f1a import ReferenceF1aDispatcher
    from pathlib import Path
    dispatch = ReferenceF1aDispatcher.__call__
    calls = []

    def capture(self, intent, verdict):
        path = Path(self.memory_root) / intent.args["path"]
        calls.append((intent.args.copy(), path.read_text()))
        return dispatch(self, intent, verdict)

    monkeypatch.setattr(ReferenceF1aDispatcher, "__call__", capture)
    read, edit = episode()
    result = probe(read, edit, 2, "- [done] Verify result")
    arms = result["arms"]
    assert not arms["recorded_proposal"]["reported_ok"]
    assert not arms["recorded_proposal"]["changed"]
    assert arms["grounded_oracle"]["reported_ok"] and arms["grounded_oracle"]["matches_oracle"]
    assert not arms["stale_read_control"]["reported_ok"]
    assert not arms["stale_read_control"]["changed"]
    for label in ("relative_numbering_control", "stale_text_control"):
        assert not arms[label]["reported_ok"]
        assert not arms[label]["changed"]
    assert result["selected_line"] == 21
    assert result["tests_numbering_translation"]
    oracle_args, oracle_copy = calls[1]
    assert len(oracle_copy.splitlines()) == result["observed_total_lines"] == 40
    assert oracle_copy.splitlines()[19:22] == [
        "heading", "- [still open] Verify result", "leave this alone"]
    assert oracle_args["start_line"] == oracle_args["end_line"] == result["selected_line"]
    assert arms["grounded_oracle"]["dispatched_start_line"] == 21
    assert calls[2][0]["start_line"] == arms["relative_numbering_control"]["dispatched_start_line"] == 2
    assert calls[2][1] == oracle_copy
    assert "PRIVATE" not in json.dumps(result) and "Verify result" not in json.dumps(result)


def test_first_line_window_has_no_numbering_translation_to_test():
    read, edit = episode()
    read["result"] = read["result"].replace("20-22 of 40", "1-3 of 40")
    result = probe(read, edit, 2, "done")
    assert not result["tests_numbering_translation"]
    assert result["arms"]["relative_numbering_control"]["reported_ok"]


def test_padding_cannot_match_selected_old_text():
    read, edit = episode()
    read["result"] = read["result"].replace("- [still open] Verify result", "[unobserved padding]")
    result = probe(read, edit, 2, "done")
    assert result["arms"]["grounded_oracle"]["matches_oracle"]
    assert not result["arms"]["relative_numbering_control"]["reported_ok"]


@pytest.mark.parametrize("mutation", ["missing_footer", "missing_header", "missing_line", "bad_bounds", "wrong_footer"])
def test_incomplete_read_never_becomes_authoritative(mutation):
    read, _ = episode()
    if mutation == "missing_footer":
        read["result"] = read["result"].split("\n[end")[0]
    elif mutation == "missing_header":
        read["result"] = read["result"].split("\n", 1)[1]
    elif mutation == "missing_line":
        read["result"] = read["result"].replace("leave this alone\n", "")
    elif mutation == "bad_bounds":
        read["result"] = read["result"].replace("20-22 of 40", "22-20 of 40")
    else:
        read["result"] = read["result"].replace("lines 20-22 of 40.]", "lines 19-21 of 40.]")
    with pytest.raises(ValueError):
        observed_window(read)


def test_mismatched_paths_and_range_edits_are_not_rebased_silently():
    read, edit = episode()
    edit["args"]["path"] = "another.md"
    with pytest.raises(ValueError):
        probe(read, edit, 2, "done")
    edit["args"]["path"] = read["args"]["path"]
    edit["args"]["start_line"] = 21
    with pytest.raises(ValueError):
        probe(read, edit, 2, "done")


@pytest.mark.parametrize("line,new", [(0, "done"), (4, "done"), (2, "a\nb"), (2, "- [still open] Verify result")])
def test_invalid_or_noop_oracles_are_refused(line, new):
    with pytest.raises(ValueError):
        probe(*episode(), line, new)


def test_cli_hashes_record_and_never_touches_named_target(tmp_path, capsys):
    import hashlib
    read, edit = episode()
    target = tmp_path / "PRIVATE.md"
    target.write_text("live file must not change")
    read["args"]["path"] = edit["args"]["path"] = str(target)
    raw = json.dumps({"ts": "test-beat", "explore": {"trace": [read, edit]}}).encode() + b"\r\n"
    log = tmp_path / "log.jsonl"
    log.write_bytes(raw)
    args = [str(log), "--beat", "test-beat", "--phase", "explore", "--read-index", "0",
            "--edit-index", "1", "--relative-line", "2", "--new-line", "- [done] Verify result"]
    assert main(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["beat_record_sha256"] == hashlib.sha256(raw).hexdigest()
    assert target.read_text() == "live file must not change" and log.read_bytes() == raw
    log.write_bytes(raw + raw)
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
