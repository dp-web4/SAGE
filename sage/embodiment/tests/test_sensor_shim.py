"""The sensor shim (sage/embodiment/sensor_shim.py). MEASURED ON SPROUT, 2026-11-17: all 222 frames its
eyes had saved were magenta, green about 35% below red and blue, in daylight and lamplight alike, and the
being described "purple light" in a normally lit room for five weeks. The shim corrects at the capture
thread every reader shares, and the frame's receipt says what was done."""
import json
import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from sage.embodiment import look, sensor_shim  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher  # noqa: E402

# Sprout's latest frame (11-17), as its mean BGR: a white-walled room at night, rendered magenta.
MAGENTA_ROOM = np.full((360, 640, 3), (153, 98, 146), np.uint8)


def _ratio(frame):
    b, g, r = frame.reshape(-1, 3).astype(float).mean(0)
    return g / ((r + b) / 2)


def test_the_magenta_cast_is_taken_out_and_the_shim_says_by_how_much(monkeypatch):
    monkeypatch.delenv(sensor_shim.SHIM_ENV, raising=False)
    shim = sensor_shim.for_sensor("imx219-argus")
    out = shim.apply(MAGENTA_ROOM)
    assert _ratio(MAGENTA_ROOM) < 0.7 and 0.97 < _ratio(out) < 1.03
    d = shim.describe()
    b, g, r = d["white_balance"]["gains_bgr"]
    assert d["sensor"] == "imx219-argus" and g > 1.3 and b < 1.0 and r < 1.0
    text = sensor_shim.describe_text(d)
    assert "corrected before you see them" in text and f"x{g:.2f}" in text and "cast, not the room's" in text


def test_a_scene_that_really_is_one_colour_is_muted_not_erased(monkeypatch):
    monkeypatch.delenv(sensor_shim.SHIM_ENV, raising=False)
    red_wall = np.full((360, 640, 3), (20, 20, 200), np.uint8)
    out = sensor_shim.for_sensor("imx219-argus").apply(red_wall)
    b, g, r = out.reshape(-1, 3).astype(float).mean(0)
    assert r > 1.5 * g and r > 1.5 * b                             # max_gain bounds it: still red


def test_one_odd_frame_does_not_swing_the_eye_and_dark_frames_teach_nothing(monkeypatch):
    monkeypatch.delenv(sensor_shim.SHIM_ENV, raising=False)
    wb = sensor_shim.WhiteBalance(every=1, smooth=0.2)
    wb.apply(MAGENTA_ROOM)
    settled = wb.describe()["gains_bgr"]
    wb.apply(np.full((360, 640, 3), (30, 30, 220), np.uint8))       # a red coat passes
    moved = wb.describe()["gains_bgr"]
    assert abs(moved[1] - settled[1]) < 0.25 * settled[1]
    before = wb.describe()["gains_bgr"]
    wb.apply(np.full((360, 640, 3), (3, 1, 4), np.uint8))           # lens covered: noise
    assert wb.describe()["gains_bgr"] == before


def test_off_is_the_raw_sensor_and_no_claim(monkeypatch):
    monkeypatch.setenv(sensor_shim.SHIM_ENV, "off")
    shim = sensor_shim.for_sensor("imx219-argus")
    assert shim.apply(MAGENTA_ROOM) is MAGENTA_ROOM and shim.describe() == {}
    assert sensor_shim.describe_text(shim.describe()) == ""


def test_a_profile_file_replaces_the_default_for_its_sensor(monkeypatch, tmp_path):
    p = tmp_path / "shim.json"
    p.write_text(json.dumps({"imx219-argus": {"white_balance": {"mode": "fixed", "gains": [0.8, 1.5, 0.85]}}}))
    monkeypatch.setenv(sensor_shim.SHIM_ENV, str(p))
    d = sensor_shim.for_sensor("imx219-argus").describe()["white_balance"]
    assert d == {"mode": "fixed", "gains_bgr": [0.8, 1.5, 0.85], "estimated": True}
    assert "fixed for this sensor" in sensor_shim.describe_text({"sensor": "x", "white_balance": d})


def test_the_look_answer_carries_the_correction(tmp_path):
    corr = {"sensor": "imx219-argus", "white_balance": {"mode": "grayworld", "gains_bgr": [0.8, 1.5, 0.85],
                                                       "estimated": True}}
    req, _, _ = look._dirs(str(tmp_path))
    (Path(req) / "r1.json").write_text(json.dumps({"id": "r1", "ts": __import__("time").time()}))
    (r,) = look.respond([MAGENTA_ROOM], [0], "open", body_dir=str(tmp_path), corrections=[corr])
    assert r["ok"] and r["correction"] == corr


def test_the_camera_receipt_tells_the_being_its_eye_was_corrected(tmp_path, monkeypatch):
    monkeypatch.setattr(HestiaF1aDispatcher, "_call",
                        lambda self, n, a: {"actionId": "act"} if n == "hestia_begin_action" else {}, raising=False)
    d = HestiaF1aDispatcher.__new__(HestiaF1aDispatcher)
    d.worktree, d.memory_root, d.camera_source = None, str(tmp_path), "cortex"
    import sage.gateway.hestia_dispatch as hd
    corr = {"sensor": "imx219-argus", "white_balance": {"mode": "grayworld", "gains_bgr": [0.8, 1.5, 0.85],
                                                       "estimated": True}}

    def ok_run(cmd, **kw):
        Path(cmd[-1]).write_bytes(b"\xff\xd8\xffJPEG\xff\xd9")
        return types.SimpleNamespace(returncode=0, stderr=b"",
                                     stdout=json.dumps({"eye": "left", "correction": corr}).encode())
    monkeypatch.setattr(hd.subprocess, "run", ok_run)
    env = d._do_camera(BeingIntent("camera", {"out_path": "scratch/camera/f.jpg"}))
    assert env.ok and env.result["correction"] == corr
    assert "corrected before you see them" in env.result["note"] and "green x1.50" in env.result["note"]

    def raw_run(cmd, **kw):                                          # no shim: no claim of one
        Path(cmd[-1]).write_bytes(b"\xff\xd8\xffJPEG\xff\xd9")
        return types.SimpleNamespace(returncode=0, stderr=b"", stdout=b"not json")
    monkeypatch.setattr(hd.subprocess, "run", raw_run)
    env = d._do_camera(BeingIntent("camera", {"out_path": "scratch/camera/g.jpg"}))
    assert env.ok and "correction" not in env.result and "corrected" not in env.result["note"]


def test_the_cortex_capture_thread_stores_the_corrected_frame(monkeypatch):
    """Every reader takes Camera.frame, so that is where the correction must already be."""
    monkeypatch.delenv(sensor_shim.SHIM_ENV, raising=False)
    from sage.embodiment import visual_cortex as vc
    cam = vc.Camera.__new__(vc.Camera)
    cam.shim, cam.frame, cam.ok, cam.running = sensor_shim.for_sensor("imx219-argus"), None, True, True

    class OneFrame:
        def read(self):
            cam.running = False
            return True, MAGENTA_ROOM.copy()
    cam.cap = OneFrame()
    vc.Camera.run(cam)
    assert 0.97 < _ratio(cam.frame) < 1.03
