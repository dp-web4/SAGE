"""Closed value sets are enums in the tool specs (2026-10-01). A slot described only in prose ("one of: open,
avert, dwell, closed") is free text to a grammar-bound generate: on sprout-being's real explore seed, a
JSON-constrained act filled gaze's mode with "tool_call" on 21 of 24 gaze acts."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import GIT_OPS, ollama_tools  # noqa: E402


def test_closed_value_sets_are_enums_and_the_prose_stays():
    props = {t["function"]["name"]: t["function"]["parameters"]["properties"]
             for t in ollama_tools(["gaze", "git_read"])}
    assert props["gaze"]["mode"]["enum"] == ["open", "avert", "dwell", "closed"]
    assert props["git_read"]["op"]["enum"] == list(GIT_OPS)
    assert "one of" in props["gaze"]["mode"]["description"]


def test_open_slots_stay_open():
    props = {t["function"]["name"]: t["function"]["parameters"]["properties"] for t in ollama_tools(["say", "gaze"])}
    assert "enum" not in props["say"]["text"] and "enum" not in props["gaze"]["words"]
