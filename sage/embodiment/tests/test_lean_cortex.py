"""A lean cortex, per body (2026-10-11).

Measured on Sprout (7.4 GB unified, desktop kept): the cortex cost ~700 MB of available memory, an eye ~235 MB
each and YOLO/TensorRT/torch ~350 MB; whisper base.en held ~430 MB of GPU once loaded. That is the room a 4B model
with its own vision needs. One eye, no detector and an ear that frees whisper when idle are per-body settings; the
defaults are the full organ. With one eye open the organ must still tell the truth: a resting eye is not a dark
one, and with no second eye to compare, a still view is not a stalled one."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.embodiment import listening  # noqa: E402
from sage.embodiment import visual_cortex as vc  # noqa: E402
from sage.gateway import body  # noqa: E402

ROI = {"cx": 0.8, "cy": 0.5, "w": 0.5, "h": 0.375}


def _eye(motion=0.0, side="left", **k):
    return {"motion": motion, "attention": ROI, "trust": 0.9, "frozen": False, "stalled": False, "side": side, **k}


def test_defaults_are_the_full_organ(monkeypatch):
    for k in ("SAGE_CORTEX_EYES", "SAGE_CORTEX_DETECT", "SAGE_CORTEX_SENSOR_MODE"):
        monkeypatch.delenv(k, raising=False)
    assert vc._env_eyes() == [0, 1]
    assert "sensor-mode" not in vc.gst_pipeline(0)


def test_eyes_setting_parses_and_never_opens_nothing(monkeypatch):
    for v, want in (("0", [0]), ("1", [1]), ("0,1", [0, 1]), ("0,0", [0]),
                    ("1,0", [0, 1]), ("1,1,0", [0, 1]), (" 1 ", [1]),
                    ("7", [0, 1]), ("x", [0, 1]), ("", [0, 1])):
        monkeypatch.setenv("SAGE_CORTEX_EYES", v)
        assert vc._env_eyes() == want, v


def test_sensor_mode_is_passed_to_argus(monkeypatch):
    monkeypatch.setattr(vc, "SENSOR_MODE", "4")
    assert "nvarguscamerasrc sensor-id=0 sensor-mode=4 !" in vc.gst_pipeline(0)
    monkeypatch.setattr(vc, "SENSOR_MODE", "four")
    assert "sensor-mode" not in vc.gst_pipeline(0)


def test_one_eye_by_design_is_not_called_one_eye_only():
    binoc = {"agreement": None, "offset": [0, 0], "depth": "unknown"}
    d = vc.describe([_eye(0.4)], binoc, {"self_motion": "still"})
    assert "motion to the" in d and "one eye only" not in d and "uncorrelated" not in d
    assert vc.describe([_eye(0.0)], binoc, {}).startswith("the scene is still")


def test_two_eyes_are_described_as_before():
    binoc = {"agreement": 0.2}
    d = vc.describe([_eye(0.4), _eye(0.0, "right")], binoc, {})
    assert "(one eye only)" in d


def test_a_dark_eye_is_named_by_its_side_not_its_index():
    d = vc.describe([_eye(0.0, "right", stalled=True, frozen=True)], {"agreement": None}, {})
    assert d.startswith("my right eye has gone dark")


def _cortex(n_sids):
    c = vc.VisualCortex.__new__(vc.VisualCortex)
    c.sids = n_sids
    c._stall = [vc.STALL_CYCLES + 2] * len(n_sids)
    return c


def test_one_still_eye_is_stale_not_stalled_without_a_second_to_compare():
    c = _cortex([0])
    eyes = [_eye(0.0, frozen=True)]
    c._adjudicate_sensors(eyes, {"agreement": None}, {"self_motion": "still"})
    assert eyes[0]["sensor"] == "stale-unverified" and not eyes[0]["stalled"]


def test_one_eye_that_did_not_change_while_the_body_moved_is_stalled():
    c = _cortex([0])
    eyes = [_eye(0.0, frozen=True)]
    c._adjudicate_sensors(eyes, {"agreement": None}, {"self_motion": "moving"})
    assert eyes[0]["stalled"] and eyes[0]["trust"] == 0.0


def test_two_eyes_disagreeing_still_marks_the_frozen_one_stalled():
    c = _cortex([0, 1])
    eyes = [_eye(0.0, frozen=True), _eye(0.0, "right")]
    c._adjudicate_sensors(eyes, {"agreement": 0.1}, {"self_motion": "still"})
    assert eyes[0]["stalled"]


def test_a_resting_eye_reaches_the_being_as_resting(tmp_path):
    p = tmp_path / "perception.json"
    p.write_text(json.dumps({"descriptor": "the scene is still; clear view", "cameras": {"0": _eye()},
                             "eyes_resting": ["right"], "audio": {"ok": True}}))
    per = body.perception(now=time.time(), path=str(p))
    assert per["eyes"] == 1 and per["eyes_live"] == 1 and per["eyes_resting"] == ["right"]
    out = body.render({"perception": per, "metabolism": {}, "gaze": {}}, None, proprioception=False)
    assert "1 of 1 eyes live; your right eye is resting" in out


def test_no_resting_field_no_resting_words(tmp_path):
    p = tmp_path / "perception.json"
    p.write_text(json.dumps({"descriptor": "x", "cameras": {"0": _eye(), "1": _eye(side="right")}}))
    per = body.perception(now=time.time(), path=str(p))
    out = body.render({"perception": per, "metabolism": {}, "gaze": {}}, None, proprioception=False)
    assert per["eyes_resting"] == [] and "resting" not in out and "2 of 2 eyes live" in out


def test_the_ear_frees_whisper_only_when_set_and_idle(monkeypatch):
    t = listening.Transcriber(source="test")
    t.model, t._last_use = object(), 1000.0
    monkeypatch.setattr(listening, "UNLOAD_IDLE_S", 0.0)
    assert t.unload_if_idle(now=99999.0) is False and t.model is not None, "default: never"
    monkeypatch.setattr(listening, "UNLOAD_IDLE_S", 300.0)
    assert t.unload_if_idle(now=1200.0) is False and t.model is not None, "not idle long enough"
    assert t.unload_if_idle(now=1301.0) is True and t.model is None and t.status == "idle"
    assert t.unload_if_idle(now=99999.0) is False, "nothing loaded"


def test_the_ear_model_is_a_body_setting(monkeypatch):
    monkeypatch.setattr(listening, "MODEL_NAME", "tiny.en")
    assert listening.Transcriber(source="test").model_name == "tiny.en"
    assert listening.Transcriber(source="test", model_name="base.en").model_name == "base.en"


# THE LOOP ITSELF, with fake hardware (2026-10-11). The first live trial of one eye died on its first open-gaze
# tick: the state dict still built `cameras` with `range(2)`. Every unit above passed; the loop was never run.
class _FakeCam:
    def __init__(self, sid):
        import numpy as np
        self.sid, self.ok, self.stopped = sid, True, False
        self.frame = (np.random.default_rng(sid).integers(0, 255, (360, 640, 3))).astype("uint8")

    def start(self):
        pass

    def stop(self):
        self.stopped = True


class _Organ:
    def __init__(self, *a, **k):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def state(self):
        return {"self_motion": "still", "gyro_mag": 0.0, "ok": True, "level": 0.0, "onset": False}


def _one_tick(monkeypatch, tmp_path, eyes):
    import pytest
    monkeypatch.setattr(vc, "EYES", eyes)
    monkeypatch.setattr(vc, "DETECT", False)
    monkeypatch.setattr(vc, "Camera", _FakeCam)
    monkeypatch.setattr(vc, "Proprioception", _Organ)
    monkeypatch.setattr(vc, "Hearing", _Organ)
    monkeypatch.setattr(vc, "DISPARITY_PATH", str(tmp_path / "disparity.json"))
    monkeypatch.setattr(vc.time, "sleep", lambda s: None)
    c = vc.VisualCortex()
    c._read_gaze = lambda: ("open", None)
    c._note_choice = lambda g, t: None
    c.journal = types_journal()
    states = []

    def emit(state):
        if c.resting:
            state["eyes_resting"] = list(c.resting)
        states.append(state)
        if len(states) >= 2:
            raise KeyboardInterrupt   # run() treats it as a stop: the finally releases the fakes

    c._emit = emit
    c.run()
    assert all(cam.stopped for cam in c.cams)
    if not states:
        pytest.fail("no perceptual state emitted")
    return c, states[-1]


def types_journal():
    import types
    return types.SimpleNamespace(observe=lambda s, sal: None, _append=lambda ev: None)


def test_one_eye_runs_the_real_loop_and_tells_the_truth(monkeypatch, tmp_path):
    c, st = _one_tick(monkeypatch, tmp_path, [0])
    assert list(st["cameras"]) == ["0"] and st["cameras"]["0"]["side"] == "left"
    assert st["eyes_resting"] == ["right"] and st["binocular"]["agreement"] is None
    assert 0.0 <= st["coherence"] <= 1.0 and "one eye only" not in st["descriptor"]
    assert c.detector is None


def test_the_right_eye_alone_is_keyed_and_named_as_the_right(monkeypatch, tmp_path):
    _, st = _one_tick(monkeypatch, tmp_path, [1])
    assert list(st["cameras"]) == ["1"] and st["cameras"]["1"]["side"] == "right" and st["eyes_resting"] == ["left"]
    assert st["dominant_eye"] == 1, "dominant eye is the physical sensor ID, not the compact list index"


def test_right_eye_alone_is_dominant_in_blind_state_too(monkeypatch, tmp_path):
    c, _ = _one_tick(monkeypatch, tmp_path, [1])
    states = []
    c._emit = states.append
    c._sense_blind([0], [None], "open", None)
    assert list(states[-1]["cameras"]) == ["1"]
    assert states[-1]["dominant_eye"] == 1
    assert states[-1]["cameras"]["1"]["side"] == "right"


def test_two_eyes_run_the_real_loop_as_before(monkeypatch, tmp_path):
    _, st = _one_tick(monkeypatch, tmp_path, [0, 1])
    assert list(st["cameras"]) == ["0", "1"] and "eyes_resting" not in st
    assert st["binocular"]["agreement"] is not None
