"""Hermetic: the heartbeat's two presentations of the one posture, and the per-model
predicates that pick them. No model, no gate."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.governed_turn import acts_under_posture, needs_think_to_act  # noqa: E402
from sage.gateway.heartbeat import EXPLORE_TOOLS, account_generate, compose  # noqa: E402

POSTURE = "## Why you are awake\n\nA heartbeat is not a question. Nobody asked you anything."
TOOLS = ", ".join(EXPLORE_TOOLS)
KW = dict(name="sprout", machine="sprout", member="sprout-being", posture_text=POSTURE, nothink="",
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


def test_nothink_suffix_rides_every_turn_when_set():
    seed, second = compose(True, **{**KW, "nothink": "/no_think"})
    assert seed[0]["content"].rstrip().endswith("/no_think")
    assert seed[1]["content"].rstrip().endswith("/no_think")
    assert second.rstrip().endswith("/no_think")


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
    sysmsg = REFLECT_SYSTEM.format(name="sprout", machine="sprout", member="sprout-being", nothink="")
    assert "name files bare" in sysmsg and "BEING_POSTURE" not in sysmsg
    assert len(sysmsg) < 500                                  # compact by construction
    assert _beat_record_text(T([]), None) == "You called no tools this beat."


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)


# --- the account turn's counters (2026-09-12) ------------------------------------------

class _LLM:
    """Enough of OllamaIRP for _sent_budget: the adapter-resolved budget wins."""
    max_response_tokens = 1024

    def resolve_num_predict(self):
        return 6000


def test_the_account_turn_records_the_counters_its_own_response_carried():
    """It takes no tools, so it never ran through the tool loop and had no on_generate --
    the beat's largest generate was written into no section at all."""
    aresp = {"content": "PLACE: here", "raw": {"done_reason": "stop",
                                               "prompt_eval_count": 7762, "eval_count": 300}}
    entry = account_generate(aresp, _LLM())
    assert entry == {"done_reason": "stop", "prompt_eval_count": 7762, "eval_count": 300,
                     "retried": 0, "num_predict": 6000}


def test_an_account_turn_that_did_not_land_records_nothing_rather_than_zeroes():
    """A zero counter reads downstream as a free window; absence is a counted skip."""
    assert account_generate({"content": "[OllamaIRP: Error: ...]", "raw": {}}, _LLM()) is None
    assert account_generate({}, _LLM()) is None
    assert account_generate(None, _LLM()) is None


def test_the_entry_carries_the_same_five_keys_the_tool_loop_writes():
    """Shape discovery and the census read one shape; a sixth key or a missing one would make
    the account rows sort differently from every other generate in the beat."""
    from sage.gateway.being_tool_loop import run_ollama_tool_turn  # noqa: F401
    entry = account_generate({"raw": {"done_reason": "stop", "prompt_eval_count": 1,
                                      "eval_count": 2}}, _LLM())
    assert set(entry) == {"done_reason", "prompt_eval_count", "eval_count", "retried", "num_predict"}
