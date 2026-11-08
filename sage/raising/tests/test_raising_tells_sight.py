"""
The raising session tells a being whether it sees, from the model's capability.

Since 2026-10-12 Sprout's 4B has seen its own camera frames in beats, while the
raising session's gaze offering still said "you don't see through them directly".
The wording now follows `model_reads_images` (the beat's own check); a model
without vision keeps the text-only wording.

Run:
    python3 -m pytest -q -c /dev/null sage/raising/tests/test_raising_tells_sight.py
"""

import json
import sys
import time
from pathlib import Path

_RAISING = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RAISING.parent.parent))
sys.path.insert(0, str(_RAISING / "scripts"))

import ollama_raising_session as ors  # noqa: E402


def _gaze_prompt(tmp_path, monkeypatch, reads):
    (tmp_path / ".sprout").mkdir()
    (tmp_path / ".sprout" / "perception.json").write_text(json.dumps({"ts": time.time()}))
    monkeypatch.setenv("HOME", str(tmp_path))
    s = object.__new__(ors.OllamaRaisingSession)
    s.phase = "creating"
    s._reads_images = reads
    seen = []

    def gen(prompt):
        seen.append(prompt)
        raise RuntimeError("stop here")  # the offering returns before writing gaze.json

    s.generate_response = gen
    s._offer_gaze_choice()
    assert len(seen) == 1
    return seen[0]


def test_a_seeing_model_is_told_it_sees(tmp_path, monkeypatch):
    p = _gaze_prompt(tmp_path, monkeypatch, True)
    assert "You can see through them in your beats" in p
    assert "don't see through them directly" not in p
    assert "not hypothetical" in p


def test_a_text_only_model_keeps_the_text_wording(tmp_path, monkeypatch):
    p = _gaze_prompt(tmp_path, monkeypatch, False)
    assert "don't see through them directly" in p
    assert "limited descriptions in words" in p
    assert "see through them in your beats" not in p


def test_unknown_sight_is_text_only(tmp_path, monkeypatch):
    (tmp_path / ".sprout").mkdir()
    (tmp_path / ".sprout" / "perception.json").write_text(json.dumps({"ts": time.time()}))
    monkeypatch.setenv("HOME", str(tmp_path))
    s = object.__new__(ors.OllamaRaisingSession)
    s.phase = "creating"
    seen = []
    s.generate_response = lambda prompt: (seen.append(prompt), (_ for _ in ()).throw(RuntimeError()))[1]
    s._offer_gaze_choice()
    assert "don't see through them directly" in seen[0]
