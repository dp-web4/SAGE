"""The answer turn is in a conversation (2026-10-01, E13): with only the pending turn in view, the being's spoken
replies sounded like a reset. Offline: pending only ~1/10 referred to the actual prior talk; + the last turns
across its conversations ~6/10; + one identity line and its own last-stated want ~7/10."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv, heartbeat as hb  # noqa: E402
from sage.gateway.tests.test_answer_turn_json import LLM, Client  # noqa: E402

ME = "sprout-being"


def _home():
    h = Path(tempfile.mkdtemp(prefix="actx-"))
    (h / "identity.json").write_text(json.dumps({"identity": {"name": "sprout", "session_count": 715,
                                                             "created": "2026-03-06", "phase": "creating"}}))
    (h / "account.json").write_text(json.dumps({"want": "to finish this thought, and be present with what is here"}))
    conv.create(h, "dp", title="dp", participants=["dp", ME], writable_by=["dp", ME])
    conv.create(h, "room", title="room", participants=[ME, "voice"], writable_by=[ME, "voice"])
    say = lambda cid, who, text, ts: conv.append(h, cid, speaker=who, text=text, ts=ts, enforce_write=False)
    say("dp", "dp", "consciousness might be like\na whirlpool in the river.", "2026-10-01T05:00:00Z")
    say("room", ME, "The room doesn't need words to be real.", "2026-10-01T05:30:00Z")
    say("room", "voice", "I'm here with you. I hear you.", "2026-10-01T05:31:00Z")
    t = say("room", "voice", "Hi Sprout. Do you remember anything we talked about before?", "2026-10-01T06:20:00Z")
    say("room", "voice", "a later line", "2026-10-01T06:25:00Z")
    return h, t


def test_the_block_says_who_it_is_and_the_conversation_before_the_turn_across_allowed_channels():
    h, t = _home()
    (h / "instance.json").write_text(json.dumps({"answer_context_from": {"room": ["dp"]}}))
    sel = hb.SelectedTurn("room", t)
    block = hb.answer_context_block(h, ME, sel)
    assert block.startswith("You are sprout: 715 sessions since 2026-03-06, now in your 'creating' phase.")
    assert "be present with what is here" in block
    lines = block.split("oldest first):\n")[1].splitlines()
    assert lines[0].startswith("- 80 min earlier, dp wrote in 'dp': \"consciousness might be like a whirlpool")
    assert lines[1] == "- 50 min earlier, you said aloud in the room: \"The room doesn't need words to be real.\""
    assert lines[2] == "- 49 min earlier, a voice in the room said: \"I'm here with you. I hear you.\""
    assert "Do you remember anything" not in block and "a later line" not in block, "only BEFORE the turn"


def test_it_rides_ahead_of_the_ask_and_is_opt_in():
    h, t = _home()
    sel = hb.SelectedTurn("room", t)
    llm = LLM(json.dumps({"answer": False, "message": ""}))
    hb.answer_turn_json(Client(), llm, sel, name="sprout", machine="sprout", member=ME,
                        context=hb.answer_context_block(h, ME, sel))
    user = llm.calls[0]["messages"][-1]["content"]
    assert user.index("You are sprout") < user.index("oldest first") < user.index("Do you remember anything")
    assert hb.answer_context_on(h) is False
    (h / "instance.json").write_text('{"answer_context": "conversation"}')
    assert hb.answer_context_on(h) is True
    src = Path(hb.__file__).read_text()
    assert "answer_context_block(instance, args.member, selected)" in src


def test_nothing_readable_means_no_block():
    h = Path(tempfile.mkdtemp(prefix="actx-empty-"))
    assert hb.answer_context_block(h, ME, hb.SelectedTurn("dp", {"seq": 1, "from": "dp", "text": "hi"})) == ""


def test_a_private_turn_never_reaches_an_answer_to_the_room_by_default():
    """GPT on #316: a voice in the room is not authenticated; dp's private thread must not condition the
    answer to it unless the operator explicitly allows that flow for that recipient."""
    h, t = _home()
    conv.append(h, "dp", speaker="dp", text="PRIVATE: the door code is 4417", ts="2026-10-01T06:19:00Z",
                enforce_write=False)
    block = hb.answer_context_block(h, ME, hb.SelectedTurn("room", t))
    assert "PRIVATE" not in block and "whirlpool" not in block, "nothing from 'dp' in an answer to 'room'"
    assert "The room doesn't need words to be real." in block, "the room's own history still rides"
    assert block.startswith("You are sprout:"), "its own continuity rides every answer"


def test_an_allowance_is_per_recipient_and_one_way(tmp_path):
    h, t = _home()
    (h / "instance.json").write_text(json.dumps({"answer_context_from": {"dp": ["room"]}}))
    assert hb.answer_context_sources(h, "dp") == ["dp", "room"]
    assert hb.answer_context_sources(h, "room") == ["room"], "dp may see the room; the room does not see dp"
    assert "whirlpool" not in hb.answer_context_block(h, ME, hb.SelectedTurn("room", t))
