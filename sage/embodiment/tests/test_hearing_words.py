"""Hearing words: a reply channel, not a room recorder (dp, 2026-09-26: "is there a path for it to
hear when i reply in voice?").

Pinned here: nothing is transcribed outside the window speak() opens or while the being is speaking;
heard words carry no speaker identity; whisper's near-silence hallucinations are dropped; the beat
shows only words since the previous beat; a voice wakes a beat, held while one is already running.
"""
import json
import os
import struct
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.embodiment import listening  # noqa: E402

W = 1600 * 2   # one 0.1 s window of s16le


def _chunk(v=0):
    return struct.pack("<1600h", *([v] * 1600))


def _feed(seg, pattern):
    """pattern: list of (level, n_windows). Returns utterances produced."""
    out = []
    for level, n in pattern:
        for _ in range(n):
            u = seg.feed(_chunk(), level, 0.01)
            if u:
                out.append(u)
    return out


def test_a_spoken_phrase_is_cut_out_with_its_first_syllable():
    seg = listening.Segmenter()
    utts = _feed(seg, [(0.0, 10), (0.2, 12), (0.0, 9)])
    assert len(utts) == 1
    assert len(utts[0]) == (3 + 12 + 8) * W, "pre-roll (0.3 s) + speech + the 0.8 s that ended it"


def test_a_knock_is_not_words_and_silence_is_nothing():
    seg = listening.Segmenter()
    assert _feed(seg, [(0.0, 50)]) == []
    assert _feed(seg, [(0.3, 2), (0.0, 10)]) == [], "0.2 s voiced is below MIN_VOICED_S"


def test_a_long_speech_is_cut_at_the_cap_not_buffered_forever():
    seg = listening.Segmenter()
    utts = _feed(seg, [(0.2, 250)])
    assert len(utts) == 1 and len(utts[0]) == 200 * W


def test_the_window_opens_and_closes_by_time(tmp_path):
    p = str(tmp_path / "listen.json")
    assert listening.window(path=p) == {"listening": False, "speaking": False}, "absent = closed"
    listening.mark(path=p, listen_until=time.time() + 60, speaking_until=time.time() - 1)
    assert listening.window(path=p) == {"listening": True, "speaking": False}
    listening.mark(path=p, speaking_until=time.time() + 5)
    assert listening.window(path=p)["speaking"] and listening.window(path=p)["listening"]
    assert not listening.window(time.time() + 120, path=p)["listening"]


def _hearing(monkeypatch, tmp_path, **win):
    from sage.embodiment import audio
    monkeypatch.setattr(listening, "LISTEN_PATH", str(tmp_path / "listen.json"))
    if win:
        listening.mark(**win)
    h = audio.Hearing()
    got = []
    h.transcriber.submit = lambda u: got.append(u) or True
    return h, got


def _speak_at(h, level=0.2):
    for lv, n in [(level, 12), (0.0, 9)]:
        for _ in range(n):
            h._listen(_chunk(), lv, 0.01)


def test_outside_a_window_the_room_is_not_transcribed(monkeypatch, tmp_path):
    h, got = _hearing(monkeypatch, tmp_path)
    _speak_at(h)
    assert got == []


def test_inside_a_window_words_go_to_the_transcriber(monkeypatch, tmp_path):
    h, got = _hearing(monkeypatch, tmp_path, listen_until=time.time() + 60, speaking_until=0)
    _speak_at(h)
    assert len(got) == 1


def test_its_own_voice_is_never_handed_back(monkeypatch, tmp_path):
    h, got = _hearing(monkeypatch, tmp_path, listen_until=time.time() + 60,
                      speaking_until=time.time() + 60)
    _speak_at(h)
    assert got == [], "while speak() plays, the ear drops audio"


def test_the_ear_state_reports_the_listener():
    from sage.embodiment import audio
    st = audio.Hearing().state()
    assert st["words"] == "idle" and st["listening"] is False


class _FakeModel:
    def __init__(self, segs):
        self.segs = segs

    def transcribe(self, a, **k):
        return {"segments": self.segs}


def test_whisper_near_silence_hallucinations_are_dropped_and_no_speaker_is_recorded():
    t = listening.Transcriber(source="mic")
    t._fp16 = False
    t.model = _FakeModel([{"text": " Thank you.", "no_speech_prob": 0.9, "avg_logprob": -0.3},
                          {"text": " Hi Sprout, it's good to hear you.", "no_speech_prob": 0.05,
                           "avg_logprob": -0.2}])
    rec = t.transcribe(b"\0\0" * 16000)
    assert rec["text"] == "Hi Sprout, it's good to hear you."
    assert set(rec) == {"ts", "text", "seconds", "source"}, "words, time, mic — never who"
    t.model = _FakeModel([{"text": " you", "no_speech_prob": 0.1, "avg_logprob": -1.6}])
    assert t.transcribe(b"\0\0" * 1600) is None


def test_a_missing_whisper_fails_open(monkeypatch):
    import builtins
    real = builtins.__import__
    monkeypatch.setattr(builtins, "__import__",
                        lambda n, *a, **k: (_ for _ in ()).throw(ImportError("no whisper")) if n == "whisper" else real(n, *a, **k))
    t = listening.Transcriber(source="mic")
    t._load()
    assert t.model is None and t.status.startswith("unavailable")


def test_the_beat_shows_only_words_since_the_previous_beat_and_names_no_one(monkeypatch, tmp_path):
    from sage.gateway import body
    now = time.time()
    heard = [{"ts": now - 600, "text": "old words", "source": "mic"},
             {"ts": now - 30, "text": "I heard you, Sprout.", "source": "mic"}]
    cur = {"heard": heard, "heard_until": now - 30}
    prev = {"heard_until": now - 600}
    lines = body.render_heard(cur, prev, {"audio_sources": [{"name": "AIRHUG 01"}]})
    text = "\n".join(lines)
    assert "I heard you, Sprout." in text and "old words" not in text
    assert "Through AIRHUG 01 you heard a voice in the room" in text
    assert "dp" not in text, "a voice is not authenticated; the beat never names a speaker"
    assert body.render_heard(cur, {"heard_until": now}, {}) == []


def test_speak_opens_the_window_after_the_sound_and_mutes_during_it(monkeypatch, tmp_path):
    from sage.gateway import body
    import subprocess
    monkeypatch.setattr(listening, "LISTEN_PATH", str(tmp_path / "listen.json"))
    during = []
    def run(argv, **k):
        if argv[0] == "pw-play":
            during.append(listening.window())
    monkeypatch.setattr(subprocess, "run", run)
    body.speak("hello")
    assert during == [{"listening": False, "speaking": True}], "muted while its own voice plays"
    after = listening.window(time.time() + 1)
    assert after == {"listening": True, "speaking": False}
    assert not listening.window(time.time() + body.LISTEN_WINDOW_S + 1)["listening"]


def test_a_voice_wakes_a_beat_held_while_one_is_running(monkeypatch, tmp_path):
    from sage.embodiment import presence
    from sage.gateway import being_join
    heard = tmp_path / "heard.jsonl"
    monkeypatch.setattr(presence, "HEARD", str(heard))
    monkeypatch.setattr(being_join, "write_wake_marker", lambda d, s: None)
    started = []
    import subprocess
    monkeypatch.setattr(subprocess, "run",
                        lambda argv, **k: started.append(argv) or type("R", (), {"returncode": 0, "stderr": ""})())
    p = presence.Presence.__new__(presence.Presence)
    p.heard_seen, p.heard_pending, p.last_heard_wake = 0, None, 0.0
    p._log = lambda ev: None
    heard.write_text(json.dumps({"ts": time.time(), "text": "hello Sprout"}) + "\n")
    running = [True]
    monkeypatch.setattr(presence.Presence, "_beat_running", staticmethod(lambda: running[0]))
    p._check_heard(time.time())
    assert started == [] and p.heard_pending, "held, not dropped, while a beat runs"
    running[0] = False
    p._check_heard(time.time())
    assert started and started[0][-1] == "sage-heartbeat.service" and p.heard_pending is None
    p._check_heard(time.time() + 5)
    assert len(started) == 1, "no new words, no new beat"


def test_a_failed_playback_or_synthesis_opens_no_window(monkeypatch, tmp_path):
    """GPT review of #220: the window used to open from a `finally`, so a sound that never
    played still started a 2-minute transcription. Nothing said, nothing opened."""
    from sage.gateway import body
    import subprocess
    import pytest
    monkeypatch.setattr(listening, "LISTEN_PATH", str(tmp_path / "listen.json"))
    for fails in ("pw-play", "espeak-ng"):
        def run(argv, **k):
            if argv[0] == fails:
                raise subprocess.CalledProcessError(1, argv)
        monkeypatch.setattr(subprocess, "run", run)
        with pytest.raises(subprocess.CalledProcessError):
            body.speak("hello")
        assert listening.window(time.time() + 1) == {"listening": False, "speaking": False}, fails


def test_a_failed_beat_start_keeps_the_words_and_retries(monkeypatch, tmp_path):
    """GPT review of #220: a failed `systemctl start` cleared the pending words, so the voice
    was never delivered. They stay pending until a beat actually starts."""
    from sage.embodiment import presence
    from sage.gateway import being_join
    heard = tmp_path / "heard.jsonl"
    monkeypatch.setattr(presence, "HEARD", str(heard))
    monkeypatch.setattr(being_join, "write_wake_marker", lambda d, s: None)
    monkeypatch.setattr(presence.Presence, "_beat_running", staticmethod(lambda: False))
    rc = [1]
    started = []
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda argv, **k: started.append(argv)
                        or type("R", (), {"returncode": rc[0], "stderr": "Failed to start"})())
    p = presence.Presence.__new__(presence.Presence)
    p.heard_seen, p.heard_pending, p.last_heard_wake = 0, None, 0.0
    p._log = lambda ev: None
    heard.write_text(json.dumps({"ts": time.time(), "text": "hello Sprout"}) + "\n")
    t = time.time()
    p._check_heard(t)
    assert len(started) == 1 and p.heard_pending, "failed start: words kept"
    p._check_heard(t + 5)
    assert len(started) == 1, "retry waits out the gap"
    rc[0] = 0
    p._check_heard(t + presence.HEARD_BEAT_GAP_S + 1)
    assert len(started) == 2 and p.heard_pending is None, "retried and delivered"
