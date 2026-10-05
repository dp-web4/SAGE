"""The being's own earlier turns are compacted too (being_tool_loop.compact_convo).

legion-being, dp chat seq 148 (2026-10-05): "my context window filled mid-beat at exactly
32,768 — my own turns fill it and compaction never trims them"."""
import json

from sage.gateway import being_tool_loop as btl


class LLM:
    def __init__(self, num_ctx):
        self.num_ctx = num_ctx


def _convo(n_turns=10, arg=2000):
    msgs = [{"role": "system", "content": "s" * 2000}, {"role": "user", "content": "go"}]
    for k in range(n_turns):
        msgs.append({"role": "assistant", "content": f"step {k}",
                     "tool_calls": [{"function": {"name": "memory_edit",
                                                  "arguments": {"path": f"f{k}.py", "old": "o",
                                                                "new": f"N{k}" + "x" * arg}}}]})
        msgs.append({"role": "tool", "content": f"ok {k}"})
    return msgs


def test_the_estimate_counts_tool_call_arguments():
    m = [{"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "memory_edit", "arguments": {"new": "x" * 1000}}}]}]
    assert btl._convo_chars(m) >= len(json.dumps({"new": "x" * 1000}))


def test_old_own_turns_lose_their_bodies_newest_are_whole():
    msgs = _convo()
    out, elided = btl.compact_convo(msgs, LLM(num_ctx=btl._ANSWER_RESERVE + 2500))
    own = [m for m in out if m["role"] == "assistant"]
    for m in own[-btl.COMPACT_OWN_TURNS_KEPT:]:
        assert btl._OWN_SIGIL not in m["tool_calls"][0]["function"]["arguments"]["new"]
    oldest = own[0]["tool_calls"][0]["function"]["arguments"]
    assert btl._OWN_SIGIL in oldest["new"] and oldest["new"].startswith("N0")
    assert oldest["path"] == "f0.py"                      # which call, on what, survives
    assert any(e.get("own_turn") for e in elided)
    assert msgs[2]["tool_calls"][0]["function"]["arguments"]["new"].endswith("x")  # input untouched
    assert btl._convo_chars(out) < btl._convo_chars(msgs)


def test_nothing_is_cut_when_the_prompt_fits():
    msgs = _convo(n_turns=3, arg=100)
    out, elided = btl.compact_convo(msgs, LLM(num_ctx=200_000))
    assert out == msgs and elided == []


def test_a_cut_argument_is_not_cut_again():
    msgs = _convo()
    once, _ = btl.compact_convo(msgs, LLM(num_ctx=btl._ANSWER_RESERVE + 2500))
    twice, el2 = btl.compact_convo(once, LLM(num_ctx=btl._ANSWER_RESERVE + 2500))
    assert not any(e.get("own_turn") for e in el2)
    assert twice[2]["tool_calls"] == once[2]["tool_calls"]
