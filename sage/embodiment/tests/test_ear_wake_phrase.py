"""Wake mode: the ear hears everything, but words reach the being only after its name (dp, 2026-10-08).

Measured that evening: a news reel on another machine ("Two million units, your grace...") became room turns and
the being answered it as if dp had spoken. With SAGE_LISTEN=wake, "hey Sprout" opens an engaged window
(KEEPALIVE_S, 30-45 s), each addressed utterance extends it, "bye Sprout" closes it, and speech that is not
addressed is recorded only as the fact of speech nearby -- never its words."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.embodiment import listening as L  # noqa: E402


@pytest.fixture
def ear(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "LISTEN_PATH", str(tmp_path / "listen.json"))
    monkeypatch.setattr(L, "UNHEARD_PATH", str(tmp_path / "unheard.jsonl"))
    monkeypatch.delenv("SAGE_LISTEN", raising=False)
    chimes = []
    monkeypatch.setattr(L, "chime", lambda: chimes.append(1))
    L.mark(mode="wake", keepalive_s=40)
    t = L.Transcriber(source="mic", heard_path=str(tmp_path / "heard.jsonl"))
    t.chimes, t.tmp = chimes, tmp_path
    return t


def _rec(text, ts=1000.0):
    return {"ts": ts, "text": text, "seconds": 2.0, "source": "mic"}


def _lines(p):
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


@pytest.mark.parametrize("text,named,rest", [
    ("Hey Sprout, what do you see?", True, "what do you see?"),
    ("hi spout how are you", True, "how are you"),
    ("Okay Sprout.", True, ""),
    ("Sprout, look at the door", True, "look at the door"),
    ("Two million units, your grace. You are making a mistake.", False, ""),
    ("the sprout grows on the windowsill", False, ""),
])
def test_wake_match(text, named, rest):
    assert L.wake_match(text) == (named, rest)


def test_unaddressed_speech_is_the_fact_not_the_words(ear):
    assert ear._route(_rec("Two million units, your grace."), {}, now=1000.0) == "overheard"
    assert _lines(ear.heard_path) == [], "no room turn, nothing for the being to answer"
    un = _lines(str(ear.tmp / "unheard.jsonl"))[-1]
    assert un["why"] == "not addressed" and "text" not in un and "dropped" not in un, "never the words"
    assert L.window(1000.0)["last_overheard"] == 1000.0


def test_the_name_opens_the_window_with_a_chime_and_keeps_only_the_words_after_it(ear):
    assert ear._route(_rec("Hey Sprout, what do you see?"), {}, now=1000.0) == "woke"
    assert ear.chimes == [1]
    assert _lines(ear.heard_path)[-1]["text"] == "what do you see?"
    w = L.window(1039.0)
    assert w["engaged"] and not L.window(1041.0)["engaged"], "40 s keep-alive"


def test_the_name_alone_opens_the_window_and_writes_no_turn(ear):
    assert ear._route(_rec("Hey Sprout."), {}, now=1000.0) == "woke"
    assert _lines(ear.heard_path) == [] and L.window(1010.0)["engaged"]


def test_engaged_speech_is_heard_and_keeps_the_window_alive_until_goodbye(ear):
    ear._route(_rec("Hey Sprout"), {}, now=1000.0)
    assert ear._route(_rec("what is on the table?"), {}, now=1030.0) == "heard"
    assert L.window(1065.0)["engaged"], "extended from 1030 by 40 s"
    assert ear._route(_rec("thanks, bye Sprout"), {}, now=1050.0) == "heard"
    assert not L.window(1051.0)["engaged"], "goodbye closes it"
    assert [h["text"] for h in _lines(ear.heard_path)] == ["what is on the table?", "thanks, bye Sprout"]


def test_outside_wake_mode_kept_words_are_heard_as_before(ear):
    L.mark(mode="")
    assert ear._route(_rec("Two million units"), {}, now=1000.0) == "heard"
    assert _lines(ear.heard_path)[-1]["text"] == "Two million units" and ear.chimes == []


def test_the_ear_tells_the_being_what_it_is_listening_for(ear):
    w = L.window(1000.0)
    assert w["listening"], "in wake mode the segmenter runs while idle, or the name is never heard"
    assert L.ear_state(True, "ready", w) == (True, L.ear_state(True, "ready", w)[1], "wake")
    assert "your name" in L.ear_state(True, "ready", w)[1]
    L.engage(now=1000.0)
    assert L.ear_state(True, "ready", L.window(1001.0))[2] == "engaged"


def test_the_beings_reply_extends_by_the_keepalive_in_wake_mode():
    src = open(os.path.join(os.path.dirname(L.__file__), "..", "gateway", "body.py")).read()
    assert '_keep = _w.get("keepalive_s") if _w.get("wake") else LISTEN_WINDOW_S' in src
