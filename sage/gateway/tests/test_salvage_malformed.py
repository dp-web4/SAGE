"""Synthetic malformed structured-response controls; no provider or effector."""
import pytest

from sage.gateway.being_tool_loop import salvage_tool_calls


TOOLS = [{"function": {"name": "recall", "parameters": {"properties": {"query": {}}}}}]
CALL = '{"name":"recall","arguments":{"query":"synthetic"}}'


@pytest.mark.parametrize("body", [
    '[' + CALL,
    '[' + CALL + ', null',
    '[' + CALL + ' ' + CALL + ']',
    '{"calls": [' + CALL + ']',
    CALL + '\n[' + CALL,
    '```json\n[' + CALL + '\n```',
    '```json\n' + CALL + '\n```\n```json\n[' + CALL + '\n```',
])
def test_damaged_structured_response_is_not_partially_executed(body):
    assert salvage_tool_calls(body, TOOLS) == []


def test_complete_array_still_recovers_in_order():
    calls = salvage_tool_calls('[' + CALL + ',' + CALL + ']', TOOLS)
    assert [call["function"]["name"] for call in calls] == ["recall", "recall"]


def test_complete_values_and_existing_prose_form_still_recover():
    assert len(salvage_tool_calls(CALL + '\n' + CALL, TOOLS)) == 2
    assert len(salvage_tool_calls('Checking first.\n' + CALL, TOOLS)) == 1


def test_malformed_unlabelled_fence_cancels_an_earlier_valid_call():
    text = '```json\n' + CALL + '\n```\n```\n[' + CALL + '\n```'
    assert salvage_tool_calls(text, TOOLS) == []
