"""The ear's state is a sensed fact with its cause (dp, 2026-10-01): "it should be resilient to audio being
offline for any number of reasons - mute, bt disconnect, power off, or just me not being there. that's part
of the world and its uncertain nature." Could-not-listen is never presented as heard-nothing."""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.embodiment import listening  # noqa: E402
from sage.gateway import body  # noqa: E402


def _file(d=None):
    p = Path(tempfile.mkdtemp(prefix="ear-")) / "listen.json"
    p.write_text(json.dumps(d or {}))
    return str(p)


def test_mute_closes_even_an_always_open_ear_and_is_capped(monkeypatch):
    monkeypatch.setenv("SAGE_LISTEN", "always")
    p = _file()
    until = listening.mute(10_000, by="dp", path=p)
    assert until - time.time() <= listening.MUTE_MAX_MIN * 60 + 1, "a forgotten mute ends by itself"
    w = listening.window(path=p)
    assert w["listening"] is False and w["muted"]["by"] == "dp"
    listening.unmute(path=p)
    assert listening.window(path=p)["listening"] is True and listening.window(path=p)["muted"] is None


def test_the_first_known_cause_wins_most_physical_first():
    open_win = {"listening": True, "always": True, "muted": None}
    muted = {"listening": False, "always": True, "muted": {"until": time.time() + 600, "by": "dp"}}
    assert listening.ear_state(True, "ready", open_win, device_connected=False)[2] == "device"
    assert listening.ear_state(False, "ready", open_win)[2] == "stream"
    assert listening.ear_state(True, "unavailable: no whisper", open_win)[2] == "recognizer"
    h, why, key = listening.ear_state(True, "ready", muted)
    assert (h, key) == (False, "muted") and "muted by dp until" in why
    assert listening.ear_state(True, "ready", {"listening": False})[2] == "window"
    assert listening.ear_state(True, "ready", open_win)[:2] == (True, "always open")


def test_only_changes_are_logged_and_the_last_one_says_since_when():
    log = str(Path(tempfile.mkdtemp(prefix="ear-")) / "ear.jsonl")
    assert listening.note_ear(True, "always open", "always", path=log, now=100.0)
    assert listening.note_ear(True, "always open", "always", path=log, now=200.0) is None
    assert listening.note_ear(False, "the headset is not connected", "device", path=log, now=300.0)
    assert listening.ear_since(log)["ts"] == 300.0
    assert len(Path(log).read_text().splitlines()) == 2


def _cur(**audio):
    return {"perception": {"live": True, "audio_ok": True, "audio_words": "ready", **audio}}


def test_the_line_says_could_not_listen_with_the_cause_never_heard_nothing(monkeypatch):
    monkeypatch.setattr(listening, "EAR_LOG", str(Path(tempfile.mkdtemp()) / "ear.jsonl"))
    monkeypatch.setattr(body, "_heard_since", lambda ts: [{"ts": time.time() - 630, "text": "hi"}])
    line = body.ear_line(_cur(audio_hearing=False, audio_ear="muted by dp until 06:20"), {})
    assert "NOT hearing" in line and "muted by dp until 06:20" in line
    assert "not evidence that nobody spoke" in line and "10 min ago" in line
    line = body.ear_line(_cur(audio_hearing=True, audio_ear="always open"), {})
    assert line.startswith("- Your ear for words is open (always open)") and "not evidence" not in line


def test_a_disconnected_headset_overrides_and_offline_senses_are_unknown(monkeypatch):
    monkeypatch.setattr(body, "_heard_since", lambda ts: [])
    inv = {"audio_device": {"name": "AIRHUG 01", "connected": False}}
    line = body.ear_line(_cur(audio_hearing=True, audio_ear="always open"), inv)
    assert "NOT hearing" in line and "headset is not connected" in line and "heard no words yet" in line
    off = body.ear_line({"perception": {"live": False, "audio_hearing": True}}, {})
    assert "unknown this beat" in off and "not evidence" in off


def test_an_older_cortex_keeps_the_old_wording(monkeypatch):
    assert body.ear_line(_cur(), {}) == ""
    assert body.ear_known(_cur()) is False and body.ear_known(_cur(audio_hearing=False)) is True


def test_the_cli_mutes_and_unmutes(monkeypatch, capsys):
    p = _file()
    monkeypatch.setattr(listening, "LISTEN_PATH", p)
    monkeypatch.setattr(listening, "EAR_LOG", str(Path(p).with_name("ear.jsonl")))
    listening.main(["mute", "45", "--by", "dp"])
    assert listening.window(path=p)["muted"]["by"] == "dp"
    listening.main(["on"])
    assert listening.window(path=p)["muted"] is None


def test_since_belongs_to_the_cause_shown_not_just_the_state(monkeypatch):
    """GPT on #313: muted for an hour, then the headset drops: never "not connected since an hour ago"."""
    log = str(Path(tempfile.mkdtemp(prefix="ear-")) / "ear.jsonl")
    monkeypatch.setattr(listening, "EAR_LOG", log)
    monkeypatch.setattr(body, "_heard_since", lambda ts: [])
    hour_ago = time.time() - 3600
    listening.note_ear(False, "muted by dp until 07:00", "muted", path=log, now=hour_ago)
    stamp = time.strftime("%H:%M", time.localtime(hour_ago))
    muted = body.ear_line(_cur(audio_hearing=False, audio_ear="muted by dp until 07:00", audio_ear_key="muted"), {})
    assert f"since {stamp}" in muted, "same state, same cause: the logged time is right"
    inv = {"audio_device": {"name": "AIRHUG 01", "connected": False}}
    dropped = body.ear_line(_cur(audio_hearing=False, audio_ear="muted by dp until 07:00", audio_ear_key="muted"), inv)
    assert "headset is not connected" in dropped and f"since {stamp}" not in dropped and " since " not in dropped
    recog = body.ear_line(_cur(audio_hearing=False, audio_ear="word recognition is not available",
                               audio_ear_key="recognizer"), {})
    assert " since " not in recog, "a different cause than the one logged: no since"


def test_one_authoritative_line_about_the_ear_when_the_headset_is_gone():
    cur = _cur(audio_hearing=False, audio_ear="the headset is not connected", audio_ear_key="device")
    cur["perception"]["descriptor"] = "a still room"
    txt = body.render(dict(cur, inventory={"audio_device": {"name": "AIRHUG 01", "connected": False},
                                           "verbs": ["speak"]}), None)
    assert txt.count("cannot be heard") == 0 and "NOT hearing" in txt and "`speak` is not available" in txt
