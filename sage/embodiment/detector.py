#!/usr/bin/env python3
"""Object detection for Sprout's visual cortex — the organ's first SEMANTIC sense.

YOLO11n (COCO-80) via TensorRT on the Orin GPU. Turns a frame into a list of
{label, conf, box} — so perception can finally say WHAT it sees ("a person, a cup"),
not just "motion to the left". This is the keystone that also gives binocular
correspondence a robust primitive: match *objects* across eyes, not fragile pixels.

Runtime: the prebuilt fp16 engine (~/.sprout/models/yolo11n_fp16.engine). TRT I/O
buffers are torch CUDA tensors (torch-GPU works on this Orin; no pycuda dependency).

Defensive by design: if the engine is missing or TRT/torch are unavailable, detect()
returns [] and the organ degrades gracefully to motion-only perception — vision without
naming, never a crash.
"""
from __future__ import annotations
import json
import os
import time
import numpy as np

# TRACK B BASELINE INSTRUMENT (compiled-transducers arc, explorations/2026-10-06-compiled-transducers-sensors-
# effectors.md): is this organ bound by the TensorRT arithmetic or by the seams around it? Per-detect stage times
# (perf_counter, ~microseconds of overhead), summarised every TIMING_EVERY detections into TIMING_PATH. Measurement
# only: detections are unchanged.
TIMING_PATH = os.path.expanduser(os.getenv("SAGE_DETECTOR_TIMING", "~/.sprout/detector_timing.jsonl"))
TIMING_EVERY = 60
TIMING_STAGES = ("prep", "gpu", "d2h", "post", "total")


def timing_summary(rows: list) -> dict:
    """p50/p95 milliseconds per stage over `rows` ({stage: seconds}), plus counts. Pure, for tests and the log."""
    out = {"n": len(rows)}
    for st in TIMING_STAGES:
        xs = sorted(r[st] * 1000.0 for r in rows if r.get(st) is not None)
        if xs:
            q = lambda p: xs[min(len(xs) - 1, int(p * len(xs)))]
            out[st] = {"p50_ms": round(q(.5), 2), "p95_ms": round(q(.95), 2)}
    out["with_detections"] = sum(1 for r in rows if r.get("dets"))
    return out

def _best_engine() -> str:
    """Pick the engine the POWER BUDGET can sustain. Empirically (2026-07-20, dp at the rig),
    only NANO runs continuously on this board without overcurrent throttling — medium (68 GFLOPs)
    and small (21 GFLOPs) both trip it (the inference power SPIKE, not average draw; a 500ms
    tegrastats sample misses it, so trust the board's throttle notices, not the meter). So nano is
    the default; small/medium are opt-in for bench experiments only. Getting better recognition
    inside this power envelope is open work (lower input res, DLA offload, clock cap, or non-COCO)."""
    base = os.path.expanduser("~/.sprout/models")
    order = ["yolo11n_fp16.engine"]
    if os.environ.get("SPROUT_YOLO_SMALL"):
        order = ["yolo11s_fp16.engine"] + order
    if os.environ.get("SPROUT_YOLO_MEDIUM"):
        order = ["yolo11m_fp16.engine"] + order
    for name in order:
        p = os.path.join(base, name)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return os.path.join(base, "yolo11n_fp16.engine")


ENGINE_PATH = _best_engine()
IMGSZ = 640

COCO = [
    "person","bicycle","car","motorcycle","airplane","bus","train","truck","boat","traffic light",
    "fire hydrant","stop sign","parking meter","bench","bird","cat","dog","horse","sheep","cow",
    "elephant","bear","zebra","giraffe","backpack","umbrella","handbag","tie","suitcase","frisbee",
    "skis","snowboard","sports ball","kite","baseball bat","baseball glove","skateboard","surfboard",
    "tennis racket","bottle","wine glass","cup","fork","knife","spoon","bowl","banana","apple",
    "sandwich","orange","broccoli","carrot","hot dog","pizza","donut","cake","chair","couch",
    "potted plant","bed","dining table","toilet","tv","laptop","mouse","remote","keyboard","cell phone",
    "microwave","oven","toaster","sink","refrigerator","book","clock","vase","scissors","teddy bear",
    "hair drier","toothbrush",
]


def _letterbox(img: np.ndarray, size: int = IMGSZ):
    """Aspect-preserving resize to size×size with gray pad. Returns (chw, scale, padx, pady)."""
    h, w = img.shape[:2]
    s = min(size / h, size / w)
    nh, nw = int(round(h * s)), int(round(w * s))
    import cv2
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas[py:py+nh, px:px+nw] = resized
    rgb = canvas[:, :, ::-1]                      # BGR→RGB
    chw = np.ascontiguousarray(rgb.transpose(2, 0, 1), dtype=np.float32) / 255.0
    return chw, s, px, py


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_th: float) -> list[int]:
    """Greedy class-agnostic NMS (torchvision.ops absent on this box)."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1).clip(0) * (y2 - y1).clip(0)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]; keep.append(int(i))
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]]); yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]]); yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = (xx2 - xx1).clip(0) * (yy2 - yy1).clip(0)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
        order = order[1:][iou <= iou_th]
    return keep


class ObjectDetector:
    def __init__(self, conf: float = 0.50, iou: float = 0.5, max_det: int = 20,
                 engine_path: str = ENGINE_PATH):
        self.conf = conf; self.iou = iou; self.max_det = max_det
        self.engine_path = engine_path
        self._ready = False; self._failed = False
        self._ctx = None; self._in = None; self._out = None
        self._in_name = self._out_name = None; self._stream = None; self._torch = None
        self._timing: list = []

    def _note_timing(self, row: dict) -> None:
        self._timing.append(row)
        if len(self._timing) >= TIMING_EVERY:
            rows, self._timing = self._timing, []
            try:
                os.makedirs(os.path.dirname(TIMING_PATH), exist_ok=True)
                with open(TIMING_PATH, "a") as f:
                    f.write(json.dumps({"ts": round(time.time(), 2), "engine": os.path.basename(self.engine_path),
                                        **timing_summary(rows)}) + "\n")
            except Exception:
                pass      # an instrument never breaks the organ

    def _load(self):
        if self._ready or self._failed:
            return
        try:
            import tensorrt as trt, torch
            if not os.path.exists(self.engine_path):
                raise FileNotFoundError(self.engine_path)
            logger = trt.Logger(trt.Logger.ERROR)
            runtime = trt.Runtime(logger)
            with open(self.engine_path, "rb") as f:
                engine = runtime.deserialize_cuda_engine(f.read())
            self._ctx = engine.create_execution_context()
            for i in range(engine.num_io_tensors):
                name = engine.get_tensor_name(i)
                if engine.get_tensor_mode(name) == trt.TensorIOMode.INPUT:
                    self._in_name = name
                else:
                    self._out_name = name; self._out_shape = tuple(engine.get_tensor_shape(name))
            self._ctx.set_input_shape(self._in_name, (1, 3, IMGSZ, IMGSZ))
            self._in = torch.empty((1, 3, IMGSZ, IMGSZ), dtype=torch.float32, device="cuda")
            self._out = torch.empty(self._out_shape, dtype=torch.float32, device="cuda")
            self._ctx.set_tensor_address(self._in_name, self._in.data_ptr())
            self._ctx.set_tensor_address(self._out_name, self._out.data_ptr())
            self._stream = torch.cuda.Stream()
            self._torch = torch
            self._ready = True
            print(f"[detector] loaded {os.path.basename(self.engine_path)} (conf>={self.conf})", flush=True)
        except Exception as e:
            self._failed = True
            print(f"[detector] disabled (motion-only vision): {type(e).__name__}: {e}", flush=True)

    def detect(self, frame_bgr: np.ndarray) -> list[dict]:
        """Return [{label, conf, box:[x1,y1,x2,y2], cls}] in frame pixel coords. [] if unavailable."""
        self._load()
        if not self._ready:
            return []
        torch = self._torch
        H, W = frame_bgr.shape[:2]
        t0 = time.perf_counter()
        chw, s, px, py = _letterbox(frame_bgr, IMGSZ)
        t1 = time.perf_counter()
        try:
            self._in.copy_(torch.from_numpy(chw).unsqueeze(0))
            self._ctx.execute_async_v3(self._stream.cuda_stream)
            self._stream.synchronize()
            t2 = time.perf_counter()
            out = self._out.cpu().numpy()[0]                     # [84, 8400]
            t3 = time.perf_counter()
        except Exception as e:
            print(f"[detector] inference error: {type(e).__name__}: {e}", flush=True)
            return []
        dets = self._post(out, s, px, py, W, H)
        t4 = time.perf_counter()
        self._note_timing({"prep": t1 - t0, "gpu": t2 - t1, "d2h": t3 - t2, "post": t4 - t3,
                           "total": t4 - t0, "dets": len(dets)})
        return dets

    def _post(self, out, s, px, py, W, H) -> list[dict]:
        """Raw engine output -> detections in frame pixel coords (moved out of detect() unchanged, to time it)."""
        out = out.T                                              # [8400, 84]
        cls_scores = out[:, 4:]
        cls = cls_scores.argmax(1); conf = cls_scores[np.arange(len(cls)), cls]
        m = conf >= self.conf
        if not m.any():
            return []
        xywh = out[m, :4]; conf = conf[m]; cls = cls[m]
        # xywh (letterboxed 640 space) → xyxy → undo letterbox → frame coords
        cx, cy, bw, bh = xywh[:, 0], xywh[:, 1], xywh[:, 2], xywh[:, 3]
        x1 = (cx - bw / 2 - px) / s; y1 = (cy - bh / 2 - py) / s
        x2 = (cx + bw / 2 - px) / s; y2 = (cy + bh / 2 - py) / s
        boxes = np.stack([x1, y1, x2, y2], 1)
        keep = _nms(boxes, conf, self.iou)[: self.max_det]
        dets = []
        for i in keep:
            bx = boxes[i]
            dets.append({
                "label": COCO[int(cls[i])] if int(cls[i]) < len(COCO) else str(int(cls[i])),
                "conf": round(float(conf[i]), 3),
                "box": [int(np.clip(bx[0], 0, W)), int(np.clip(bx[1], 0, H)),
                        int(np.clip(bx[2], 0, W)), int(np.clip(bx[3], 0, H))],
                "cls": int(cls[i]),
            })
        return dets


if __name__ == "__main__":
    import sys, cv2, time
    det = ObjectDetector()
    path = sys.argv[1] if len(sys.argv) > 1 else None
    img = cv2.imread(path) if path else np.random.randint(0, 255, (360, 640, 3), np.uint8)
    t = time.time(); d = det.detect(img); dt = (time.time() - t) * 1000
    print(f"{len(d)} detections in {dt:.0f}ms:", d[:10])
