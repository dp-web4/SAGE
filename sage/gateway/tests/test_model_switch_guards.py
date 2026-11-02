"""Two guards a model switch needs (Sprout 2026-10-12, moving sprout-being to the 4B with vision).

1. A TAGGED NAME KEEPS ITS SIZE'S LIMITS. `qwen3.8-distill:4b-q4-vision` missed the declared `4b` variant,
   num_ctx fell to the 8192 floor, and 36 of 37 beats were refused by Ollama for 13 hours.
2. NO IMAGE TO A MODEL THAT CANNOT READ ONE. The 2B answers an image with a 500, which fails the beat."""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.gateway import heartbeat as hb  # noqa: E402
from sage.irp.adapters.model_capabilities import ModelCapabilities, load_capabilities  # noqa: E402


def _caps(variants):
    c = ModelCapabilities.__new__(ModelCapabilities)
    c.variants = variants
    c.num_predict, c.think_default, c.thinking_supported = None, None, True
    return c


def test_a_tagged_build_keeps_its_sizes_declared_window():
    c = _caps({"4b": {"num_ctx": 16384, "num_predict_think": 6000}, "4b-q4": {"num_ctx": 12288}})
    assert c.resolve_num_ctx("m:4b-q3-vision", 8192) == 16384           # "4b" is the prefix
    assert c.resolve_num_ctx("m:4b-q4-vision", 8192) == 12288           # the longest declared prefix wins
    assert c.resolve_num_ctx("m:4b", 8192) == 16384                     # exact, unchanged
    assert c.resolve_num_ctx("m:4bx", 8192) == 8192                     # a prefix only at a dash
    assert c.resolve_num_ctx("m:zz", 8192) == 8192                      # undeclared: the floor
    assert c.resolve_num_predict("m:4b-vision", True) == 6000


def test_the_real_config_gives_the_vision_tag_the_4b_window():
    m = "qwen3.8-distill:4b-q4-vision"
    assert load_capabilities(m).resolve_num_ctx(m, 8192) == 16384


FRAME = ("b64data", {"path": "/x/f.jpg", "carried": True})


def test_a_frame_is_withheld_from_a_model_that_cannot_read_it_and_the_being_is_told():
    out = hb.frames_the_model_can_read([FRAME], "qwen3.8-distill:2b", reads=lambda m: False)
    assert out[0][0] is None and out[0][1]["carried"] is False
    assert "cannot read images" in out[0][1]["why"] and "qwen3.8-distill:2b" in out[0][1]["why"]


def test_a_model_that_reads_images_gets_the_frame_and_no_frame_means_no_question():
    assert hb.frames_the_model_can_read([FRAME], "m:4b", reads=lambda m: True) == [FRAME]
    asked = []
    hb.frames_the_model_can_read([(None, {"carried": False})], "m", reads=lambda m: asked.append(m) or False)
    assert asked == []                                                  # no frame: Ollama is not asked


def test_vision_is_read_from_ollamas_capabilities_and_unknown_is_no(monkeypatch):
    import urllib.request
    answers = {"seer": {"capabilities": ["completion", "vision"]}, "blind": {"capabilities": ["completion"]}}

    def fake(req, timeout=0):
        m = json.loads(req.data)["model"]
        if m not in answers:
            raise OSError("unreachable")
        return io.BytesIO(json.dumps(answers[m]).encode())
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    monkeypatch.setattr(hb, "_READS_IMAGES", {})
    assert hb.model_reads_images("seer") is True
    assert hb.model_reads_images("blind") is False
    assert hb.model_reads_images("gone") is False                      # unknown is no, never a failed beat


def _last(t0, *acts):
    return {"t0": t0, "explore": {"trace": [dict(effector="camera", ok=ok, args={"out_path": p},
                                                result={"out_path": p} if ok else None) for p, ok in acts]}}


def test_a_frame_saved_outside_scratch_camera_still_reaches_the_being(tmp_path):
    """sprout-being's first look (2026-10-12 21:02) saved scratch/test-vision.jpg; the beat looked only
    under scratch/camera/, so the frame never rode."""
    import time
    t0 = time.time() - 5
    (tmp_path / "scratch").mkdir()
    jpg = b"\xff\xd8\xff" + b"x" * 64 + b"\xff\xd9"
    (tmp_path / "scratch" / "test-vision.jpg").write_bytes(jpg)
    last = _last(t0, ("scratch/test-vision.jpg", True), ("scratch/failed.jpg", False), ("../outside.jpg", True))
    paths = hb.camera_frame_paths(last, tmp_path)
    assert [p.name for p in paths] == ["test-vision.jpg"]                # the failed act and the escape are not taken
    frames = hb.fresh_frames(tmp_path, None, t0, extra=paths)
    assert [m.get("carried") for _, m in frames] == [True] and frames[0][0]
    assert hb.fresh_frames(tmp_path, None, t0) == []                       # without the act's path: the old miss


def test_no_last_beat_or_no_camera_act_adds_nothing(tmp_path):
    assert hb.camera_frame_paths(None, tmp_path) == []
    assert hb.camera_frame_paths({"explore": {"trace": [{"effector": "gaze", "ok": True}]}}, tmp_path) == []
