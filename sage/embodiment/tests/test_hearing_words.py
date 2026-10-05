"""Hearing words: a reply channel, not a room recorder (dp, 2026-09-26: "is there a path for it to
hear when i reply in voice?").

Pinned here: nothing is transcribed outside the window speak() opens or while the being is speaking;
heard words carry no speaker identity; whisper's near-silence hallucinations are dropped; the beat
shows only words since the previous beat; a voice wakes a beat, queued behind a running one (#295).
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
    assert listening.window(path=p) == {"listening": False, "speaking": False, "always": False, "muted": None}, "absent = closed"
    listening.mark(path=p, listen_until=time.time() + 60, speaking_until=time.time() - 1)
    assert listening.window(path=p) == {"listening": True, "speaking": False, "always": False, "muted": None}
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
    # words, time, mic, and what was left out (2026-10-01: nothing dropped silently) — never who
    assert set(rec) <= {"ts", "text", "seconds", "source", "dropped", "unclear"}
    assert not {"speaker", "who", "from"} & set(rec)
    assert rec["dropped"][0]["why"] == "silence" and "unclear" not in rec, "a hallucination is not unclear speech"
    t.model = _FakeModel([{"text": " you", "no_speech_prob": 0.1, "avg_logprob": -1.6}])
    gone = t.transcribe(b"\0\0" * 1600)
    assert gone["text"] == "" and gone["dropped"][0]["at"] == "all", "no words: measured, never a heard line"


def test_a_missing_whisper_fails_open(monkeypatch):
    import builtins
    real = builtins.__import__
    monkeypatch.setattr(builtins, "__import__",
                        lambda n, *a, **k: (_ for _ in ()).throw(ImportError("no whisper")) if n == "whisper" else real(n, *a, **k))
    t = listening.Transcriber(source="mic")
    t._load()
    assert t.model is None and t.status.startswith("unavailable")


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
    assert during == [{"listening": False, "speaking": True, "always": False, "muted": None}], "muted while its own voice plays"
    after = listening.window(time.time() + 1)
    assert after == {"listening": True, "speaking": False, "always": False, "muted": None}
    assert not listening.window(time.time() + body.LISTEN_WINDOW_S + 1)["listening"]


def _hearing_presence(monkeypatch, tmp_path):
    """Presence reading a temp heard.jsonl, against a fake systemd (SAGE #295)."""
    from sage.embodiment import presence
    from sage.gateway import arousal
    from sage.gateway.tests.fake_systemd import FakeSystemd
    heard = tmp_path / "heard.jsonl"
    monkeypatch.setattr(presence, "HEARD", str(heard))
    sysd = FakeSystemd()
    monkeypatch.setattr(arousal, "_systemd", sysd)
    p = presence.Presence.__new__(presence.Presence)
    p.heard_seen, p.last_key, p._since_trim = 0, "", 0
    p._log = lambda ev: None
    return p, heard, sysd, arousal


def test_a_voice_wakes_a_beat_and_mid_beat_it_starts_the_next_one(monkeypatch, tmp_path):
    """Words heard are an event (#295): a beat now, or, while one runs, queued so the next beat
    starts the moment it ends. Not held for presence's next poll, and not spaced by a 45 s gap."""
    p, heard, sysd, arousal = _hearing_presence(monkeypatch, tmp_path)
    sysd.running = True
    heard.write_text(json.dumps({"ts": time.time(), "text": "hello Sprout"}) + "\n")
    [w] = p._check_heard(time.time())
    assert w["queued"] is True and sysd.starts == 0 and len(sysd.arms) == 1
    assert [e["descriptor"] for e in arousal.peek_pending()] == ['heard a voice: "hello Sprout"']
    sysd.beat_ends()
    assert sysd.starts == 1, "the next beat started as soon as the running one ended"
    assert p._check_heard(time.time() + 5) == [], "no new words, no new beat"
    sysd.beat_ends()
    with open(heard, "a") as f:
        f.write(json.dumps({"ts": time.time(), "text": "are you there"}) + "\n")
    [w] = p._check_heard(time.time() + 6)
    assert w["start_accepted"] is True and w["started"] is None and sysd.starts == 2, "no 45 s gap: new words, new beat"


def test_a_failed_beat_start_keeps_the_words_pending(monkeypatch, tmp_path):
    """GPT review of #220: a failed start once cleared the words. Now they are in the pending set
    before any start is tried, and the next beat, whatever starts it, claims them."""
    p, heard, sysd, arousal = _hearing_presence(monkeypatch, tmp_path)
    sysd.start_rc = 1
    heard.write_text(json.dumps({"ts": time.time(), "text": "hello Sprout"}) + "\n")
    [w] = p._check_heard(time.time())
    assert w["start_accepted"] is None and w["started"] is None
    [e] = arousal.claim_pending("the-next-beat")
    assert e["descriptor"] == 'heard a voice: "hello Sprout"'


def test_heard_log_preserves_unknown_and_does_not_claim_a_started_beat(monkeypatch, tmp_path, capsys):
    p, heard, sysd, _ = _hearing_presence(monkeypatch, tmp_path)
    logged = []
    p._log = logged.append
    for i, rc in enumerate((0, 1, -15)):
        sysd.running, sysd.start_rc = False, rc
        with heard.open("a") as stream:
            stream.write(json.dumps({"ts": i, "text": f"turn {i}"}) + "\n")
        p._check_heard(time.time())
        assert logged[-1]["started"] is None
        assert logged[-1]["start_accepted"] is (True if rc == 0 else None)
        assert logged[-1]["wake_evidence_version"] == 2
    text = capsys.readouterr().out
    assert "beat started" not in text and text.count("beat entry unconfirmed") == 3


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
        assert listening.window(time.time() + 1) == {"listening": False, "speaking": False, "always": False, "muted": None}, fails


def test_the_mic_that_heard_is_named_not_the_first_one_listed():
    """2026-09-26 13:57Z: dp's words came through the Airhug and the beat said "Through Built-in
    Audio Analog Stereo". Name the source the words came from; if that can't be told, "your mic"."""
    from sage.gateway import body
    inv = {"audio_sources": [{"name": "Built-in Audio Analog Stereo", "kind": "wired"},
                             {"name": "AIRHUG 01", "kind": "bluetooth"}]}
    assert body._heard_mic([{"source": "bluez_input.41_42.0"}], inv) == "AIRHUG 01"
    assert body._heard_mic([{"source": "alsa_input.analog"}], inv) == "your mic"
    assert body._heard_mic([{"source": "alsa_input.analog"}],
                           {"audio_sources": [{"name": "USB Mic", "kind": "wired"}]}) == "USB Mic"
