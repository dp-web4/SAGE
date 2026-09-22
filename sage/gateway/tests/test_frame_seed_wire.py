"""Regression pin: frame parts seeded into messages survive the tool loop.

Pins run_ollama_tool_turn at head f0be361c2 (branch legion/mission-artifact):
seed_messages content is Any, and its generate wrapper copies content through
UNCHANGED (m.get('content', '')), so a parts list in the seed arrives as a
parts list in the outgoing ollama chat payload. #76 pinned the irp half; this
pins the loop half — the wire from what heartbeat seeds to what ollama receives
is already complete, and the only str-only site left is heartbeat's digest
composition (the minimal frame-channel change lives there, nowhere else).

First run was red for a fixture reason, not a claim reason: _FakeLLM took
**kwargs only, but the loop calls llm.get_chat_response(msgs, tools=tools) with
msgs POSITIONAL — TypeError before any assertion ran. Fixed to take messages
positionally; after that fix the test passes (1 passed).

Body: legion-being (legion-gemma3-12b), 2026-09-13. Verified with check
gateway::test_frame_seed_wire at the head it ran against; verdict transcribed
verbatim to scratch/ before any public claim.
"""

from sage.gateway.being_tool_loop import run_ollama_tool_turn


class _FakeLLM:
    """Records exactly what get_chat_response receives."""

    num_ctx = 24576  # so the loop's window-pressure computation has a number

    def __init__(self):
        self.calls = []

    def get_chat_response(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return {"content": "", "tool_calls": []}


def test_frame_seed_reaches_outgoing_payload():
    """A frame part seeded into seed_messages arrives intact in the payload."""
    llm = _FakeLLM()
    b64 = "aGVsbG8="  # 'hello' — small, non-colliding marker
    text_part = {"type": "text", "text": "digest line"}
    image_part = {"type": "image", "image": b64}
    seed = [{"role": "user", "content": [text_part, image_part]}]

    run_ollama_tool_turn(None, llm, seed, max_steps=1)

    assert llm.calls, "get_chat_response was never called"
    msgs = llm.calls[0]["messages"]
    content = msgs[0]["content"]
    assert isinstance(content, list), (
        f"seed parts list degraded to {type(content).__name__} in the outgoing payload")
    assert len(content) == 2, f"expected both parts, got {len(content)}"
    assert content[0] == text_part, "text part altered or reordered"
    assert content[1]["type"] == "image", "image part dropped from payload"
    assert content[1]["image"] == b64, (
        f"base64 altered in transit: {content[1]['image']!r}")
