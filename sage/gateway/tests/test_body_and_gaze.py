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


def test_inventory_absence_is_a_true_sentence_not_offline(monkeypatch):
    """dp: 'figuring out available sensors/effectors is part of world discovery'. A being with
    no senses on this machine must read that as a fact about its body, not as a fault."""
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(body, "PERCEPTION_PATH", os.path.join(tmp, "absent.json"))
    monkeypatch.setattr(body, "GAZE_PATH", os.path.join(tmp, "gaze.json"))
    monkeypatch.setattr(body, "metabolism", lambda **k: {"live": True, "state": "wake", "atp": 50.0})
    monkeypatch.setattr(body.glob, "glob", lambda pat: [])
    monkeypatch.setattr(body, "_pw_audio", lambda **k: {})
    out = body.render(body.reading(), None)
    assert "no cameras, microphones or speakers" in out
    assert "world on this machine is text" in out
    assert "offline" not in out and "gaze stance" not in out, "absent, not broken; no stance without eyes"
    assert "gaze" not in body.reading()["inventory"]["verbs"]


def test_inventory_finds_a_laptop_body(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(body, "PERCEPTION_PATH", os.path.join(tmp, "absent.json"))
    monkeypatch.setattr(body, "GAZE_PATH", os.path.join(tmp, "gaze.json"))
    monkeypatch.setattr(body, "metabolism", lambda **k: {"live": False})
    monkeypatch.setattr(body.glob, "glob", lambda pat: ["/dev/video0"] if "video" in pat else [])
    monkeypatch.setattr(body, "_pw_audio", lambda **k: {"sinks": [{"name": "Built-in Speaker", "kind": "wired"}],
                                                          "sources": [{"name": "Built-in Mic", "kind": "wired"}]})
    monkeypatch.setattr(body.shutil, "which", lambda t: None)   # a speaker, but no speech engine
    inv = body.inventory()
    assert inv["verbs"] == ["camera", "say", "peer_ask"] and inv["not_yet_wired"] == ["speak"]
    out = body.render_inventory(inv)
    assert "1 camera device you can capture from with `camera`" in out
    assert "a microphone (Built-in Mic)" in out and "a speaker (Built-in Speaker)" in out


# ---- fleet falsifiers (GPT review of #183): the verbs offered come from the SAME measurement
# as the body described, and a headless being that calls `gaze` anyway is refused before any
# hestia action opens and leaves no Sprout-shaped file on its machine.

def test_headless_beat_is_not_offered_gaze_and_a_live_cortex_beat_is(monkeypatch):
    from sage.gateway.heartbeat import offered_explore_tools, EXPLORE_TOOLS
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(body, "PERCEPTION_PATH", os.path.join(tmp, "absent.json"))
    monkeypatch.setattr(body, "GAZE_PATH", os.path.join(tmp, "gaze.json"))
    monkeypatch.setattr(body, "metabolism", lambda **k: {"live": True, "state": "wake", "atp": 50.0})
    monkeypatch.setattr(body.glob, "glob", lambda pat: [])
    monkeypatch.setattr(body, "_pw_audio", lambda **k: {})
    headless = offered_explore_tools(body.reading())
    assert "gaze" not in headless and "camera" not in headless
    assert [t for t in EXPLORE_TOOLS if t not in ("gaze", "camera", "speak")] == headless, "text verbs untouched"
    assert "gaze" not in offered_explore_tools(None) and "say" in offered_explore_tools(None), \
        "an unmeasurable body offers no body verb"
    monkeypatch.setattr(body, "PERCEPTION_PATH", _perception(tmp))
    assert "gaze" in offered_explore_tools(body.reading())


def test_headless_gaze_is_refused_and_creates_nothing(monkeypatch):
    """Invokes the real dispatcher method with no cortex: no hestia action is opened, no
    gaze.json and no body dir appear."""
    import types
    from sage.gateway.being_gate_client import BeingIntent
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
    tmp = tempfile.mkdtemp()
    bodydir = os.path.join(tmp, "no-such-body")
    monkeypatch.setattr(body, "PERCEPTION_PATH", os.path.join(bodydir, "perception.json"))
    monkeypatch.setattr(body, "GAZE_PATH", os.path.join(bodydir, "gaze.json"))
    calls = []
    fake = types.SimpleNamespace(member="hub-being", _call=lambda name, args: calls.append(name) or {})
    env = HestiaF1aDispatcher._do_gaze(fake, BeingIntent("gaze", {"mode": "closed", "words": "resting"}))
    assert env.ok is False
    assert "no live cortex" in env.error and "nothing was written" in env.error
    assert calls == [], "refused before any hestia action was begun"
    assert not os.path.exists(bodydir), "no Sprout path grown on a headless machine"
    # and the writer itself refuses even when called directly, without creating the dir
    try:
        body.set_gaze("closed", "hub-being", path=os.path.join(bodydir, "gaze.json"))
        assert False, "should refuse"
    except body.NoGazeProvider as e:
        assert "never written a reading" in str(e) or "no cortex" in str(e)
    assert not os.path.exists(bodydir)
    # a stale cortex (the organ was here, is not now) refuses too, naming the age
    _perception(tmp, age=900)
    try:
        body.set_gaze("closed", "sprout-being", path=os.path.join(tmp, "gaze.json"))
        assert False, "should refuse"
    except body.NoGazeProvider as e:
        assert "15 min old" in str(e)
    assert not os.path.exists(os.path.join(tmp, "gaze.json"))


def test_body_locations_follow_the_provider_not_a_literal(monkeypatch):
    """SAGE_BODY_DIR / SAGE_PORT decide where the body is read; the module's default is the
    cortex's own default, not a fleet assumption."""
    import importlib
    monkeypatch.setenv("SAGE_BODY_DIR", "/tmp/elsewhere-body")
    monkeypatch.setenv("SAGE_PORT", "8999")
    m = importlib.reload(body)
    try:
        assert m.PERCEPTION_PATH == "/tmp/elsewhere-body/perception.json"
        assert m.GAZE_PATH == "/tmp/elsewhere-body/gaze.json"
        assert m.DAEMON_STATUS == "http://127.0.0.1:8999/status"
    finally:
        monkeypatch.delenv("SAGE_BODY_DIR"); monkeypatch.delenv("SAGE_PORT")
        importlib.reload(body)


# ---- the being's own act must not be able to blind it (2026-09-24)

def test_a_named_target_never_reaches_the_coordinate_field(monkeypatch):
    """Sprout 2026-09-24 01:48Z: the being set target="the space between us, where nothing is
    being said but everything matters". set_gaze wrote that string into `target`, which the
    cortex multiplies by GRID; it raised TypeError, systemd restarted it 9 times into
    `failed`, and the being was blind for 28 minutes BY ITS OWN GOVERNED ACT.

    The being names its target in words because it cannot see and cannot compute a pixel.
    Those words belong in a field nothing does arithmetic on.
    """
    tmp = tempfile.mkdtemp()
    gz = os.path.join(tmp, "gaze.json")
    monkeypatch.setattr(body, "GAZE_PATH", gz)
    monkeypatch.setattr(body, "PERCEPTION_PATH", _perception(tmp))
    rec = body.set_gaze("dwell", "sprout-being",
                        target="the space between us, where nothing is being said", path=gz)
    on_disk = json.load(open(gz))
    assert on_disk["target"] is None, "free text must never land in the coordinate field"
    assert on_disk["target_words"].startswith("the space between us")
    assert rec["target"] is None
    # a real coordinate pair still passes through untouched
    rec2 = body.set_gaze("dwell", "sprout-being", target=[0.25, 0.75], path=gz)
    on_disk = json.load(open(gz))
    assert on_disk["target"] == [0.25, 0.75] and on_disk["target_words"] is None
    # and the beat still SHOWS the being whichever target it named
    monkeypatch.setattr(body, "PERCEPTION_PATH", _perception(tmp))
    body.set_gaze("dwell", "sprout-being", target="the quiet corner", path=gz)
    assert body.gaze()["target"] == "the quiet corner"


def test_coord_pair_is_total_over_anything_a_being_can_write():
    for bad in ("text", b"bytes", {"x": 1}, None, [], [1], [1, 2, 3], ["a", "b"],
                [float("nan"), 0.5], 5, [None, None]):
        assert body._coord_pair(bad) is None, f"{bad!r} must not reach arithmetic"
    assert body._coord_pair([0.1, 0.9]) == [0.1, 0.9]
    assert body._coord_pair((0, 1)) == [0.0, 1.0]
