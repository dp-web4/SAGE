"""Synthetic bounds and fidelity controls; no model, live capture or network."""
import json
import math

import pytest

from sage.gateway import being_tool_loop as loop
from sage.gateway.tests.test_being_tool_loop import _client, OK_DISPATCH


def test_supported_json_round_trips_without_truncation():
    row = {"messages": [{"content": "a\n🌿\ud800"}], "reply": {"ok": True, "v": None},
           "numbers": [0, -1, 2.5], "pair": ("x", "y")}
    encoded = loop._serialize_bounded_turn_capture(row)
    assert encoded.endswith("\n") and "\n" not in encoded[:-1]
    assert json.loads(encoded) == json.loads(json.dumps(row))


def test_exact_byte_limit_and_escape_expansion(monkeypatch):
    row = {"value": "é🌿"}
    expected = json.dumps(row, ensure_ascii=True, separators=(",", ":")) + "\n"
    monkeypatch.setattr(loop, "_TURN_CAPTURE_MAX_BYTES", len(expected.encode("utf-8")))
    assert loop._serialize_bounded_turn_capture(row) == expected
    monkeypatch.setattr(loop, "_TURN_CAPTURE_MAX_BYTES", len(expected.encode("utf-8")) - 1)
    with pytest.raises(OSError, match="limit"):
        loop._serialize_bounded_turn_capture(row)


def test_rejects_oversized_string_without_serializing_the_whole_value(monkeypatch):
    original = json.dumps
    seen_lengths = []

    def observed(value, *args, **kwargs):
        if isinstance(value, str):
            seen_lengths.append(len(value))
        return original(value, *args, **kwargs)

    monkeypatch.setattr(loop, "_TURN_CAPTURE_MAX_BYTES", 128)
    monkeypatch.setattr(loop.json, "dumps", observed)
    with pytest.raises(OSError, match="limit"):
        loop._serialize_bounded_turn_capture({"value": "x" * 100_000})
    assert not seen_lengths or max(seen_lengths) <= 4096


def test_unsupported_object_is_not_coerced_or_executed():
    class Untrusted:
        def __str__(self):
            raise AssertionError("unexpected conversion")

    with pytest.raises(TypeError, match="unsupported"):
        loop._serialize_bounded_turn_capture({"value": Untrusted()})


def test_cycles_nonfinite_numbers_and_ambiguous_keys_refuse():
    cycle = []
    cycle.append(cycle)
    for row in (cycle, {"v": math.inf}, {"v": math.nan}, {1: "one", "1": "also one"}):
        with pytest.raises((OSError, TypeError, ValueError)):
            loop._serialize_bounded_turn_capture(row)


def test_node_and_depth_limits_are_explicit(monkeypatch):
    monkeypatch.setattr(loop, "_TURN_CAPTURE_MAX_NODES", 3)
    with pytest.raises(OSError, match="limit"):
        loop._serialize_bounded_turn_capture([1, 2, 3])
    monkeypatch.setattr(loop, "_TURN_CAPTURE_MAX_NODES", 100)
    monkeypatch.setattr(loop, "_TURN_CAPTURE_MAX_DEPTH", 2)
    with pytest.raises(OSError, match="limit"):
        loop._serialize_bounded_turn_capture([[[0]]])


def test_real_capture_path_does_not_serialize_full_oversized_row(tmp_path, monkeypatch):
    class FakeLLM:
        def get_chat_response(self, messages, **kwargs):
            return {"content": "done", "tool_calls": [],
                    "raw": {"message": {"thinking": "x" * 100_000}}}

    (tmp_path / "instance.json").write_text(json.dumps({"params": {"turn_capture": "on"}}))
    client = _client(OK_DISPATCH)
    client.memory_root = str(tmp_path)
    monkeypatch.setattr(loop, "_TURN_CAPTURE_MAX_BYTES", 128)
    original = json.dumps
    full_rows = []

    def observed(value, *args, **kwargs):
        if isinstance(value, dict) and "messages" in value and "reply" in value:
            full_rows.append(value)
        return original(value, *args, **kwargs)

    monkeypatch.setattr(loop.json, "dumps", observed)
    result = loop.run_ollama_tool_turn(client, FakeLLM(), [{"role": "user", "content": "hello"}], tools=[])
    assert result.reply == "done"
    assert result.capture_stats == {"attempted": 1, "written": 0, "failed": 1}
    assert not (tmp_path / "turn_capture.jsonl").exists()
    assert not full_rows, "the complete oversized row was serialized before the limit was checked"
