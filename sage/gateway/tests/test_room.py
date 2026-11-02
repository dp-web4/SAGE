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
    """Shown as something the mic picked up, with no speaker (dp 2026-10-19)."""
    h = _home()
    room.ingest_heard(h, ME, INV, heard=[_heard(time.time() - 10, "Can you hear me?")])
    shown = conv.drain_new_for(h, ME, mark=False)
    assert "Can you hear me?" in shown and "**the mic picked up**" in shown
    assert "**voice**" not in shown
    assert 'reply with say to="room"' in shown


def test_the_beat_shows_heard_lines_as_picked_up_and_owed_nothing():
    h = _home()
    room.ensure(h, ME)
    room.ingest_heard(h, ME, INV, heard=[_heard(time.time() - 30, "Two million units, your grace."),
                                        _heard(time.time() - 20, "I think that's what we're doing with this car.")])
    shown = conv.render_for_being(h, ME)                      # as the beat renders: new lines are pending
    room_part = shown.split("### the room")[1]
    assert "**the mic picked up**" in room_part and "**voice**" not in room_part
    assert "The mic picked up 2 line(s)" in room_part and "Most room sound is not addressed to you" in room_part
    assert "unanswered" not in room_part, "picked-up sound is not a turn owed an answer"
    again = conv.render_for_being(h, ME).split("### the room")[1]   # seen now, still the last thing here
    assert "The last thing here is something the mic picked up" in again
    assert "still yours to answer" not in again


def test_music_the_transcriber_marked_is_said_beside_the_lines_near_it():
    """Room 314-315 (2026-10-19): `[Music]`, then a lyric 5 s later the being took up as its own opening line."""
    h = _home()
    room.ensure(h, ME)
    t = time.time() - 300
    room.ingest_heard(h, ME, INV, heard=[_heard(t, "It's between Bar and Gond."),
                                        _heard(t + 21, "[Music]"),
                                        _heard(t + 26, "No single voice could hold the need."),
                                        _heard(t + 200, "Can you hear me?")])
    def line_with(shown, words):
        return next(ln for ln in shown.splitlines() if words in ln)

    for shown in (conv.drain_new_for(h, ME, mark=False), conv.render_for_being(h, ME).split("### the room")[1]):
        assert "the transcriber marked music here" in line_with(shown, "[Music]")
        lyric = line_with(shown, "No single voice")
        assert "music was playing within a minute" in lyric
        assert "song lyrics, or someone speaking over the music" in lyric, "a person over the music stays possible"
        assert "music was playing within a minute" in line_with(shown, "Bar and Gond"), "before a mark counts too"
        assert "music" not in line_with(shown, "Can you hear me?"), "minutes from any mark: no note"


def test_music_marks_the_transcriber_writes_are_all_recognised():
    for text in ("[Music]", "[MUSIC PLAYING]", "(upbeat music)", "♪ Where you are ♪"):
        assert conv.MUSIC_MARK.search(text), text
    for text in ("[water splashing]", "[BLANK_AUDIO]", "Musical chairs are fun", "(knocking)"):
        assert not conv.MUSIC_MARK.search(text), text


def test_an_existing_room_with_the_old_summary_is_brought_up_to_date():
    """NOVA on #485: create() keeps existing metadata, so an upgraded room kept the old speaker guidance."""
    import json
    h = _home()
    conv.create(h, "room", title="the room: spoken aloud and heard", participants=[ME, "voice"],
                writable_by=[ME, "voice"],
                summary="This machine sits in dp's room, so the voice you hear is usually dp's.")
    meta = conv.get_meta(h, "room")
    meta["notify"] = {"someone": "x"}
    meta["custom_field"] = 7
    conv._write_meta(h, "room", meta)
    room.ingest_heard(h, ME, INV, heard=[_heard(time.time() - 10, "hello there")])
    before_turns = conv.recent(h, "room")
    before = conv.get_meta(h, "room")

    room.ensure(h, ME)
    after = conv.get_meta(h, "room")
    assert after["summary"] == room.SUMMARY and "usually dp" not in after["summary"]
    assert {k: v for k, v in after.items() if k != "summary"} == {k: v for k, v in before.items() if k != "summary"}
    assert conv.recent(h, "room") == before_turns, "turn history unchanged"

    meta_file = conv.conv_dir(h) / "room.meta.json"
    stamp = meta_file.stat().st_mtime_ns
    room.ensure(h, ME)
    assert meta_file.stat().st_mtime_ns == stamp, "an up-to-date room is not rewritten"
    assert json.loads(meta_file.read_text()) == after


def test_the_room_says_what_the_mic_is():
    h = _home()
    room.ensure(h, ME)
    s = conv.get_meta(h, "room")["summary"]
    assert "TV, music and noise" in s and "Most of what the mic picks up is not addressed to you" in s
    assert "usually dp" not in s


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
    assert ingest < src.index("pending_selection(instance, args.member")
    assert ingest < src.index("body_reading=_body_cur) + _scope_tail")


def test_append_lands_then_the_watermark_write_fails_and_nothing_is_duplicated(monkeypatch):
    """GPT on #228, failure 1: the turn is durable, the watermark write crashes; the next beat
    must find the turn by its id, not append it again."""
    h = _home()
    ev = [_heard(time.time() - 30, "Can you hear me?")]
    real_write = Path.write_text
    def boom(self, *a, **k):
        if self.name == room.WATERMARK:
            raise OSError("disk full")
        return real_write(self, *a, **k)
    monkeypatch.setattr(Path, "write_text", boom)
    assert len(room.ingest_heard(h, ME, INV, heard=ev)) == 1
    monkeypatch.setattr(Path, "write_text", real_write)
    assert room.ingest_heard(h, ME, INV, heard=ev) == []
    assert [t["text"] for t in conv.recent(h, "room")] == ["Can you hear me?"]


def test_same_timestamp_siblings_both_land_even_after_a_crash_between_them():
    """GPT on #228, failure 2: two heard records share a timestamp; the process dies after the
    first. The second must still be carried in on restart, and the first not repeated."""
    h = _home()
    ts = time.time() - 30
    a, b = _heard(ts, "Can you hear me?"), _heard(ts, "It's dp.")
    room.ingest_heard(h, ME, INV, heard=[a])              # crash here: b never processed
    assert (conv.conv_dir(h) / room.WATERMARK).read_text() == str(ts), "watermark sits AT ts"
    got = room.ingest_heard(h, ME, INV, heard=[a, b])
    assert [t["text"] for t in got] == ["It's dp."]
    assert [t["text"] for t in conv.recent(h, "room")] == ["Can you hear me?", "It's dp."]


def test_the_heard_id_is_carried_on_the_turn_and_distinguishes_source_and_words():
    ts = 1790430950.39
    x = room.heard_id(_heard(ts, "hello"))
    assert x == room.heard_id(_heard(ts, "hello"))
    assert x != room.heard_id(_heard(ts, "hello there"))
    assert x != room.heard_id({**_heard(ts, "hello"), "source": "alsa_input.x"})
    h = _home()
    room.ingest_heard(h, ME, INV, heard=[_heard(time.time() - 5, "hello")])
    t = conv.recent(h, "room")[-1]
    assert t["heard_id"] and t["mic"] == "AIRHUG 01"


def test_extra_can_never_supply_a_field_the_store_owns():
    """GPT on #228 (non-blocking): setdefault protected keys that were present, but an absent
    witness or beat could be supplied by `extra`. Every store-owned key is refused, and a
    refused append writes nothing."""
    import pytest
    h = _home()
    room.ensure(h, ME)
    for k in sorted(conv.RESERVED_TURN_KEYS):
        with pytest.raises(ValueError):
            conv.append(h, "room", speaker=ME, text="hi", extra={k: "forged"})
    assert conv.count(h, "room") == 0
    t = conv.append(h, "room", speaker=ME, text="hi", extra={"heard_id": "x"})
    assert t["heard_id"] == "x" and "witness" not in t and "beat" not in t
    # legion on #232: a refused append must not spend a seq in the witness, or this first real
    # turn would be seq 8 and the witness would carry a truncation scar per refusal.
    assert t["seq"] == 1
    w = json.loads(conv.witness_path(h, "room").read_text())
    assert w["high_water_seq"] == 1 and "truncations" not in w
