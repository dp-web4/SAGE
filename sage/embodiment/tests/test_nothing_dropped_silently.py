"""Nothing the ear heard is dropped silently (dp, 2026-10-01: "voice transcription now cuts off what i said.
looks like an arbitrary length limit?"). It was not a length limit: whisper segments judged probably-silence or
low-confidence were left out without a trace, so "...adjustments to how you can" kept its head and lost its tail."""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.embodiment import listening  # noqa: E402
from sage.gateway import conversations as conv, room  # noqa: E402

ME = "sprout-being"
CLEAR = {"no_speech_prob": 0.05, "avg_logprob": -0.3}
UNCLEAR = {"no_speech_prob": 0.2, "avg_logprob": -1.4}
SILENT = {"no_speech_prob": 0.9, "avg_logprob": -0.5}


def seg(text, kind):
    return dict(kind, text=" " + text)


def test_an_unclear_tail_is_kept_as_dropped_and_marked():
    r = listening.judge_segments([seg("Reach out to your siblings who have been making", CLEAR),
                                  seg("some adjustments to how you can talk to them", UNCLEAR)], seconds=6.1)
    assert r["text"] == "Reach out to your siblings who have been making"
    assert r["unclear"] == "tail" and r["dropped"][0]["why"] == "unclear" and r["dropped"][0]["at"] == "tail"
    assert "how you can talk" in r["dropped"][0]["text"], "the left-out words are kept for measurement"


def test_a_silent_tail_is_recorded_but_never_marked_as_unclear_speech():
    r = listening.judge_segments([seg("Okay.", CLEAR), seg("Thank you.", SILENT)])
    assert r["text"] == "Okay." and "unclear" not in r and r["dropped"][0]["why"] == "silence"


def test_head_and_middle_places():
    assert listening.judge_segments([seg("mm", UNCLEAR), seg("hello there", CLEAR)])["unclear"] == "head"
    assert listening.judge_segments([seg("a", CLEAR), seg("b", UNCLEAR), seg("c", CLEAR)])["unclear"] == "middle"


def test_all_dropped_has_no_words_and_goes_to_the_unheard_log_not_the_room(monkeypatch):
    d = Path(tempfile.mkdtemp(prefix="ear-"))
    monkeypatch.setattr(listening, "UNHEARD_PATH", str(d / "unheard.jsonl"))
    t = listening.Transcriber(source="mic", heard_path=str(d / "heard.jsonl"))
    t.model, t._fp16 = object(), False
    monkeypatch.setattr(t, "transcribe", lambda audio: listening.judge_segments([seg("Thank you.", SILENT)]))
    t._handle(b"\x00\x00" * 1600)
    assert not (d / "heard.jsonl").exists(), "no words, no wake"
    line = json.loads((d / "unheard.jsonl").read_text().splitlines()[0])
    assert line["why"] == "no kept words" and line["dropped"][0]["at"] == "all"


def test_a_backlog_drop_is_counted_and_logged(monkeypatch):
    d = Path(tempfile.mkdtemp(prefix="ear-"))
    monkeypatch.setattr(listening, "UNHEARD_PATH", str(d / "unheard.jsonl"))
    t = listening.Transcriber(source="mic")
    for _ in range(8):
        assert t.submit(b"\x00\x00" * 160)
    assert t.submit(b"\x00\x00" * 160) is False and t.backlog_drops == 1
    assert json.loads((d / "unheard.jsonl").read_text().splitlines()[0])["why"] == "backlog"


def test_the_room_says_where_speech_was_unclear():
    h = Path(tempfile.mkdtemp(prefix="room-"))
    conv.create(h, "dp", title="dp", participants=["dp", ME], writable_by=["dp", ME])
    heard = [dict(listening.judge_segments([seg("Reach out to your siblings", CLEAR), seg("how you can", UNCLEAR)],
                                           now=time.time() - 5), source="bluez_input.x")]
    got = room.ingest_heard(h, ME, {}, heard=heard)
    assert got[0]["text"] == "Reach out to your siblings [the rest was unclear]"
    assert room.heard_text({"text": "fine"}) == "fine"


def test_the_pause_is_configurable_and_defaults_to_today(monkeypatch):
    import importlib
    monkeypatch.delenv("SAGE_LISTEN_PAUSE_S", raising=False)
    assert importlib.reload(listening).END_SILENCE_S == 0.8
    monkeypatch.setenv("SAGE_LISTEN_PAUSE_S", "1.2")
    assert importlib.reload(listening).END_SILENCE_S == 1.2
    monkeypatch.delenv("SAGE_LISTEN_PAUSE_S")
    importlib.reload(listening)
