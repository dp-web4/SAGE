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


def test_the_answer_temperature_samples_the_answer_turn_alone_and_is_restored(tmp_path):
    seen = []

    class TLLM(LLM):
        temperature = 0.4

        def get_chat_response(self, messages, tools=None, fmt=None):
            seen.append(self.temperature)
            return super().get_chat_response(messages, tools, fmt)
    h, t = _home()
    llm = TLLM(json.dumps({"answer": False, "message": ""}))
    res = hb.answer_turn_json(Client(), llm, hb.SelectedTurn("room", t), name="s", machine="s", member=ME,
                              temperature=0.7)
    assert seen == [0.7] and llm.temperature == 0.4, "this turn only; the beat's temperature is restored"
    assert res.answer_form["temperature"] == 0.7
    hb.answer_turn_json(Client(), llm, hb.SelectedTurn("room", t), name="s", machine="s", member=ME)
    assert seen[-1] == 0.4, "unset: unchanged"
    assert hb.answer_temperature(tmp_path) is None
    (tmp_path / "instance.json").write_text('{"answer_temperature": 9}')
    assert hb.answer_temperature(tmp_path) == 1.5, "clamped"
    src = Path(hb.__file__).read_text()
    assert "temperature=answer_temperature(instance)" in src


def test_the_answer_turn_is_told_what_it_can_do_and_that_it_has_no_internet():
    from sage.gateway import toolset as ts
    line = hb.abilities_line(ts.unavailable({"inventory": {"verbs": ["camera", "gaze", "speak"]}}, "/tmp/wt", {}))
    assert "look through your eyes" in line and "ask a sibling" in line
    assert "search the code repository checked out on this seat (not your home)" in line
    for plumbing in ("tool", "say", "peer_ask", "camera"):
        assert plumbing not in line, f"harness word {plumbing!r} in the being's facts (LEGIBILITY 1.14)"
    assert line.endswith("You have no internet access."), "true while no web verb is in the toolset"
    h, t = _home()
    assert "no internet" not in hb.answer_context_block(h, ME, hb.SelectedTurn("room", t)), "not tied to the option"


def test_every_answer_prompt_carries_what_it_can_do_even_without_answer_context():
    """GPT on #334: an instance with NO answer_context (Sprout's checked-in config) must still be told."""
    h, t = _home()
    assert hb.answer_context_on(h) is False
    llm = LLM(json.dumps({"answer": False, "message": ""}))
    hb.answer_turn_json(Client(), llm, hb.SelectedTurn("room", t), name="s", machine="s", member=ME)
    user = llm.calls[0]["messages"][-1]["content"]
    assert hb.abilities_line() in user and user.index(hb.abilities_line()) < user.index("You have not answered yet")


def test_answer_then_act_is_opt_in_and_wired_without_say_or_speak(tmp_path):
    assert hb.act_after_answer_on(tmp_path) is False
    for v in ('"false"', "1", '"yes"', "null"):
        (tmp_path / "instance.json").write_text('{"act_after_answer": %s}' % v)
        assert hb.act_after_answer_on(tmp_path) is False, f"{v} is not a literal true: off"
    (tmp_path / "instance.json").write_text('{"act_after_answer": true}')
    assert hb.act_after_answer_on(tmp_path) is True
    src = Path(hb.__file__).read_text()
    i = src.index("ANSWER, THEN ACT (2026-10-02)")
    block = src[i:i + 2200]
    assert 'not in ("say", "speak")' in block and "should_yield=_yield_for_a_person" in block
    assert "act_form=explore_turn_mode(instance)" in block and 'get("sent")' in block and "preempted" in block
    assert '"act_after_answer": _turn(act_after)' in src
    assert "if not, rest." in hb.AFTER_ANSWER, "a format with rest as a full answer, not an instruction to act"


def test_once_a_web_verb_exists_the_line_names_it_and_stops_saying_no_internet(monkeypatch):
    from sage.gateway import toolset
    monkeypatch.setattr(toolset, "canonical_toolset", lambda: ["camera", "search", "peer_ask", "web_search", "rest"])
    line = hb.abilities_line()
    assert "search the web a few times an hour" in line and "no internet" not in line


def test_the_line_claims_only_what_is_measured_on_this_machine():
    """GPT on #334: canonical_toolset() has every fleet verb; a headless being must not be told it can see."""
    from sage.gateway import toolset as ts
    body = lambda verbs: {"inventory": {"verbs": verbs}}  # noqa: E731
    sprout = hb.abilities_line(ts.unavailable(body(["camera", "gaze", "speak", "pair_audio"]), "/tmp/wt", {}))
    assert "look through your eyes" in sprout and "speak aloud" in sprout
    headless = hb.abilities_line(ts.unavailable(body([]), "/tmp/wt", {}))
    assert "look through your eyes" not in headless and "speak aloud" not in headless
    no_speaker = hb.abilities_line(ts.unavailable(body(["camera", "gaze"]), "/tmp/wt", {}))
    assert "look through your eyes" in no_speaker and "speak aloud" not in no_speaker
    unmeasured = hb.abilities_line()
    assert "eyes" not in unmeasured and "speak" not in unmeasured, "not measured: not claimed"
    src = Path(hb.__file__).read_text()
    assert "abilities=abilities_line(_unavail)" in src, "the beat passes what it measured"
