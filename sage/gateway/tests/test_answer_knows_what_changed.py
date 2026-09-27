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


def _beat(t, verbs=None, clock=False, words=False):
    r = {"ts": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "t0": t}
    if verbs is not None:
        r["body"] = {"inventory": {"verbs": verbs}, "perception": ({"audio_words": "idle"} if words else {})}
    if clock:
        r["clock"] = {"local": "x"}
    return json.dumps(r)


def _home(tmp_path, beats):
    (tmp_path / "heartbeats.jsonl").write_text("\n".join(beats) + "\n")
    return tmp_path


def test_it_names_real_gains_and_nothing_that_was_already_there(tmp_path):
    now = time.time()
    h = _home(tmp_path, [
        _beat(now - 20 * DAY),                                    # before the census existed
        _beat(now - 12 * DAY, ["gaze", "say", "peer_ask"]),       # the census begins: baseline
        _beat(now - 3 * DAY, ["gaze", "say", "peer_ask", "speak"], clock=True, words=True),
    ])
    conv.create(h, "room", title="room", participants=["b", "voice"], writable_by=["b", "voice"])
    line = hb.recent_changes(h, now=now)
    assert "you gained `speak`" in line and "local time" in line and "hear words" in line
    assert "'room' conversation opened" in line
    for old in ("`say`", "`gaze`", "`peer_ask`"):
        assert old not in line, "the census starting is not the being gaining these"


def test_state_toggled_abilities_are_not_gains(tmp_path):
    now = time.time()
    h = _home(tmp_path, [_beat(now - 10 * DAY, ["gaze", "speak"]),
                         _beat(now - 2 * DAY, ["camera", "pair_audio", "say"])])
    line = hb.recent_changes(h, now=now)
    assert "camera" not in line and "pair_audio" not in line, "a cortex down / headset away is not a gain"


def test_no_baseline_no_claim(tmp_path):
    now = time.time()
    h = _home(tmp_path, [_beat(now - 1 * DAY, ["speak"], clock=True)])
    assert hb.recent_changes(h, now=now) == "", "a record that does not reach before the window claims nothing"


def test_the_gate():
    for q in ("did you notice any differences today?", "anything new?", "we updated your tools",
              "what changed?", "have you noticed an improvement"):
        assert hb.asks_about_change(q), q
    for q in ("my beat never ends. and neither does yours", "how are you feeling?", "good morning"):
        assert not hb.asks_about_change(q), q


def test_the_line_sits_in_the_user_turn_above_the_question_and_is_recorded():
    from test_answer_turn_json import LLM, Client, TURN   # noqa: E402
    sel = hb.SelectedTurn("dp", TURN)
    llm = LLM(json.dumps({"answer": False, "message": ""}))
    res = hb.answer_turn_json(Client(), llm, sel, name="s", machine="s", member="s",
                              changes="Changes to you in the last days, from your own records: you gained `speak` (d).")
    user = llm.calls[0]["messages"][-1]["content"]
    assert user.startswith("Changes to you") and user.index("gained `speak`") < user.index(TURN["text"][:20])
    assert "Changes to you" not in llm.calls[0]["messages"][0]["content"], "not the system prompt (0/6 there)"
    assert res.answer_form["with_changes"] is True


def test_the_heartbeat_gates_it():
    src = open(os.path.join(os.path.dirname(__file__), "..", "heartbeat.py")).read()
    assert "recent_changes(instance) if asks_about_change(selected.text)" in src
