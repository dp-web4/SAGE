"""Offline audit controls, including parity with the actual pending() reader."""
import hashlib
import json

import pytest

from sage.gateway import run_queue_audit as a

SEAT, BEING = "test-seat", "test-being"


def ask(sha="a" * 12, mode="fast", path="notes/example.py"):
    tag = f"sha256:{sha}" if sha else "unknown digest"
    return (f"[request_run] {path}\nwhy: private rationale\n"
            f"(10 bytes, {tag}; the seat decides)\narguments: --mode {mode}")


def result(answers=(), path="notes/example.py"):
    return (f"[request_run] I ran {path} (sha {'a' * 12}) with arguments: --mode fast. "
            "exit code 1.\n" + (a.srr.answers_line(list(answers)) if answers else ""))


def rows(*items):
    return [{"seq": i, "from": speaker, "text": text}
            for i, (speaker, text) in enumerate(items, 1)]


@pytest.mark.parametrize("sha,mode", [("b" * 12, "fast"), ("a" * 12, "slow"), (None, "fast")])
def test_unmatched_older_request_is_labelled_not_reopened(tmp_path, sha, mode):
    turns = rows((BEING, ask(sha, mode)), (BEING, ask()), (SEAT, result([2])))
    original = json.dumps(turns)
    report = a.audit(turns, tmp_path, SEAT)
    assert report["legacy_pending"] == 0
    assert report["candidate_unresolved"] == 1
    assert report["categories"]["explicit_answer"] == 1
    assert report["closed_without_candidate_binding"] == 1
    assert report["affected_requests"][0]["request_seq"] == 1
    assert json.dumps(turns) == original
    assert "private rationale" not in json.dumps(report)
    assert "notes/example.py" not in json.dumps(report)


PARITY_CASES = [
    rows((BEING, ask()), (SEAT, "unrelated")),
    rows((BEING, ask()), (SEAT, result())),
    rows((BEING, ask()), (SEAT, "Deferred. Answers your request seq 1.")),
    rows((BEING, ask()), (BEING, ask()),
         (SEAT, "[request_run] I did not run notes/example.py. Answers your request seq 1.")),
    rows((BEING, ask()), (SEAT, result()), (BEING, ask())),
    rows((BEING, ask("b" * 12)), (BEING, ask()), (SEAT, result([2]))),
    rows((BEING, ask(None)), (SEAT, result())),
    rows((BEING, ask(path="notes/../notes/example.py")), (SEAT, result())),
    rows((BEING, ask()), (SEAT, result(path="notes/other.py"))),
    rows((BEING, "quoted [request_run] in prose"), (SEAT, "Answers your request seq 1.")),
    rows((BEING, ask()), (SEAT, "")),
    rows((BEING, ask()), (SEAT, "[request_run] I did not run notes/example.py. Deferred."),
         (SEAT, "Superseded. Answers your request seq 1.")),
]


@pytest.mark.parametrize("turns", PARITY_CASES)
def test_legacy_classification_matches_production_pending(tmp_path, monkeypatch, turns):
    monkeypatch.setenv("SEAT_ID", SEAT)
    monkeypatch.setattr(a.conv, "recent", lambda home, cid, limit: turns[-limit:])
    expected = a.srr.pending(tmp_path, "test-channel")
    report = a.audit(turns, tmp_path, SEAT)
    assert report["legacy_pending"] == len(expected)
    assert report["requests"] == sum(report["categories"].values())


def test_failed_run_can_bind_without_claiming_success(tmp_path):
    report = a.audit(rows((BEING, ask()), (SEAT, result())), tmp_path, SEAT)
    assert report["categories"]["matching_run"] == 1
    assert report["candidate_unresolved"] == 0
    assert "success" not in report["categories"]


@pytest.mark.parametrize("separator", ["\r", "\x0b", "\u2028"])
@pytest.mark.parametrize("after_path", [False, True])
def test_first_line_boundaries_match_production_pending(tmp_path, monkeypatch, separator, after_path):
    receipt = ("[request_run] I ran notes/example.py" + separator + "continued"
               if after_path else "[request_run] I ran " + separator + "notes/example.py")
    turns = rows((BEING, ask()), (SEAT, receipt))
    monkeypatch.setenv("SEAT_ID", SEAT)
    monkeypatch.setattr(a.conv, "recent", lambda home, cid, limit: turns[-limit:])
    expected = a.srr.pending(tmp_path, "test-channel")
    assert a.audit(turns, tmp_path, SEAT)["legacy_pending"] == len(expected) == int(not after_path)


def test_later_explicit_disposition_supplies_binding(tmp_path):
    report = a.audit(PARITY_CASES[-1], tmp_path, SEAT)
    assert report["categories"]["explicit_answer"] == 1
    assert not report["affected_requests"]


def test_default_window_matches_production_tail(tmp_path, monkeypatch):
    turns = rows((BEING, ask()), *[(SEAT, "ordinary conversation")] * 400)
    monkeypatch.setenv("SEAT_ID", SEAT)
    monkeypatch.setattr(a.conv, "recent", lambda home, cid, limit: turns[-limit:])
    report = a.audit(turns, tmp_path, SEAT)
    assert report["prefix_turns_excluded"] == 1
    assert report["requests"] == len(a.srr.pending(tmp_path, "test-channel")) == 0
    historical = a.audit(turns, tmp_path, SEAT, window=401)
    assert historical["window_kind"] == "historical_counterfactual"
    assert historical["legacy_pending"] == 1


@pytest.mark.parametrize("turns", [[{}], [{"seq": True}],
    [{"seq": 0, "from": BEING, "text": "x"}],
    [{"seq": 2, "from": BEING, "text": "x"}, {"seq": 1, "from": BEING, "text": "y"}],
    [{"seq": 1, "from": BEING, "text": {}}],
    [{"seq": 1, "from": BEING, "text": "x"}] * 2])
def test_malformed_snapshot_refused_not_silently_skipped(tmp_path, turns):
    with pytest.raises(ValueError):
        a.audit(turns, tmp_path, SEAT)


def test_cli_is_read_only_and_output_omits_transcript_and_paths(tmp_path, capsys):
    source = tmp_path / "snapshot.jsonl"
    data = "\n".join(json.dumps(t) for t in PARITY_CASES[5]).encode()
    source.write_bytes(data)
    a.main(["--turns", str(source), "--home", str(tmp_path), "--seat", SEAT])
    report = json.loads(capsys.readouterr().out)
    assert source.read_bytes() == data
    assert report["snapshot_sha256"] == hashlib.sha256(data).hexdigest()
    encoded = json.dumps(report)
    assert str(tmp_path) not in encoded and BEING not in encoded and SEAT not in encoded
    assert "private rationale" not in encoded
    assert sorted(p.name for p in tmp_path.iterdir()) == ["snapshot.jsonl"]


def test_snapshot_limits_and_invalid_json_fail_closed(tmp_path, monkeypatch):
    source = tmp_path / "snapshot.jsonl"
    source.write_text("{broken}\n")
    with pytest.raises(ValueError, match="JSONL"):
        a.read_snapshot(source)
    monkeypatch.setattr(a, "MAX_BYTES", 2)
    with pytest.raises(ValueError, match="byte limit"):
        a.read_snapshot(source)
    monkeypatch.setattr(a, "MAX_TURNS", 1)
    with pytest.raises(ValueError, match="turn limit"):
        a.audit(PARITY_CASES[0], tmp_path, SEAT)


@pytest.mark.parametrize("window", [0, 2001, True, -1])
def test_window_limit(tmp_path, window):
    with pytest.raises(ValueError):
        a.audit([], tmp_path, SEAT, window=window)


def test_home_must_exist_for_resolver_parity(tmp_path):
    with pytest.raises(ValueError, match="existing directory"):
        a.audit([], tmp_path / "absent", SEAT)


def test_implementation_fingerprints_are_recorded(tmp_path):
    report = a.audit([], tmp_path, SEAT)
    assert set(report["implementation_sha256"]) == {"audit", "conversations", "seat_run_requests"}
    assert all(len(value) == 64 for value in report["implementation_sha256"].values())
