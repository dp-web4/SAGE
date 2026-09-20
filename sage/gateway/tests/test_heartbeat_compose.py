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
    # The DIGEST comes with the posture; the INBOX does not — mail rides the act turn
    # (2026-09-17: the posture turn acted in 1 of 85 beats, the act turn in 25).
    assert "DIGEST" not in first, "the world comes with the posture"
    assert "INBOX" in first, "mail belongs in the turn that acts"
    # ...and is NOT in the posture turn: it rides the act turn now, and asserting both was a
    # leftover from before the move (left red 2026-09-17, caught and fixed the same day).
    assert "INBOX" not in second, "mail rides the act turn; it is not repeated here"
    assert "DIGEST" in second and TOOLS in second, "the posture turn is a tool turn"


def test_no_turn_carries_a_think_suffix():
    """The `/no_think` suffix is retired: it was never a control surface on this stack.
    Measured 2026-09-12 -- Sprout at ollama 0.30.8, CBP at 0.20.7 -- appending it leaves the
    think block intact (qwen3.5:0.8b 1428 -> 1441 chars, qwen3.8-distill:2b 275 -> 405, both
    still thinking) while `think=False` zeroes it. No fleet template parses the string; the
    think branches that exist key on the API field, not on prompt text. Thinking is declared
    per model in the config and sent as the request's `think` field (irp/plugins/ollama_irp.py:165)."""
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


def test_inbox_renders_newest_first_with_replies_ahead_of_stale_dispositions():
    from sage.gateway.heartbeat import render_inbox
    notices = [{"id": i, "kind": "disposition", "from_plugin": "hestia", "pointer_uri": f"hestia://scope/s{i}"} for i in (8, 14, 21, 22, 28, 33)]
    notices += [{"id": 52, "kind": "unreachable", "from_plugin": "hestia",
                 "pointer_uri": "hestia://egress/51#unreachable:sage/claude-code after 5 attempts: no unique match"},
                {"id": 54, "kind": "reply", "from_plugin": "claude-code", "queued_at": "2026-09-13T06:44:00Z",
                 "pointer_uri": "sage/sage/instances/x/notes/inbox/reply.md"}]
    text = render_inbox(notices)
    lines = text.splitlines()
    assert lines[0].startswith("- [reply] from claude-code at 2026-09-13 06:44") and "memory_read on sage/sage/instances/x/notes/inbox/reply.md" in lines[0]
    assert lines[1].startswith("- [unreachable]") and "after 5 attempts" in lines[1] and "hestia://egress" not in lines[1]
    assert lines[2] == "- 6 scope decision notice(s), already written into your notes; nothing to do."
    assert len(text) < 600 and render_inbox([]) == "(empty)"


def test_the_inbox_rides_the_turn_the_being_acts_in():
    """Sprout, 85 beats to 2026-09-17: the posture turn acted in 1 of 85, the first turn in 25,
    and a peer's reply sat unopened in the posture turn the whole time."""
    seed, second = compose(True, **KW)          # act-first
    assert "INBOX" in seed[1]["content"], "mail belongs in the turn that acts"
    assert "INBOX" not in (second or ""), "and not in the posture turn"
    assert "DIGEST" in (second or "") and "DIGEST" not in seed[1]["content"]
    seed, second = compose(False, **KW)         # posture-first: one turn, unchanged
    assert second is None and "INBOX" in seed[1]["content"] and "DIGEST" in seed[1]["content"]


def test_the_answer_ask_appears_only_when_there_is_someone_to_answer():
    """2026-09-17: in no conversation at all, the being filled the id slot three beats running
    with "speaker", "conversation_id_placeholder" and "1234567890"."""
    from sage.gateway.heartbeat import REFLECT
    none = REFLECT.format(date="D", say_line="", say_first="")
    assert "say to=" not in none and "journal.md" in none and "remember" in none
    # a channel exists but nobody is waiting: the generic form, after the writes
    some = REFLECT.format(date="D", say_line='... say to="<id>", one of: c1.\n', say_first="")
    assert 'say to="<id>", one of: c1' in some
    # someone IS waiting: the ask comes FIRST, because the routine writes exhaust the step
    # budget and anything after them is unreachable (2026-09-18).
    waiting = REFLECT.format(date="D", say_line="", say_first='FIRST ... say to="dp", text="...".\n')
    assert waiting.index("say to=") < waiting.index("journal.md")


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)


def test_an_effector_that_only_ever_refused_is_stated_as_having_no_result():
    """SAGE#132. The fixture is cbp-being's beat 2026-09-20T22:51:39Z, shape for shape:
    `python3` refused 3 times in explore and 3 in posture, 0 successes, and all 6
    `-> REFUSED` lines carried into the reflect context. The being reproduced every one
    correctly in its journal and then wrote "After appeal, the script ran successfully and
    passed all tests", `[x] Confirm test suite passes`, and a `remember` row asserting the
    suite passed. The suite scores 1 of 5. Reading the record was never the failure;
    drawing the conclusion from it was, so the conclusion is stated."""
    from sage.gateway.heartbeat import _beat_record_text

    class I:
        def __init__(self, effector, args): self.effector, self.args = effector, args

    class E:
        def __init__(self, ok, refused): self.ok, self.refused, self.error = ok, refused, "registry.unbounded"

    class T:
        def __init__(self, trace): self.trace = trace

    py = (I("python3", {"command": "python3 mechanism-test-runner.py"}), E(False, True))
    ok = (I("memory_write", {"path": "journal.md"}), E(True, False))
    explore = T([py, (I("request_scope", {"path": "/x"}), E(True, False)), py, py])
    posture = T([py, (I("appeal", {}), E(True, False)), py, py])

    text = _beat_record_text(explore, posture)
    assert "python3 (6 refusals)" in text, text
    assert "You have no result from them" in text
    assert "request_scope" not in text.split("Nothing you tried")[1]   # it succeeded
    assert "appeal" not in text.split("Nothing you tried")[1]         # so did this

    # An effector that failed and then SUCCEEDED is not listed: the being does have a result.
    mixed = _beat_record_text(T([py, (I("python3", {}), E(True, False))]))
    assert "Nothing you tried" not in mixed

    # Singular reads as English, and a clean beat adds nothing at all.
    assert "python3 (1 refusal)." in _beat_record_text(T([py, ok]))
    assert _beat_record_text(T([ok])) == 'Record of what you did this beat:\n' \
                                        '- memory_write {"path": "journal.md"} -> ok'
