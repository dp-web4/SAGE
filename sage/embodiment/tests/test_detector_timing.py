"""Track B baseline instrument (compiled-transducers arc): the detector's stage timing, measurement only.
No GPU here: post-processing is checked for equivalence with main's inline code, and the summary/log are pure."""
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.embodiment import detector  # noqa: E402


def _synthetic(seed):
    rng = np.random.default_rng(seed)
    out = rng.random((84, 8400)).astype(np.float32)
    out[:4] *= 640.0                                   # boxes in letterboxed space
    out[4:] *= 0.55                                    # most class scores under conf, a few over
    return out


def _main_inline(det, out, s, px, py, W, H):
    """main's detect() post-processing, copied verbatim from origin/main at the time of this change."""
    out = out.T
    cls_scores = out[:, 4:]
    cls = cls_scores.argmax(1); conf = cls_scores[np.arange(len(cls)), cls]
    m = conf >= det.conf
    if not m.any():
        return []
    xywh = out[m, :4]; conf = conf[m]; cls = cls[m]
    cx, cy, bw, bh = xywh[:, 0], xywh[:, 1], xywh[:, 2], xywh[:, 3]
    x1 = (cx - bw / 2 - px) / s; y1 = (cy - bh / 2 - py) / s
    x2 = (cx + bw / 2 - px) / s; y2 = (cy + bh / 2 - py) / s
    boxes = np.stack([x1, y1, x2, y2], 1)
    keep = detector._nms(boxes, conf, det.iou)[: det.max_det]
    dets = []
    for i in keep:
        bx = boxes[i]
        dets.append({"label": detector.COCO[int(cls[i])] if int(cls[i]) < len(detector.COCO) else str(int(cls[i])),
                     "conf": round(float(conf[i]), 3),
                     "box": [int(np.clip(bx[0], 0, W)), int(np.clip(bx[1], 0, H)),
                             int(np.clip(bx[2], 0, W)), int(np.clip(bx[3], 0, H))],
                     "cls": int(cls[i])})
    return dets


def test_post_is_equivalent_to_mains_inline_postprocessing():
    det = detector.ObjectDetector()
    for seed in range(5):
        out = _synthetic(seed)
        assert det._post(out.copy(), 0.5, 0.0, 140.0, 640, 360) == _main_inline(det, out.copy(), 0.5, 0.0, 140.0, 640, 360)


def test_timing_summary_and_the_log_every_n(tmp_path, monkeypatch):
    rows = [{"prep": 0.002, "gpu": 0.010 + i * 1e-4, "d2h": 0.001, "post": 0.003, "total": 0.016, "dets": i % 2}
            for i in range(60)]
    s = detector.timing_summary(rows)
    assert s["n"] == 60 and s["with_detections"] == 30 and s["gpu"]["p50_ms"] > s["prep"]["p50_ms"]
    monkeypatch.setattr(detector, "TIMING_PATH", str(tmp_path / "t.jsonl"))
    det = detector.ObjectDetector()
    for r in rows[:59]:
        det._note_timing(r)
    assert not (tmp_path / "t.jsonl").exists(), "nothing written before TIMING_EVERY"
    det._note_timing(rows[59])
    line = json.loads((tmp_path / "t.jsonl").read_text().strip())
    assert line["n"] == 60 and "total" in line and det._timing == []


def test_a_broken_log_path_never_breaks_detection(monkeypatch):
    monkeypatch.setattr(detector, "TIMING_PATH", "/proc/forbidden/t.jsonl")
    det = detector.ObjectDetector()
    for _ in range(detector.TIMING_EVERY):
        det._note_timing({"prep": 0.0, "gpu": 0.0, "d2h": 0.0, "post": 0.0, "total": 0.0, "dets": 0})
