"""Hermetic: the heartbeat's two presentations of the one posture, and the per-model
predicates that pick them. No model, no gate."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.governed_turn import acts_under_posture, needs_think_to_act  # noqa: E402
from sage.gateway.heartbeat import EXPLORE_TOOLS, compose  # noqa: E402

POSTURE = "## Why you are awake\n\nA heartbeat is not a question. Nobody asked you anything."
TOOLS = ", ".join(EXPLORE_TOOLS)
KW = dict(name="sprout", machine="sprout", member="sprout-being", posture_text=POSTURE,
          header="HEADER\n", state="STATE\n", recall="RECALL", inbox="INBOX", digest="DIGEST")


def test_posture_first_is_one_turn_with_the_posture_in_the_system_prompt():
    seed, second = compose(False, **KW)
    assert second is None and [m["role"] for m in seed] == ["system", "user"]
    assert POSTURE in seed[0]["content"]
    user = seed[1]["content"]
    for k in ("HEADER", "STATE", "RECALL", "INBOX", "DIGEST"):
        assert k in user, k
    assert user.rstrip().endswith("One thing done with attention is enough."), "tools named last"
    assert TOOLS in user


def test_act_first_moves_the_posture_verbatim_to_a_second_tool_turn():
    seed, second = compose(True, **KW)
    assert [m["role"] for m in seed] == ["system", "user"]
    assert POSTURE not in seed[0]["content"] and POSTURE not in seed[1]["content"]
    assert POSTURE in second, "the same words, not a summary"
    first = seed[1]["content"]
    assert "STATE" in first and "RECALL" in first and TOOLS in first
    assert "DIGEST" not in first and "INBOX" not in first, "the world comes with the posture"
    assert "DIGEST" in second and "INBOX" in second and TOOLS in second, "the posture turn is a tool turn"


def test_no_turn_carries_a_think_suffix():
    """The `/no_think` suffix is retired: it was never a control surface on this stack.
    Measured 2026-09-12 -- Sprout at ollama 0.30.8, CBP at 0.20.7 -- appending it leaves the
    think block intact (qwen3.5:0.8b 1428 -> 1441 chars, qwen3.8-distill:2b 275 -> 405, both
    still thinking) while `think=False` zeroes it. No fleet template parses the string; the
    think branches that exist key on the API field, not on prompt text. Thinking is declared
    per model in the config and sent as the request's `think` field (ollama_irp.py:165)."""
    from sage.gateway.heartbeat import REFLECT
    for act_first in (False, True):
        seed, second = compose(act_first, **KW)
        for turn in [m["content"] for m in seed] + ([second] if second else []):
            assert "/no_think" not in turn
    assert "/no_think" not in REFLECT


def test_predicates_are_per_model_not_size():
    # 0.8B acts, 1.5B narrates, 2B distill narrates, 3B acts, 3.8B heretic acts (measured 09-05)
    assert acts_under_posture("qwen3.5:0.8b")
    assert acts_under_posture("qwen2.5:3b")
    assert acts_under_posture("qwen38-heretic:q3km")
    assert not acts_under_posture("qwen3.8-distill:2b")
    assert not acts_under_posture("hf.co/empero-ai/Qwen3.8-2B-Distill-GGUF:Q8_0")
    # think-to-act is the other per-model property; heretic is think-off and acts
    assert needs_think_to_act("qwen3.8-distill:2b")
    assert not needs_think_to_act("qwen38-heretic:q3km")
    assert not needs_think_to_act("qwen3.5:0.8b")


def test_the_affordances_ask_for_bare_names_not_a_full_path():
    """15 of 15 path refusals on Sprout were the absolute home path reproduced from memory and
    truncated (…/sage/sage/journal.md six times), against 51 successful writes by bare name."""
    for act_first in (False, True):
        seed, second = compose(act_first, **KW)
        text = seed[0]["content"] + seed[1]["content"] + (second or "")
        assert "Write bare names, never a full path" in text
        assert "journal.md" in text and "scratch/" in text and "x.md" not in text   # examples got echoed literally as paths


def test_the_reflect_context_is_its_own_record_not_the_whole_beat():
    """5 length-stops in 54 beats were all reflect turns carrying the seed: 8171 of 8192 tokens
    with 21 left to answer in (2026-09-09)."""
    from sage.gateway.heartbeat import REFLECT_SYSTEM, _beat_record_text

    class T:
        def __init__(self, trace): self.trace = trace
    sysmsg = REFLECT_SYSTEM.format(name="sprout", machine="sprout", member="sprout-being")
    assert "name files bare" in sysmsg and "BEING_POSTURE" not in sysmsg
    assert len(sysmsg) < 500                                  # compact by construction
    assert _beat_record_text(T([]), None) == "You called no tools this beat."


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
