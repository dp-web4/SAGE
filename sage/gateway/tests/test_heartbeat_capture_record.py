"""Synthetic checks for the capture-evidence projection; no live beat is run."""

from types import SimpleNamespace

from sage.gateway import heartbeat


def test_disabled_and_legacy_results_do_not_claim_a_capture():
    assert heartbeat._capture_evidence_for_record(SimpleNamespace()) == {}
    assert heartbeat._capture_evidence_for_record(SimpleNamespace(capture_stats=None)) == {}


def test_capture_record_contains_only_validated_counts_and_no_content():
    result = SimpleNamespace(capture_stats={"attempted": 2, "written": 1, "failed": 1,
                                            "content": "synthetic secret"})
    assert heartbeat._capture_evidence_for_record(result) == {
        "capture_stats": {"attempted": 2, "written": 1, "failed": 1,
                          "durability": "not_established"}}


def test_inconsistent_capture_counts_are_not_recorded_as_success():
    result = SimpleNamespace(capture_stats={"attempted": 1, "written": 2, "failed": 0})
    assert heartbeat._capture_evidence_for_record(result) == {"capture_stats": {"status": "invalid"}}


def test_actual_turn_projection_includes_counts_and_preserves_trace():
    intent = SimpleNamespace(effector="test", args={"x": 1})
    envelope = SimpleNamespace(ok=True, refused=False, pending=False, error=None, note="",
                               witness_id="synthetic", verdict=SimpleNamespace(rule="test"), result={"ok": 1})
    result = SimpleNamespace(reply="done", steps=1, capped=False, trace=[(intent, envelope)],
                             thinking=[], salvaged=[], generates=[],
                             capture_stats={"attempted": 1, "written": 0, "failed": 1,
                                            "content": "synthetic secret"})
    projected = heartbeat._turn_for_record(result)
    assert projected["capture_stats"] == {"attempted": 1, "written": 0, "failed": 1,
                                           "durability": "not_established"}
    assert projected["trace"] == [{"effector": "test", "args": {"x": 1}, "ok": True,
                                    "refused": False, "pending": False, "error": None,
                                    "note": None, "witness_id": "synthetic", "rule": "test",
                                    "result": {"ok": 1}}]
    assert "synthetic secret" not in repr(projected)
    assert heartbeat._turn_for_record(None) is None
