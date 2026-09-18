"""Conversations: both directions in one ordered record, per-conversation write access.

dp's acceptance criteria, 2026-09-07, pinned as tests:
  1. dp can VIEW the seat's conversation with the being and not comment on it;
  2. dp can view and SPEAK in dp's own conversation with the being;
  3. all chats preserved, accessible, display bounded by the existing 'x recent' protocol.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv  # noqa: E402


def _inst():
    return Path(tempfile.mkdtemp(prefix="conv-"))


def _two(inst):
    conv.create(inst, "dp", title="dp and being",
                participants=["dp", "legion-being"], writable_by=["dp", "legion-being"])
    conv.create(inst, "legion-claude", title="seat and being",
                participants=["legion-claude", "legion-being"],
                writable_by=["legion-claude", "legion-being"])


def test_dp_may_read_the_seats_conversation_and_not_speak_in_it():
    """Acceptance 1. Read access and write access are separate, per conversation. dp asked
    for exactly this and asked for it narrowly — multiparty comes later, because a third
    voice appearing mid-thread changes what the earlier turns meant."""
    inst = _inst(); _two(inst)
    conv.append(inst, "legion-claude", speaker="legion-claude", text="a seat turn")
    assert len(conv.recent(inst, "legion-claude")) == 1, "dp can read it"

    try:
        conv.append(inst, "legion-claude", speaker="dp", text="dp butting in")
        raise AssertionError("dp must not be able to speak in the seat's conversation")
    except ValueError as e:
        assert "may read" in str(e) and "may not speak" in str(e), e
    assert conv.count(inst, "legion-claude") == 1, "the refused turn must not land"


def test_dp_speaks_in_its_own_conversation_and_the_being_answers():
    """Acceptance 2, and the thing that makes it a conversation rather than a note: both
    directions land in ONE ordered record, each turn attributed."""
    inst = _inst(); _two(inst)
    conv.append(inst, "dp", speaker="dp", text="what are you working on?")
    conv.append(inst, "dp", speaker="legion-being", text="the check organ", witness="act-1")
    turns = conv.recent(inst, "dp")
    assert [t["from"] for t in turns] == ["dp", "legion-being"]
    assert [t["seq"] for t in turns] == [1, 2], "sequence is the record's order"
    assert turns[1]["witness"] == "act-1", "a being's turn carries its witnessed act"

    # whose move is it: unanswered turns are addressed, not inferred
    assert conv.awaiting(inst, "dp", "legion-being") == []
    conv.append(inst, "dp", speaker="dp", text="and after that?")
    pend = conv.awaiting(inst, "dp", "legion-being")
    assert len(pend) == 1 and pend[0]["text"] == "and after that?"


def test_everything_is_kept_and_only_the_view_is_bounded():
    """Acceptance 3. Storage is append-only and total; `recent` bounds the DISPLAY, using
    the fleet's existing convention (sage-daemon /chat-history?limit=N)."""
    inst = _inst(); _two(inst)
    for i in range(conv.DEFAULT_LIMIT + 25):
        conv.append(inst, "dp", speaker="dp", text=f"turn {i}")
    total = conv.DEFAULT_LIMIT + 25
    assert conv.count(inst, "dp") == total, "nothing is deleted"
    assert len(conv.recent(inst, "dp")) == conv.DEFAULT_LIMIT, "the view is bounded"
    assert len(conv.recent(inst, "dp", limit=total)) == total, "and the whole is reachable"
    assert conv.recent(inst, "dp")[-1]["text"] == f"turn {total - 1}", "the last N, newest kept"

    # the file on disk is still every line
    log = inst / "conversations" / "dp.jsonl"
    assert sum(1 for l in log.read_text().splitlines() if l.strip()) == total


def test_a_turn_is_never_edited_and_a_speaker_is_never_invented():
    inst = _inst(); _two(inst)
    conv.append(inst, "dp", speaker="dp", text="one")
    before = (inst / "conversations" / "dp.jsonl").read_text()
    conv.append(inst, "dp", speaker="dp", text="two")
    after = (inst / "conversations" / "dp.jsonl").read_text()
    assert after.startswith(before), "append-only: earlier turns are byte-identical"

    for bad in ("", "   "):
        try:
            conv.append(inst, "dp", speaker="dp", text=bad)
            raise AssertionError("an empty turn is not a turn")
        except ValueError:
            pass
    try:
        conv.append(inst, "nope", speaker="dp", text="x")
        raise AssertionError("a conversation that does not exist cannot be spoken into")
    except ValueError as e:
        assert "no such conversation" in str(e)


def test_create_is_idempotent_and_does_not_rewrite_who_may_speak():
    """Re-creating must not silently widen access on a thread already underway."""
    inst = _inst()
    conv.create(inst, "dp", title="a", participants=["dp"], writable_by=["dp"])
    again = conv.create(inst, "dp", title="hijacked", participants=["dp", "someone"],
                        writable_by=["dp", "someone"])
    assert again["writable_by"] == ["dp"] and again["title"] == "a"


def test_the_beat_block_marks_what_is_unanswered():
    inst = _inst(); _two(inst)
    conv.append(inst, "dp", speaker="dp", text="a question")
    block = conv.render_for_being(inst, "legion-being")
    assert 'say to="dp"' in block, "it is told how to reply"
    assert "unanswered" in block
    assert "saying nothing is also a choice" in block.lower()
    # a conversation it is not in does not appear
    conv.create(inst, "private", title="p", participants=["dp"], writable_by=["dp"])
    assert "id: private" not in conv.render_for_being(inst, "legion-being")


def test_say_is_actually_offered_in_a_beat_not_only_registered():
    """A VERB IN THE REGISTRY AND NOT IN THE OFFERED SET IS A VERB THE BEING DOES NOT HAVE.

    Measured 2026-09-07: `say` was added to the registry and its description table, the
    conversations block rendered in the being's state with dp's turn marked unanswered —
    and the being spent all fourteen explore steps reading its own source and closed the
    beat without replying. It looked exactly like a choice. It was the seat forgetting one
    list. `config.tools_offered` on the beat record is what made the answer a one-command
    check instead of an interpretation."""
    from sage.gateway.being_gate_client import ollama_tools
    from sage.gateway.heartbeat import EXPLORE_TOOLS, REFLECT_TOOLS

    assert "say" in EXPLORE_TOOLS, "the being must be able to answer while exploring"
    assert "say" in REFLECT_TOOLS, "and at reflection, where a beat accounts for itself"

    for offered in (EXPLORE_TOOLS, REFLECT_TOOLS):
        names = [t["function"]["name"] for t in ollama_tools(offered)]
        assert "say" in names, f"say must reach the model in {offered}"

    schema = next(t for t in ollama_tools(EXPLORE_TOOLS) if t["function"]["name"] == "say")
    params = schema["function"]["parameters"]
    assert set(params["required"]) == {"to", "text"}
    assert "saying nothing" in schema["function"]["description"].lower()


def test_a_damaged_line_is_reported_as_damage_not_as_history():
    """FOUND BY legion-being, 2026-09-07, from reading conversations.py during a beat —
    before any seat had noticed, and correctly labelled by it as "suspected-from-reading,
    not check-verified" because it cannot author a test until M1 lands.

    `count()` counted every non-empty line while `recent()` skipped ones that raise
    JSONDecodeError, so one corrupt line made "showing the last X of {total}" claim history
    that is not there. A FALSE ABSENCE — the inverse of the silent read truncation fixed
    the same morning: there it was shown less than it thought, here it is told there is
    more than exists. Both make it reason about a gap that is not where it believes."""
    inst = _inst(); _two(inst)
    conv.append(inst, "dp", speaker="dp", text="one")
    conv.append(inst, "dp", speaker="dp", text="two")
    log = inst / "conversations" / "dp.jsonl"
    with open(log, "a") as f:                       # a truncated write, as a crash leaves
        f.write('{"ts":"2026-09-08T00:00:00Z","seq":3,"from":"dp","te\n')
    conv.append(inst, "dp", speaker="dp", text="four")

    assert conv.count(inst, "dp") == len(conv.recent(inst, "dp")) == 3, \
        "the count and the reader must agree, or the view misdescribes the record"
    assert conv.integrity(inst, "dp") == {"readable": 3, "unreadable": 1, "lines": 4}

    block = conv.render_for_being(inst, "legion-being")
    assert "1 line(s) in this conversation are damaged" in block, \
        "damage is reported as damage, never hidden inside a count"
    assert "showing the last 3 of 4" not in block, "and never impersonates withheld history"

    # sequence stays monotonic ACROSS the scar: a gap reads as a scar, a duplicate would
    # make two different turns share one identity
    assert conv.append(inst, "dp", speaker="dp", text="five")["seq"] == 5


def test_awaiting_means_unseen_not_merely_spoken_after():
    """2026-09-08 06:17Z: two seat turns arrived WHILE the being's beat ran; it replied at
    reflection without having read them. By "since I last spoke" they counted as answered.
    Addressed-and-unread is the real fact; "spoke after" only proxies it."""
    inst = _inst(); _two(inst)
    conv.append(inst, "legion-claude", speaker="legion-claude", text="q1")
    # the being is SHOWN q1 (render marks it seen), then answers
    conv.render_for_being(inst, "legion-being")
    conv.append(inst, "legion-claude", speaker="legion-being", text="a1")
    assert conv.awaiting(inst, "legion-claude", "legion-being") == []
    # two seat turns land mid-beat, THEN the being speaks without having seen them
    conv.append(inst, "legion-claude", speaker="legion-claude", text="q2")
    conv.append(inst, "legion-claude", speaker="legion-claude", text="q3")
    conv.append(inst, "legion-claude", speaker="legion-being", text="a-blind")
    pend = conv.awaiting(inst, "legion-claude", "legion-being")
    assert [t["text"] for t in pend] == ["q2", "q3"], "unseen turns stay awaiting even after it spoke"
    block = conv.render_for_being(inst, "legion-being")
    assert "2 turn(s) from legion-claude" in block and "unanswered" in block
    # now they have been shown: nothing awaits
    assert conv.awaiting(inst, "legion-claude", "legion-being") == []


def test_concurrent_writers_never_interleave_or_reuse_a_sequence():
    """Two processes write these files for real — the Python heartbeat (the being's `say`)
    and the Rust daemon (a turn typed into the dashboard). A turn is prose and exceeds
    PIPE_BUF routinely, so O_APPEND alone is not atomic for it; the failure is two
    half-lines, neither parseable, in the durable account of what was said. flock on both
    sides, seq assigned inside the lock. Three processes x 20 long turns here; the manual
    proof at commit time was six x 40."""
    import json
    import subprocess
    import sys as _sys
    inst = _inst(); _two(inst)
    prog = (
        "import sys; sys.path.insert(0, %r); from pathlib import Path; "
        "from sage.gateway import conversations as c; "
        "[c.append(Path(%r), 'dp', speaker='dp', text='x'*5000 + str(i)) for i in range(20)]"
        % (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")), str(inst))
    )
    procs = [subprocess.Popen([_sys.executable, "-c", prog]) for _ in range(3)]
    assert all(p.wait(timeout=60) == 0 for p in procs)
    lines = [l for l in (inst / "conversations" / "dp.jsonl").read_text().splitlines() if l.strip()]
    assert len(lines) == 60
    seqs = [json.loads(l)["seq"] for l in lines]          # every line parses
    assert sorted(seqs) == list(range(1, 61)), "no duplicate, no gap"
    assert conv.integrity(inst, "dp")["unreadable"] == 0



def test_turn_provenance_is_recorded_and_shown(tmp_path):
    """GPT on SAGE#56: `from: dp` is only as good as the channel that wrote it. The store
    records the channel (`via`); the being's view tags unsigned channels and says why."""
    from sage.gateway import conversations as C
    C.create(tmp_path, "dp", title="dp", participants=["dp", "b"], writable_by=["dp", "b"])
    a = C.append(tmp_path, "dp", speaker="dp", text="do X", via="dp-console")
    b = C.append(tmp_path, "dp", speaker="b", text="ok", via="say")
    c = C.append(tmp_path, "dp", speaker="dp", text="legacy")            # no via
    assert a["via"] == "dp-console" and b["via"] == "say" and "via" not in c
    out = C.render_for_being(tmp_path, "b")
    assert "**dp** (" in out
    assert out.count(C.UNSIGNED_TAG) == 1                                # the console turn only
    assert "provenance unrecorded" in out                                # the legacy one, named
    assert "purported until the seat confirms" in out
    line_b = [l for l in out.splitlines() if l.startswith("- **b**")][0]
    assert "unsigned" not in line_b and "unrecorded" not in line_b       # say is the gated path



def test_a_long_turn_is_shown_capped_and_points_at_its_whole(tmp_path):
    """2026-09-08: two seat turns of 25.6k chars were re-rendered into every beat (~9k of
    24.5k tokens) and the being ran out of room to act. The record stays whole; what one
    beat SHOWS is bounded, and the cap says where the rest is — by seq, the raw line."""
    from sage.gateway import conversations as C
    C.create(tmp_path, "s", title="s", participants=["a", "b"], writable_by=["a", "b"])
    C.append(tmp_path, "s", speaker="a", text="short", via="say")
    long = "x" * 5000
    t = C.append(tmp_path, "s", speaker="a", text=long, via="say")
    full = C.render_for_being(tmp_path, "b")
    assert long in full                                                  # uncapped by default
    capped = C.render_for_being(tmp_path, "b", turn_chars=1000)
    assert long not in capped and "x" * 1000 in capped and "x" * 1001 not in capped
    assert f"+4000 chars; the whole turn: memory_read conversations/s.jsonl from_line {t['seq']} lines 1" in capped
    assert "short" in capped                                             # a short turn is untouched
    assert C.recent(tmp_path, "s")[-1]["text"] == long                   # the record is whole



def test_seen_is_not_answered(tmp_path):
    """dp's 16:30Z turn (2026-09-08) was shown on eight beats that could not act, marked
    seen on the first, and then vanished from the being's sense of what it owed."""
    from sage.gateway import conversations as C
    C.create(tmp_path, "dp", title="dp", participants=["dp", "b"], writable_by=["dp", "b"])
    C.append(tmp_path, "dp", speaker="dp", text="have fun!", via="dp-console")
    first = C.render_for_being(tmp_path, "b")
    assert "1 turn(s) from dp since you last spoke here" in first          # unseen: the loud marker
    again = C.render_for_being(tmp_path, "b")
    assert "since you last spoke here" not in again                        # seen now
    assert "The last word here is dp's (seq 1" in again and "still yours to answer" in again
    C.append(tmp_path, "dp", speaker="b", text="I will.", via="say")
    after = C.render_for_being(tmp_path, "b")
    assert "last word here" not in after and "since you last spoke" not in after



def test_drain_new_for_returns_unseen_turns_once(tmp_path):
    """Mid-beat delivery: what arrived, then nothing until something else arrives."""
    from sage.gateway import conversations as C
    C.create(tmp_path, "dp", title="dp", participants=["dp", "b"], writable_by=["dp", "b"])
    assert C.drain_new_for(tmp_path, "b") == ""                     # quiet
    C.append(tmp_path, "dp", speaker="dp", text="are you there?", via="dp-console")
    first = C.drain_new_for(tmp_path, "b")
    assert "are you there?" in first and "**dp**" in first and 'say to="dp"' in first
    assert C.drain_new_for(tmp_path, "b") == ""                     # not repeated
    C.append(tmp_path, "dp", speaker="b", text="I am", via="say")
    assert C.drain_new_for(tmp_path, "b") == ""                     # its own turn is not mail
    C.append(tmp_path, "dp", speaker="dp", text="good", via="dp-console")
    assert "good" in C.drain_new_for(tmp_path, "b")


def test_drain_new_for_can_look_without_marking(tmp_path):
    from sage.gateway import conversations as C
    C.create(tmp_path, "dp", title="dp", participants=["dp", "b"], writable_by=["dp", "b"])
    C.append(tmp_path, "dp", speaker="dp", text="hello", via="dp-console")
    assert "hello" in C.drain_new_for(tmp_path, "b", mark=False)
    assert "hello" in C.drain_new_for(tmp_path, "b")                # still unseen
    assert C.drain_new_for(tmp_path, "b") == ""


def test_an_answered_turn_is_shown_briefly_and_a_live_one_in_full():
    """The being was paying rent on its own finished conversations.

    2026-09-13: the seat sent nine turns in a day and the conversations block reached
    10,205 chars — ~3.5k tokens of a 24,576 window, re-rendered every beat, most of it
    exchanges already closed. Everything up to the being's own last word here has been read
    and replied to; it is shown briefly, with the marker naming the seq so the whole turn is
    one read away. What arrived AFTER it last spoke is live, and shown at full width."""
    import tempfile
    from pathlib import Path
    from sage.gateway import conversations as conv
    from sage.gateway.conversations import ANSWERED_TURN_CHARS

    inst = Path(tempfile.mkdtemp(prefix="answered-"))
    conv.create(inst, "seat", title="seat", participants=["legion-being", "legion-claude"],
                writable_by=["legion-being", "legion-claude"])
    long_seat = "S" * 1100
    conv.append(inst, "seat", speaker="legion-claude", text=long_seat, enforce_write=False)
    conv.append(inst, "seat", speaker="legion-being", text="B" * 1100, enforce_write=False)
    conv.append(inst, "seat", speaker="legion-claude", text="L" * 1100, enforce_write=False)

    out = conv.render_for_being(inst, "legion-being", per_conv=6, turn_chars=1200)

    # the closed exchange: shortened, and the marker says where the rest is
    assert ("S" * ANSWERED_TURN_CHARS) in out
    assert ("S" * (ANSWERED_TURN_CHARS + 1)) not in out
    assert "memory_read conversations/seat.jsonl" in out
    # the being's OWN answered turn is history too
    assert ("B" * (ANSWERED_TURN_CHARS + 1)) not in out
    # what arrived after it last spoke is live and uncut at this rung
    assert ("L" * 1100) in out


def test_the_short_cap_never_widens_a_narrow_rung():
    """At a rung narrower than the answered cap, the rung wins — the ladder exists because
    the window would not otherwise fit, and this must never fight it."""
    import tempfile
    from pathlib import Path
    from sage.gateway import conversations as conv

    inst = Path(tempfile.mkdtemp(prefix="narrow-"))
    conv.create(inst, "seat", title="seat", participants=["legion-being", "legion-claude"],
                writable_by=["legion-being", "legion-claude"])
    conv.append(inst, "seat", speaker="legion-claude", text="S" * 900, enforce_write=False)
    conv.append(inst, "seat", speaker="legion-being", text="ack", enforce_write=False)

    out = conv.render_for_being(inst, "legion-being", per_conv=6, turn_chars=200)
    assert ("S" * 200) in out and ("S" * 201) not in out


def test_the_beat_state_puts_a_ceiling_on_the_conversations_block(tmp_path, monkeypatch):
    """Until the context-fit ladder lands (Legion's review of SAGE#81): own_state renders the
    conversations block with explicit bounds, never unbounded. Legion's live store measured
    20,735 chars unbounded; one long thread must not be able to take the whole window."""
    from sage.gateway import heartbeat, conversations as C
    seen = {}

    def spy(instance, me, **kw):
        seen.update(kw)
        return ""
    monkeypatch.setattr(C, "render_for_being", spy)
    heartbeat.own_state(tmp_path, "b")
    assert seen.get("per_conv") == heartbeat.CONV_PER_CONV and seen.get("turn_chars") == heartbeat.CONV_TURN_CHARS
    assert heartbeat.CONV_TURN_CHARS and heartbeat.CONV_PER_CONV <= 12


def test_render_without_mark_does_not_consume_the_unanswered_marker():
    """A seat that LOOKS at the block must not change it.

    Measured 2026-09-14: a seat diagnostic called render_for_being to ask what the being
    could see of a turn, and the call marked every pending turn read. The being's own
    "unanswered" marker for a message it had not been shown was gone, and the record said
    it had seen something it had not. The read-only path was the destructive one.
    """
    inst = _inst(); _two(inst)
    conv.append(inst, "legion-claude", speaker="legion-claude", text="a turn the being has not seen")

    before = conv.awaiting(inst, "legion-claude", "legion-being")
    assert len(before) == 1, "precondition: exactly one unanswered turn"

    # Looking twice must not change the answer either time.
    conv.render_for_being(inst, "legion-being", mark=False)
    conv.render_for_being(inst, "legion-being", mark=False)
    still = conv.awaiting(inst, "legion-claude", "legion-being")
    assert len(still) == 1, (
        f"render_for_being(mark=False) consumed the unanswered marker: {len(still)} left")

    # And the beat's own render, which DELIVERS, still marks.
    conv.render_for_being(inst, "legion-being")
    assert conv.awaiting(inst, "legion-claude", "legion-being") == [], \
        "the delivering render must still mark turns seen"


def test_a_placeholder_is_not_a_message():
    """Specimen (sprout-being, qwen3.8-distill:2b, 2026-09-18 21:04:02Z): dp received
    "[Your brief, final word-only summary of your response]" through `say`. The template
    completion documented in SMALL_MODEL_LEGIBILITY 1.8, occupying the ARGUMENT rather than
    the reply — where no prompt-side guard could see it, because by then it is already an
    argument on its way to a person."""
    from sage.gateway.conversations import is_stub
    assert is_stub("[Your brief, final word-only summary of your response]")
    assert is_stub("  [Your complete, thoughtful journal entry responding to dp's question]  ")
    assert not is_stub("The world is a process with no end point and no right answer.")
    assert not is_stub("I'm here, listening. No pressure on me.")
    assert not is_stub(""), "empty is caught by the empty check, not this one"
    assert not is_stub("[note] and then the actual message, which is real content."), \
        "a bracket that opens a real message is not a placeholder"
    assert not is_stub("[short]"), "too short to be one of these briefs"
