"""When asked what changed, the answer turn sees what changed, from the being's own records
(2026-09-27: asked "did you notice any differences today?", sprout-being invented a warmer palette,
a larger font and "version 3.2.1"; nothing in view said what had changed)."""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import heartbeat as hb, conversations as conv  # noqa: E402

DAY = 86400


def _beat(t, verbs=None, clock=False, words=None):
    r = {"ts": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "t0": t}
    if verbs is not None:
        r["body"] = {"inventory": {"verbs": verbs},
                     "perception": ({"audio_ok": True, "audio_words": words} if words else {})}
    if clock:
        r["clock"] = {"local": "x"}
    return json.dumps(r)


def _home(tmp_path, beats):
    (tmp_path / "heartbeats.jsonl").write_text("\n".join(beats) + "\n")
    return tmp_path


def test_gains_are_measured_against_what_it_had_before_the_window(tmp_path):
    now = time.time()
    h = _home(tmp_path, [_beat(now - 10 * DAY, ["gaze", "say"]),
                         _beat(now - 3 * DAY, ["gaze", "say", "speak"], clock=True, words="idle")])
    conv.create(h, "room", title="room", participants=["b", "voice"], writable_by=["b", "voice"])
    line = hb.recent_changes(h, now=now)
    assert "you gained `speak`" in line and "local time" in line and "hear words" in line
    assert "'room' conversation opened" in line and "`say`" not in line and "`gaze`" not in line


def test_the_census_starting_inside_the_window_is_not_a_gain(tmp_path):
    now = time.time()
    h = _home(tmp_path, [_beat(now - 10 * DAY),                               # before any census
                         _beat(now - 5 * DAY, ["gaze", "say", "peer_ask"]),   # census begins
                         _beat(now - 2 * DAY, ["gaze", "say", "peer_ask", "speak"])])
    line = hb.recent_changes(h, now=now)
    assert "you gained `speak`" in line
    for old in ("`say`", "`gaze`", "`peer_ask`"):
        assert old not in line


def test_a_listener_that_is_unavailable_is_not_hearing(tmp_path):
    """cbp-claude on #249: audio_words is a status string; "unavailable: ..." is truthy."""
    now = time.time()
    h = _home(tmp_path, [_beat(now - 10 * DAY, ["say"]),
                         _beat(now - 2 * DAY, ["say"], words="unavailable: ImportError: whisper")])
    assert "hear" not in hb.recent_changes(h, now=now)


def test_losses_are_reported_and_state_toggled_abilities_are_neither(tmp_path):
    now = time.time()
    h = _home(tmp_path, [_beat(now - 10 * DAY, ["gaze", "speak", "say"]),
                         _beat(now - 2 * DAY, ["camera", "pair_audio", "say"])])
    line = hb.recent_changes(h, now=now)
    assert "`gaze` has not been offered" in line and "`speak` has not been offered" in line
    assert "camera" not in line and "pair_audio" not in line


def test_no_baseline_no_claim(tmp_path):
    now = time.time()
    h = _home(tmp_path, [_beat(now - 1 * DAY, ["speak"], clock=True)])
    assert hb.recent_changes(h, now=now) == ""


def test_the_reader_stops_at_the_window_not_the_file(tmp_path):
    now = time.time()
    old = [_beat(now - (40 + i / 100) * DAY, ["say"]) for i in range(3000)][::-1]
    h = _home(tmp_path, old + [_beat(now - 10 * DAY, ["say"]), _beat(now - 1 * DAY, ["say", "speak"])])
    got = hb._beats_since(h / "heartbeats.jsonl", now - 14 * DAY)
    assert len(got) == 2 and float(got[0]["t0"]) < float(got[1]["t0"])


def test_the_gate_asks_what_changed_not_what_exists():
    on = ["we have been updating your tools.  did you notice any differences today?", "anything new?",
          "what's changed for you since yesterday?", "we gave you some new abilities today. can you tell?",
          "have your abilities changed since last week?", "what's new with you?",
          "i installed something for you today — can you find it?", "any new tools showing up for you?"]
    off = ["what tools do you have?", "what do you notice in the room?",       # GPT's two, on #249
           "my beat never ends. and neither does yours", "how are you feeling?", "can you change the subject?",
           "which tools do you like best?", "notice how quiet it is", "what do you see out the window?",
           "tell me about the new story you're writing", "i updated my own laptop today"]
    assert [q for q in on if not hb.asks_about_change(q)] == []
    assert [q for q in off if hb.asks_about_change(q)] == []


def test_it_has_its_own_opt_in(tmp_path):
    assert hb.answer_changes_on(tmp_path) is False
    (tmp_path / "instance.json").write_text(json.dumps({"answer_turn": "json"}))
    assert hb.answer_changes_on(tmp_path) is False, "not implied by the JSON answer turn"
    (tmp_path / "instance.json").write_text(json.dumps({"answer_turn": "json", "answer_changes": True}))
    assert hb.answer_changes_on(tmp_path) is True


def test_the_line_sits_in_the_user_turn_above_the_question_and_is_recorded():
    from test_answer_turn_json import LLM, Client, TURN   # noqa: E402
    sel = hb.SelectedTurn("dp", TURN)
    llm = LLM(json.dumps({"answer": False, "message": ""}))
    res = hb.answer_turn_json(Client(), llm, sel, name="s", machine="s", member="s",
                              changes="Changes to you in the last days, from your own records: you gained `speak` (d).")
    user = llm.calls[0]["messages"][-1]["content"]
    assert user.startswith("Changes to you") and user.index("gained `speak`") < user.index(TURN["text"][:20])
    assert "Changes to you" not in llm.calls[0]["messages"][0]["content"]
    assert res.answer_form["with_changes"] is True


def test_the_heartbeat_gates_it_on_both():
    src = open(os.path.join(os.path.dirname(__file__), "..", "heartbeat.py")).read()
    assert "answer_changes_on(instance) and asks_about_change(selected.text)" in src
