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


def _beat(effector=None, path=None, ok=True):
    """A stand-in for one phase's result: a trace of (intent, envelope) pairs."""
    from types import SimpleNamespace as NS
    trace = [] if effector is None else [(NS(effector=effector, args={"path": path}), NS(ok=ok))]
    return NS(trace=trace)


def _run_beats(notices, beats):
    """Drive render_inbox + inbox_ledger the way main() does, beat after beat. Each beat is
    (explore_acted, [phase results]). Returns the rendered inbox of every beat."""
    from sage.gateway.heartbeat import inbox_handled, inbox_ledger, render_inbox
    last, seen = {}, []
    for acted, results in beats:
        shown = []
        seen.append(render_inbox(notices, handled=inbox_handled(last), shown=shown))
        last = {"inbox": inbox_ledger(last, notices, results, acted, shown)}
    seen.append(render_inbox(notices, handled=inbox_handled(last)))
    return seen


OLD_REPLY = {"id": 100, "kind": "reply", "from_plugin": "claude-code", "queued_at": "2026-09-21T10:00:00Z",
             "pointer_uri": "sage://conversation/cbp-claude#seq=3000"}
OLD_HANDOFF = {"id": 101, "kind": "handoff", "from_plugin": "legion", "queued_at": "2026-09-21T10:05:00Z",
               "pointer_uri": "shared-context/handoff/h.md"}
OLD_RULING = {"id": 102, "kind": "disposition", "from_plugin": "hestia", "queued_at": "2026-09-21T10:06:00Z",
              "pointer_uri": "hestia://appeal/abc123def456#ruled"}
STALE_REVIEW = {"id": 13840, "kind": "review_done", "from_plugin": "claude-code",
                "queued_at": "2026-09-21T14:15:02.1Z",
                "pointer_uri": "hestia://appeal/8285#ruled-deny-stands;seat-ran-it-14:13Z;use-request_run"}


def test_old_actionable_mail_stays_until_it_is_opened_not_until_it_is_old():
    """GPT HOLD on #164: age is not acknowledgement. The first cut folded every notice queued
    before the last beat began, so an unopened reply, handoff or appeal ruling vanished after
    exactly one beat -- including when that beat crashed before reading it. Pin the negative
    arm: several beats that act but never open them, and all three are still mail."""
    notices = [OLD_REPLY, OLD_HANDOFF, OLD_RULING]
    seen = _run_beats(notices, [(True, [_beat("say", "x")])] * 4)
    for text in seen:
        assert "seq=3000" in text and "shared-context/handoff/h.md" in text, text
        assert "abc123def456" in text, text
        assert "already handled" not in text, text


def test_an_opened_notice_folds_and_only_that_one():
    """The acknowledgement is an act: a successful memory_read of the notice's pointer. The
    reply opened in beat 1 folds from beat 2; the handoff nobody opened stays; a failed read
    acknowledges nothing."""
    notices = [OLD_REPLY, OLD_HANDOFF]
    seen = _run_beats(notices, [(True, [_beat("memory_read", "sage://conversation/cbp-claude"),
                                        _beat("memory_read", "shared-context/handoff/h.md", ok=False)])])
    assert "seq=3000" in seen[0] and "seq=3000" not in seen[1], seen
    assert "shared-context/handoff/h.md" in seen[1], seen[1]
    assert "1 notice(s) already handled" in seen[1], seen[1]


def test_a_finished_review_folds_after_one_beat_that_acted_on_it_not_one_that_crashed():
    """The measured case, 2026-09-22: a 14:15 review_done whose pointer read
    '...seat-ran-it-14:13Z;...;use-request_run' topped cbp-being's inbox for 11 h, and at 01:10
    it acted on that over the seat's answer from 3 minutes before. A finished review carries no
    obligation, so once shown to a beat whose explore turn acted it folds -- but a beat that
    never got to act (crashed, killed) has not been shown anything."""
    crashed = _run_beats([STALE_REVIEW], [(None, []), (False, [])])
    assert all("use-request_run" in t for t in crashed), crashed
    acted = _run_beats([STALE_REVIEW], [(True, [_beat("say", "x")])])
    assert "use-request_run" in acted[0] and "use-request_run" not in acted[1], acted
    assert acted[1].startswith("- 1 notice(s) already handled"), acted[1]


COORDINATION = {"id": 104, "kind": "coordination", "from_plugin": "legion-claude",
                "queued_at": "2026-09-21T10:07:00Z", "pointer_uri": "shared-context/plans/p.md"}


def test_a_coordination_note_shown_to_an_acting_beat_stays_until_its_pointer_is_opened():
    """GPT re-review of c25999cf6: coordination is general work coordination pointing at a
    forum/plan/file, and hestia leaves it out of member_unanswered because it may be acted on in
    silence -- not because seeing it handles it. Several acting beats that never open it: still
    mail. A successful memory_read of its pointer: folds."""
    seen = _run_beats([COORDINATION], [(True, [_beat("say", "x")])] * 3)
    assert all("shared-context/plans/p.md" in t for t in seen), seen
    assert all("already handled" not in t for t in seen), seen
    opened = _run_beats([COORDINATION], [(True, [_beat("memory_read", "shared-context/plans/p.md")])])
    assert "p.md" in opened[0] and "p.md" not in opened[1], opened
    assert opened[1].startswith("- 1 notice(s) already handled"), opened[1]


def test_the_ledger_is_pruned_to_the_inbox_and_an_id_less_notice_never_folds():
    from sage.gateway.heartbeat import inbox_ledger, render_inbox
    last = {"inbox": {"opened": [1, 2, 100], "presented": [13840, 7]}}
    led = inbox_ledger(last, [OLD_REPLY, STALE_REVIEW], [], True, [])
    assert led["opened"] == [100] and led["presented"] == [13840], led
    assert inbox_ledger(last, [], [], True, [])["opened"] == [1, 2, 100], "an unread inbox prunes nothing"
    no_id = dict(OLD_REPLY); no_id.pop("id")
    assert "seq=3000" in render_inbox([no_id], handled={None, 100})


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



def test_the_conversation_header_keys_on_reply_expectation_not_on_pending():
    """Legion's four-row table (review of #172), as a real store, not source introspection —
    the first cut's test pinned two strings and passed with `owed` forced either way.

    2026-09-19..22: dp's last turn was a STATEMENT; the being sent twelve messages into the
    channel. #147 gated the answer phase on reply-expectation; the header must key on the same
    thing, or it is the standing invitation again, conditioned on the wrong fact."""
    import tempfile
    from pathlib import Path
    from sage.gateway import conversations as c
    from sage.gateway.heartbeat import conversation_header
    inst = Path(tempfile.mkdtemp(prefix="hdr-")); me = "b"
    c.create(inst, "dp", title="t", participants=["dp", me], writable_by=["dp", me])
    assert "Nobody is waiting" in conversation_header(inst, me), "empty"
    c.append(inst, "dp", speaker="dp", text="hello, how are you?")
    assert "Someone is waiting" in conversation_header(inst, me), "a question is owed"
    c.append(inst, "dp", speaker=me, text="well, thanks")
    assert "Nobody is waiting" in conversation_header(inst, me), "answered"
    c.append(inst, "dp", speaker="dp", text="good, keep going!")
    assert "Nobody is waiting" in conversation_header(inst, me), \
        "a STATEMENT asks nothing — the row that produced twelve messages"
    assert "say` is for answering a person" in conversation_header(inst, me)

def test_standing_guidance_frames_the_posture_without_changing_it_or_the_tools():
    """posture_framing="standing_guidance" (per-instance): the posture turn says the posture is
    standing guidance that awaits no reply, keeps every tool (say included), and carries the
    posture and the digest byte-identical. cbp-being 2026-10-03 20:41Z: the default framing ("in
    the operator's words ... say in a few words") drew a `say` to dp thanking it for the posture."""
    from sage.gateway.heartbeat import POSTURE_TURN, POSTURE_TURN_STANDING
    _, default = compose(True, **KW)
    _, standing = compose(True, posture_framing="standing_guidance", **KW)
    assert "Standing guidance" in standing and "does not await a reply" in standing
    assert "act within it" in standing and "dp's posture" in standing, "attribution kept, truthfully"
    assert "in the operator's words" not in standing
    assert "say" in EXPLORE_TOOLS and TOOLS in standing, "no tool removed, say still offered"
    # the posture itself is unchanged: the same text, verbatim, in both framings
    assert POSTURE in standing and POSTURE in default
    assert standing.split(POSTURE)[1].split("This is still your time.")[0] == \
        default.split(POSTURE)[1].split("This is still your time.")[0], "digest block identical"
    # default unchanged; unknown values fall back to it; posture-first has no posture turn at all
    assert default == POSTURE_TURN.format(posture=POSTURE, digest="DIGEST", tools=TOOLS)
    assert compose(True, posture_framing="nonsense", **KW)[1] == default
    assert compose(False, posture_framing="standing_guidance", **KW)[1] is None
    assert standing == POSTURE_TURN_STANDING.format(posture=POSTURE, digest="DIGEST", tools=TOOLS)


def test_posture_framing_is_per_instance_and_recorded():
    import inspect
    from sage.gateway import heartbeat
    from sage.gateway.heartbeat import posture_framing_for
    assert posture_framing_for(None) is None and posture_framing_for({}) is None
    assert posture_framing_for({"posture_framing": "nonsense"}) is None
    assert posture_framing_for({"posture_framing": "standing_guidance"}) == "standing_guidance"
    src = inspect.getsource(heartbeat)
    assert '"posture_framing": posture_framing_for(instance_config(instance))' in src, "recorded per beat"
    assert "posture_framing=posture_framing_for(instance_config(instance))" in src, "reaches compose"


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)


def test_the_conversation_header_keys_on_reply_expectation_not_on_pending():
    """Legion's four-row table (review of #172), as a real store, not source introspection —
    the first cut's test pinned two strings and passed with `owed` forced either way.

    2026-09-19..22: dp's last turn was a STATEMENT; the being sent twelve messages into the
    channel. #147 gated the answer phase on reply-expectation; the header must key on the same
    thing, or it is the standing invitation again, conditioned on the wrong fact."""
    import tempfile
    from pathlib import Path
    from sage.gateway import conversations as c
    from sage.gateway.heartbeat import conversation_header
    inst = Path(tempfile.mkdtemp(prefix="hdr-")); me = "b"
    c.create(inst, "dp", title="t", participants=["dp", me], writable_by=["dp", me])
    assert "Nobody is waiting" in conversation_header(inst, me), "empty"
    c.append(inst, "dp", speaker="dp", text="hello, how are you?")
    assert "Someone is waiting" in conversation_header(inst, me), "a question is owed"
    c.append(inst, "dp", speaker=me, text="well, thanks")
    assert "Nobody is waiting" in conversation_header(inst, me), "answered"
    c.append(inst, "dp", speaker="dp", text="good, keep going!")
    assert "Nobody is waiting" in conversation_header(inst, me), \
        "a STATEMENT asks nothing — the row that produced twelve messages"
    assert "say` is for answering a person" in conversation_header(inst, me)
