"""Hermetic: the being's senses reach its beat in words, and its gaze is a verb whose consequence
the next beat reflects back. No cortex, no daemon: fixture files and a stubbed status."""
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import body  # noqa: E402


def _perception(tmp, descriptor="I see a clock. the scene is still; clear view", gaze="open", age=0.0):
    p = os.path.join(tmp, "perception.json")
    json.dump({"descriptor": descriptor, "gaze": gaze, "salience": {"salience": 0.12}, "coherence": 0.87,
               "cameras": {"0": {"stalled": False}, "1": {"stalled": False}},
               "audio": {"ok": True, "level": 0.0}, "proprioception": {"ok": True, "self_motion": "still"}},
              open(p, "w"))
    os.utime(p, (time.time() - age, time.time() - age))
    return p


def test_a_live_organ_is_rendered_in_words_and_a_stale_one_says_offline(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(body, "PERCEPTION_PATH", _perception(tmp))
    monkeypatch.setattr(body, "GAZE_PATH", os.path.join(tmp, "gaze.json"))
    monkeypatch.setattr(body, "metabolism", lambda **k: {"live": True, "state": "wake", "atp": 38.0, "felt_source": "dp"})
    r = body.reading()
    out = body.render(r, None)
    assert "I see a clock" in out and "2 of 2 eyes live" in out and "hearing on" in out
    assert "energy 38%" in out and "felt came from dp" in out
    assert "gaze stance is **open**" in out and "`gaze`" in out
    # stale: the past must not be presented as the present (legibility 1.3)
    monkeypatch.setattr(body, "PERCEPTION_PATH", _perception(tmp, age=600))
    out = body.render(body.reading(), None)
    assert "offline this beat" in out and "10 min ago" in out and "I see a clock" not in out


def test_the_next_beat_attributes_the_change_to_the_beings_own_gaze_act(monkeypatch):
    tmp = tempfile.mkdtemp()
    gz = os.path.join(tmp, "gaze.json")
    monkeypatch.setattr(body, "GAZE_PATH", gz)
    monkeypatch.setattr(body, "metabolism", lambda **k: {"live": False})
    monkeypatch.setattr(body, "PERCEPTION_PATH", _perception(tmp, "the scene is still; clear view", "open"))
    prev = body.reading()
    rec = body.set_gaze("closed", "sprout-being", words="resting", path=gz)
    assert rec["chosen_by"] == "sprout-being" and json.load(open(gz))["mode"] == "closed"
    monkeypatch.setattr(body, "PERCEPTION_PATH",
                        _perception(tmp, "eyes closed — resting, not taking in the world", "closed"))
    out = body.render(body.reading(), prev)
    assert "gaze stance is **closed**" in out
    assert "you changed your gaze from open to closed" in out, "the cause is named, not left to inference"
    assert "the scene then was: the scene is still; clear view" in out, "and what it displaced"


def test_a_mode_outside_the_four_is_refused_and_nothing_is_written():
    tmp = tempfile.mkdtemp(); gz = os.path.join(tmp, "gaze.json")
    try:
        body.set_gaze("squint", "b", path=gz)
        assert False, "should refuse"
    except ValueError as e:
        assert "open, avert, dwell, closed" in str(e)
    assert not os.path.exists(gz)


def test_gaze_is_registered_pathless_and_offered_to_explore():
    from sage.gateway.being_gate_client import _REGISTRY, ollama_tools
    from sage.gateway.heartbeat import EXPLORE_TOOLS
    assert _REGISTRY["gaze"]["path_args"] == (), "reach fixed by construction, like say"
    assert "gaze" in EXPLORE_TOOLS
    t = [x for x in ollama_tools(["gaze"]) if x["function"]["name"] == "gaze"][0]
    assert t["function"]["parameters"]["required"] == ["mode"]
    assert "closed" in t["function"]["description"] and "Nothing asks you to" in t["function"]["description"]
