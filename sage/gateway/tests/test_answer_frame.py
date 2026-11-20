"""The answer turn is given its last look (answer_frame): the newest frame and its age, or a line saying it is not
seeing. sprout-being 2026-11-17: asked what was really beyond a door, its answer turn, which carried no image,
described a room that was not there."""
import io
import json
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import heartbeat as hb  # noqa: E402
from sage.gateway.tests.test_answer_turn_json import LLM, Client, TURN  # noqa: E402


def _jpeg(path, mtime):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 36), (120, 70, 140)).save(buf, "JPEG")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())
    os.utime(path, (mtime, mtime))
    return path


def test_no_frame_on_disk_claims_nothing(tmp_path):
    assert hb.answer_frame(tmp_path, None, "m", reads=lambda m: True) == (None, "", {})


def test_the_newest_frame_rides_with_its_time(tmp_path):
    now = time.time()
    _jpeg(tmp_path / "scratch/camera/old.jpg", now - 5 * 3600)
    _jpeg(tmp_path / "scratch/camera/new.jpg", now - 17 * 60)
    b64, line, meta = hb.answer_frame(tmp_path, None, "m", now=now, reads=lambda m: True)
    assert b64 and meta["carried"] and meta["path"].endswith("new.jpg"), meta
    assert line.startswith("The image with this message is your last look through your eyes, taken at ")
    assert "(17 min ago)" in line and "may have changed since" in line, line


def test_an_old_frame_or_a_blind_model_is_told_not_shown(tmp_path):
    now = time.time()
    _jpeg(tmp_path / "scratch/camera/a.jpg", now - hb.ANSWER_FRAME_MAX_AGE_S - 60)
    b64, line, meta = hb.answer_frame(tmp_path, None, "m", now=now, reads=lambda m: True)
    assert b64 is None and not meta["carried"] and "older than 24 h" in meta["why"]
    assert line.startswith("No image is with this message: as you write it, you are not seeing. Your last look")
    _jpeg(tmp_path / "scratch/camera/a.jpg", now - 60)
    b64, line, meta = hb.answer_frame(tmp_path, None, "text-only", now=now, reads=lambda m: False)
    assert b64 is None and "text-only" in meta["why"] and "(1 min ago)" in line, (meta, line)


def test_the_answer_turn_carries_the_image_and_the_line_and_records_it(tmp_path):
    now = time.time()
    _jpeg(tmp_path / "scratch/camera/f.jpg", now - 120)
    frame = hb.answer_frame(tmp_path, None, "m", now=now, reads=lambda m: True)
    llm, client = LLM(json.dumps({"answer": True, "message": "dark beyond the door"})), Client()
    res = hb.answer_turn_json(client, llm, hb.SelectedTurn("dp", TURN), name="s", machine="s", member="s",
                              frame=frame)
    user = llm.calls[0]["messages"][1]
    assert user["images"] == [frame[0]] and frame[1] in user["content"]
    assert user["content"].index(frame[1]) < user["content"].index(TURN["text"])   # read before the ask
    assert res.answer_form["frame"]["carried"] is True
    # without one: no image, no line, nothing recorded
    llm = LLM(json.dumps({"answer": False, "message": ""}))
    res = hb.answer_turn_json(Client(), llm, hb.SelectedTurn("dp", TURN), name="s", machine="s", member="s")
    assert "images" not in llm.calls[0]["messages"][1] and "frame" not in res.answer_form


def test_a_newer_look_saved_outside_scratch_camera_wins(tmp_path):
    # legion-claude on #762: the being names its own out_path; a look saved to scratch/test-vision.jpg a minute ago
    # must win over a 5 h old frame under scratch/camera/, found through this beat's own camera act.
    from types import SimpleNamespace as NS
    now = time.time()
    _jpeg(tmp_path / "scratch/camera/old.jpg", now - 5 * 3600)
    _jpeg(tmp_path / "scratch/test-vision.jpg", now - 60)
    explore = NS(trace=[(NS(effector="camera", args={"out_path": "scratch/test-vision.jpg"}),
                         NS(ok=True, result={"out_path": "scratch/test-vision.jpg"}))])
    extra = hb.camera_paths_this_beat(tmp_path, explore=explore, posture=None, reflect=None)
    b64, line, meta = hb.answer_frame(tmp_path, None, "m", now=now, reads=lambda m: True, extra=extra)
    assert meta["path"].endswith("test-vision.jpg") and "(1 min ago)" in line, (meta, line)
    # without the act's path the old frame is all it finds: the failure this guards
    _, line, meta = hb.answer_frame(tmp_path, None, "m", now=now, reads=lambda m: True)
    assert meta["path"].endswith("old.jpg")
