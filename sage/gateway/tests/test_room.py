"""The room: voice as a conversation (dp, 2026-09-26: "should we have a separate chat transcript for
voice chat? or include it in the text chat with voice markers?" -> its own conversation).

Pinned: heard words become `voice` turns stamped when heard, once each; they are never written into
dp's channel; a voice that asked something is a turn waiting on the being, so the answer machinery
applies; say to room is spoken (and guarded like any say); speak is the being's turn in the room;
the clock says it in spoken words."""
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import body, conversations as conv, room  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402

ME = "sprout-being"
INV = {"audio_sources": [{"name": "Built-in Audio Analog Stereo", "kind": "wired"},
                         {"name": "AIRHUG 01", "kind": "bluetooth"}]}


def _home():
    h = Path(tempfile.mkdtemp(prefix="room-"))
    conv.create(h, "dp", title="dp", participants=["dp", ME], writable_by=["dp", ME])
    return h


def _heard(ts, text):
    return {"ts": ts, "text": text, "seconds": 1.9, "source": "bluez_input.41_42.0"}


def test_heard_words_become_voice_turns_once_stamped_when_heard():
    h = _home()
    t0 = time.time() - 120
    got = room.ingest_heard(h, ME, INV, heard=[_heard(t0, "Can you hear me?")])
    assert len(got) == 1 and got[0]["mic"] == "AIRHUG 01"
    turns = conv.recent(h, "room")
    assert turns[-1]["from"] == "voice" and turns[-1]["via"] == "voice"
    assert turns[-1]["ts"] == datetime.fromtimestamp(t0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert room.ingest_heard(h, ME, INV, heard=[_heard(t0, "Can you hear me?")]) == [], "once"
    assert conv.count(h, "dp") == 0, "a voice is never written into dp's channel"


def test_a_first_run_does_not_replay_the_whole_heard_log():
    h = _home()
    assert room.ingest_heard(h, ME, INV, heard=[_heard(time.time() - 5 * 3600, "old")]) == []


def test_a_voice_turn_says_who_spoke_is_not_known():
    h = _home()
    room.ingest_heard(h, ME, INV, heard=[_heard(time.time() - 10, "Can you hear me?")])
    shown = conv.drain_new_for(h, ME, mark=False)
    assert "Can you hear me?" in shown and conv.VOICE_TAG.strip() in shown
    assert 'reply with say to="room"' in shown


def test_a_voice_that_asked_is_a_turn_waiting_on_the_being():
    from sage.gateway.heartbeat import pending_selection
    h = _home()
    room.ingest_heard(h, ME, INV, heard=[_heard(time.time() - 10, "Can you hear me?")])
    assert conv.unanswered(h, "room", ME), "the answer machinery sees it"
    sel = pending_selection(h, ME)[4]
    assert sel is not None and sel.cid == "room"


def _dispatcher(h, monkeypatch, live=True):
    from sage.gateway import hestia_dispatch as hd
    played, calls = [], []
    d = hd.HestiaF1aDispatcher.__new__(hd.HestiaF1aDispatcher)
    d.memory_root, d.member, d.host_session_id = str(h), ME, None
    d._call = lambda name, args: (calls.append((name, args)) or {"actionId": "a1"})
    d._local = type("L", (), {"_witness": staticmethod(lambda e: "w-1")})()
    monkeypatch.setattr(body, "speak_provider",
                        lambda audio=None: {"live": live, "why": "" if live else "no audio output is connected"})
    monkeypatch.setattr(body, "speak", lambda text, timeout=60: (played.append(text) or {"chars": len(text), "seconds": 1.0}))
    monkeypatch.setattr(body, "speaker_name", lambda inv=None: "AIRHUG 01")
    return d, played, calls


def test_say_to_room_is_spoken_and_is_the_beings_turn(monkeypatch):
    h = _home()
    room.ingest_heard(h, ME, INV, heard=[_heard(time.time() - 10, "Can you hear me?")])
    d, played, _ = _dispatcher(h, monkeypatch)
    env = d._do_say(BeingIntent("say", {"to": "room", "text": "Yes, I can hear you."}))
    assert env.ok and played == ["Yes, I can hear you."]
    last = conv.recent(h, "room")[-1]
    assert last["from"] == ME and last["via"] == "speak" and last["text"] == "Yes, I can hear you."
    assert not conv.unanswered(h, "room", ME), "answered aloud is answered"


def test_say_to_room_keeps_the_say_guards_before_any_sound(monkeypatch):
    h = _home()
    room.ingest_heard(h, ME, INV, heard=[_heard(time.time() - 10, "Can you hear me?")])
    d, played, calls = _dispatcher(h, monkeypatch)
    for text in ("Can you hear me?", "[Your answer to the voice]", "..."):
        env = d._do_say(BeingIntent("say", {"to": "room", "text": text}))
        assert not env.ok, text
    assert played == [] and calls == [], "echo, placeholder and punctuation never reach the speaker"


def test_say_to_room_on_a_body_that_cannot_speak_says_so(monkeypatch):
    h = _home()
    room.ensure(h, ME)
    d, played, calls = _dispatcher(h, monkeypatch, live=False)
    env = d._do_say(BeingIntent("say", {"to": "room", "text": "hello"}))
    assert not env.ok and "cannot speak aloud" in env.error and played == [] and calls == []


def test_speak_is_recorded_in_the_room(monkeypatch):
    h = _home()
    d, played, _ = _dispatcher(h, monkeypatch)
    env = d._do_speak(BeingIntent("speak", {"text": "Hi! Is anyone there?"}))
    assert env.ok and "your turn in the room conversation" in env.result
    assert conv.recent(h, "room")[-1]["via"] == "speak"


def test_the_clock_says_the_room_in_spoken_words():
    from sage.gateway.heartbeat import clock_sense, render_clock
    h = _home()
    room.ingest_heard(h, ME, INV, heard=[_heard(time.time() - 125, "Can you hear me?")])
    out = render_clock(clock_sense(datetime.now(timezone.utc), h, ME))
    assert "a voice in the room last spoke to you 2 min ago" in out
    assert "voice last wrote" not in out


def test_the_heartbeat_carries_heard_words_in_before_it_builds_the_state():
    src = open(os.path.join(os.path.dirname(__file__), "..", "heartbeat.py")).read()
    ingest = src.index("_room.ingest_heard(instance")
    assert ingest < src.index("pending_selection(instance, args.member)")
    assert ingest < src.index("body_reading=_body_cur) + _scope_tail")
