"""Synthetic bounds and fidelity controls; no model, live capture or network."""
import json
import math
import random
import tracemalloc

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


@pytest.mark.parametrize("value", [0, 9, 999, -999, 1023, -1023])
def test_integer_at_exact_byte_limit_is_not_overrejected(monkeypatch, value):
    expected = json.dumps(value) + "\n"
    monkeypatch.setattr(loop, "_TURN_CAPTURE_MAX_BYTES", len(expected))
    assert loop._serialize_bounded_turn_capture(value) == expected


@pytest.mark.parametrize("negative", [False, True])
def test_large_integer_is_refused_before_decimal_conversion(monkeypatch, negative):
    value = 1 << 100_000
    if negative:
        value = -value
    monkeypatch.setattr(loop, "_TURN_CAPTURE_MAX_BYTES", 100)
    with pytest.raises(OSError, match="limit"):
        loop._serialize_bounded_turn_capture(value)


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


def test_oversized_existing_string_does_not_create_a_full_serialized_copy(monkeypatch):
    source = "x" * 5_000_000  # Created before measuring serializer allocations.
    monkeypatch.setattr(loop, "_TURN_CAPTURE_MAX_BYTES", 1024)
    tracemalloc.start()
    try:
        with pytest.raises(OSError, match="limit"):
            loop._serialize_bounded_turn_capture({"value": source})
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 1024 * 1024


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


def test_long_unicode_is_escaped_in_bounded_chunks(monkeypatch):
    original = json.dumps
    seen_lengths = []

    def observed(value, *args, **kwargs):
        if isinstance(value, str):
            seen_lengths.append(len(value))
        return original(value, *args, **kwargs)

    text = "a" * 1023 + "🌿" + "b" * 2000 + "\ud800"
    monkeypatch.setattr(loop.json, "dumps", observed)
    output = loop._serialize_bounded_turn_capture({"content": text})
    assert json.loads(output) == {"content": text}
    assert seen_lengths and max(seen_lengths) <= 1024


def test_synthetic_json_values_match_standard_decoder():
    rng = random.Random(641)

    def value(depth):
        if depth == 0:
            return rng.choice([None, True, False, 0, -21, 2.5, "", "é\n🌿"])
        kind = rng.randrange(3)
        if kind == 0:
            return [value(depth - 1) for _ in range(rng.randrange(4))]
        if kind == 1:
            return {f"key-{i}": value(depth - 1) for i in range(rng.randrange(4))}
        return value(0)

    for _ in range(200):
        row = value(3)
        assert json.loads(loop._serialize_bounded_turn_capture(row)) == json.loads(json.dumps(row))


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


def test_nonfinite_capture_is_reported_without_stopping_the_turn(tmp_path, capsys):
    class FakeLLM:
        def get_chat_response(self, messages, **kwargs):
            return {"content": "done", "tool_calls": [],
                    "raw": {"message": {"thinking": float("nan")}}}

    (tmp_path / "instance.json").write_text(json.dumps({"params": {"turn_capture": "on"}}))
    client = _client(OK_DISPATCH)
    client.memory_root = str(tmp_path)
    result = loop.run_ollama_tool_turn(client, FakeLLM(), [{"role": "user", "content": "hello"}], tools=[])
    assert result.reply == "done"
    assert result.capture_stats == {"attempted": 1, "written": 0, "failed": 1}
    assert not (tmp_path / "turn_capture.jsonl").exists()
    assert "non-finite turn capture value" in capsys.readouterr().err
