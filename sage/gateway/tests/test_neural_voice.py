"""A neural voice for speak, opt-in per body, falling back to espeak-ng (dp, 2026-10-01: espeak-ng is "too
harshly metallic/'robotic'"; he chose en_US-hfc_female-medium)."""
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import body  # noqa: E402
from sage.embodiment.tts_piper import sentences  # noqa: E402


def _voice_dir():
    d = Path(tempfile.mkdtemp(prefix="voices-"))
    (d / "en_US-hfc_female-medium.onnx").write_bytes(b"x")
    return d


def test_no_voice_named_means_espeak(monkeypatch):
    monkeypatch.setattr(body, "SPEAK_VOICE", "")
    assert body.neural_voice() is None


def test_a_named_voice_resolves_only_when_the_model_and_interpreter_exist(monkeypatch):
    d = _voice_dir()
    monkeypatch.setattr(body, "PIPER_VOICES", str(d))
    monkeypatch.setattr(body, "SPEAK_VOICE", "en_US-hfc_female-medium")
    monkeypatch.setattr(body, "PIPER_PYTHON", sys.executable)
    v = body.neural_voice()
    assert v["name"] == "en_US-hfc_female-medium" and v["model"].endswith(".onnx")
    monkeypatch.setattr(body, "SPEAK_VOICE", "en_US-missing-medium")
    assert body.neural_voice() is None
    monkeypatch.setattr(body, "SPEAK_VOICE", "en_US-hfc_female-medium")
    monkeypatch.setattr(body, "PIPER_PYTHON", "/nonexistent/python")
    assert body.neural_voice() is None


def test_sentences_split_at_sentence_ends_and_never_empty():
    assert sentences("Hi there.  I'm here! Are you?   ") == ["Hi there.", "I'm here!", "Are you?"]
    assert sentences("no end") == ["no end"] and sentences("   ") == []


def _fake_run(neural_ok, calls):
    def run(argv, **k):
        calls.append(argv[:3] if argv[0] != "pw-play" else ["pw-play"])
        if "sage.embodiment.tts_piper" in argv:
            return SimpleNamespace(returncode=0 if neural_ok else 1, stderr=b"piper: model failed to load")
        if argv[0] == "espeak-ng":
            Path(argv[argv.index("-w") + 1]).write_bytes(b"RIFF")
        return SimpleNamespace(returncode=0, stderr=b"")
    return run


def test_speak_uses_the_neural_voice_and_falls_back_to_espeak(monkeypatch):
    import subprocess
    monkeypatch.setattr(body, "neural_voice", lambda: {"name": "en_US-hfc_female-medium", "model": "m.onnx",
                                                       "python": sys.executable})
    monkeypatch.setattr(body, "_listening", lambda: SimpleNamespace(mark=lambda **k: None))
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_run(True, calls))
    out = body.speak("Hello there. Keep listening.")
    assert out["engine"] == "piper:en_US-hfc_female-medium" and not any(c[0] == "espeak-ng" for c in calls)
    calls.clear()
    monkeypatch.setattr(subprocess, "run", _fake_run(False, calls))
    out = body.speak("Hello there.")
    assert out["engine"] == "espeak-ng" and "model failed to load" in out["fallback_from_neural"]
    assert any(c[0] == "espeak-ng" for c in calls), "the being never loses its voice to the neural engine"
