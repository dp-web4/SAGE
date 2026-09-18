#!/usr/bin/env python3
"""Sprout's visual cortex — dual IMX219 → a compact, word-shaped PERCEPTUAL STATE.

The pixels→words organ (embodied-raising plan P1). Symbolic-first: no VLM, no VAE
checkpoint. Turns each camera's frame into (motion, attention ROI, vision-trust) and
the pair into a short natural-language scene descriptor the 0.8B can reason about.

Faithful to the surveyed early-vision mechanisms:
  - capture: nvarguscamerasrc → nvvidconv → BGR → appsink (proven 30fps dual)
  - attention: Gen-2 "gravity" — 8×8 tile motion field (75th-pct + sigmoid), a fixed
    focus window that leaky-integrates toward the peak-motion tile, homing to center.
  - vision trust: compact frame-quality (sharpness + exposure + contrast).

Writes the perceptual state as JSON (atomic) at ~POLL_HZ; optional overlay display.
Run:  ~/arc-venv/bin/python -m sage.embodiment.visual_cortex --display
"""
from __future__ import annotations
import cv2, numpy as np, time, json, os, threading, argparse, tempfile
from sage.embodiment.proprioception import Proprioception
from sage.embodiment.salience import SalienceFilter
from sage.embodiment.audio import Hearing
from sage.embodiment.detector import ObjectDetector

STATE_PATH = os.path.expanduser("~/.sprout/perception.json")
GAZE_PATH = os.path.expanduser("~/.sprout/gaze.json")   # the self's attention stance: {"mode": open|avert|dwell|closed, "target": [cx,cy]}
GAZE_PARSER = "gaze-v1"   # the interpreting-role version (PR #27): witnessed so a later parser's disagreement supersedes, never rewrites, what the runtime decided
DISPARITY_PATH = os.path.expanduser("~/.sprout/disparity_field.json")   # measured eye0→eye1 misalignment field (instrument)
POLL_HZ = 4.0            # perceptual-state emit rate
GRID = 8                 # 8×8 attention tiles
FOCUS_W, FOCUS_H = 4, 3  # focus window size in tiles
GRAVITY = 0.6            # leaky-integrate approach rate
MOTION_TH = 0.12         # tile motion gate (post-sigmoid)
MOTION_NOISE_FLOOR = 0.035  # per-tile diff (frac of 255) at/below which it's sensor noise, not motion — deadband
STALL_EPS = 0.3          # mean raw frame-diff below this = frame unchanged (a live sensor has noise > this)
STALL_CYCLES = 8         # this many unchanged cycles in a row (~2s at 4Hz) = the eye has stalled/gone blind
RECOVER_CYCLES = 60      # frozen this long (~15s) → self-heal: reopen the camera's Argus consumer (a live sensor never stays frozen this long)
RECOVER_COOLDOWN_S = 30  # min seconds between reopen attempts per eye (covers warmup, avoids thrash)
DET_PERIOD = 1.0         # object detection cadence (1Hz) — objects don't change fast, and fewer GPU
                         # inference spikes eases the Orin's power/thermal budget (overcurrent throttle)


class ObjectStabilizer:
    """Perceptual hysteresis for objects — don't blurt every fleeting phantom. A COCO model
    on an atypical/close scene flickers false positives (a waving hand → a momentary
    'elephant'); a single noisy frame shouldn't reach perception. A label must appear in
    >=CONFIRM of the last WINDOW detections before it's believed, and it lingers a beat after
    it's gone (so a briefly-occluded object doesn't blink out). Same ethos as salience: filter
    the stream, report what's persistently there."""
    WINDOW = 6      # detections remembered (~2.4s at the 2.5Hz detection cadence)
    CONFIRM = 3     # must be seen in this many of them to be believed

    def __init__(self):
        from collections import deque
        self.hist = deque(maxlen=self.WINDOW)

    def update(self, dets: list) -> list:
        cur: dict = {}
        for d in dets:                       # best instance per label this detection
            if d["label"] not in cur or d["conf"] > cur[d["label"]]["conf"]:
                cur[d["label"]] = d
        self.hist.append(cur)
        counts: dict = {}
        for frame in self.hist:
            for lab in frame:
                counts[lab] = counts.get(lab, 0) + 1
        out = []
        for lab, n in counts.items():
            if n >= self.CONFIRM:
                for frame in reversed(self.hist):   # most recent box/conf for a confirmed label
                    if lab in frame:
                        out.append(frame[lab]); break
        return sorted(out, key=lambda o: -o["conf"])


def binocular_object_agreement(objs0: list, objs1: list):
    """Semantic cross-eye correspondence: a thing is 'confirmed in the shared field' when BOTH
    eyes NAME it. This matches meaning, not appearance, so it is robust to the focus/misalignment/
    perspective that defeats pixel template-matching (measured: raw CCOEFF ~0.35 between these eyes).
    Jaccard over the confirmed object labels. Returns (agreement, shared_labels), or (None, …)
    when a semantic comparison isn't possible — caller then falls back to the pixel-based agreement.

    Crucially, this requires BOTH eyes to see objects. If only one eye does (these cameras are
    divergent — an object often lands in one FOV, not the shared overlap), that's monocular/FOV-
    limited sight, NOT disagreement; returning None (→ pixel fallback) avoids wrongly tanking
    coherence. Genuine disagreement (both eyes see objects, none shared) still reads as 0.0."""
    l0 = {o["label"] for o in objs0}
    l1 = {o["label"] for o in objs1}
    if not l0 or not l1:                      # need BOTH eyes to compare; else fall back to pixels
        return None, sorted(l0 & l1)
    union = l0 | l1
    return (len(l0 & l1) / len(union) if union else 0.0), sorted(l0 & l1)


def _object_phrase(objects_by_eye: list) -> str:
    """A short 'I see …' clause from the union of objects across both eyes (best conf each).
    Turns 'motion to the left' into 'I see a person. motion to the left' — the semantic upgrade."""
    best: dict[str, float] = {}
    for objs in objects_by_eye:
        for o in objs:
            if o["conf"] > best.get(o["label"], 0):
                best[o["label"]] = o["conf"]
    if not best:
        return ""
    labels = sorted(best, key=lambda k: -best[k])[:4]
    if len(labels) == 1:
        items = labels[0]
    elif len(labels) == 2:
        items = f"{labels[0]} and {labels[1]}"
    else:
        items = ", ".join(labels[:-1]) + f", and {labels[-1]}"
    return f"I see a {items}. "


def gst_pipeline(sid: int, w: int = 640, h: int = 360) -> str:
    return (f"nvarguscamerasrc sensor-id={sid} ! "
            f"video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1 ! "
            f"nvvidconv ! video/x-raw,width={w},height={h},format=BGRx ! "
            f"videoconvert ! video/x-raw,format=BGR ! appsink drop=true max-buffers=1 sync=false")


class Camera(threading.Thread):
    """Threaded latest-frame grabber for one CSI camera."""
    def __init__(self, sid: int):
        super().__init__(daemon=True)
        self.sid = sid
        self.cap = cv2.VideoCapture(gst_pipeline(sid), cv2.CAP_GSTREAMER)
        self.frame = None
        self.ok = self.cap.isOpened()
        self.running = True

    def run(self):
        while self.running and self.ok:
            r, f = self.cap.read()
            if r and f is not None:
                self.frame = f
            else:
                time.sleep(0.005)

    def stop(self):
        self.running = False
        time.sleep(0.05)
        self.cap.release()


def vision_trust(gray: np.ndarray) -> float:
    """Compact frame-quality trust in [0,1]: sharpness + exposure + contrast.
    (A distilled camera_trust_score; enrich with edges/noise/stereo later.)"""
    sharp = min(1.0, cv2.Laplacian(gray, cv2.CV_64F).var() / 300.0)     # focus energy
    contrast = min(1.0, gray.std() / 60.0)                              # dynamic range
    clip = (np.mean(gray < 8) + np.mean(gray > 247))                    # under/over-exposed frac
    exposure = max(0.0, 1.0 - clip / 0.30)                             # punish >30% clipped
    return float(np.clip(0.5 * sharp + 0.2 * contrast + 0.3 * exposure, 0, 1))


def motion_field(prev_gray: np.ndarray, gray: np.ndarray) -> np.ndarray:
    """8×8 tile motion scores (0..1): 75th-pct per tile, sigmoid-amplified, with a sensor-noise
    deadband. A flat static scene still has camera read/thermal noise; without a floor the sigmoid
    maps even a zero-diff tile to 0.269, and motion = max-over-64-tiles then reads noise as 'strong
    motion'. The deadband rejects sub-noise diffs, and we subtract the sigmoid's zero-point so a
    genuinely still tile scores 0 — real motion (diffs well above noise) still saturates high."""
    m = cv2.GaussianBlur(cv2.absdiff(prev_gray, gray), (5, 5), 0).astype(np.float32)
    # A flat/low-texture scene makes the camera's auto-exposure/gain HUNT — the whole frame's
    # brightness oscillates, producing large frame diffs everywhere that are illumination, not motion.
    # The frame-wide median is that pervasive baseline (a moving object is a minority of the frame,
    # so it doesn't move the median); only a tile's LOCAL EXCESS over it counts as real motion.
    baseline = float(np.median(m))
    h, w = gray.shape
    th, tw = h // GRID, w // GRID
    scores = np.zeros((GRID, GRID), np.float32)
    zero = 1.0 / (1.0 + np.exp(1.0))   # sigmoid value at s'=0 (the 0.269 floor) — subtracted off
    for ty in range(GRID):
        for tx in range(GRID):
            tile = m[ty*th:(ty+1)*th, tx*tw:(tx+1)*tw]
            excess = (float(np.percentile(tile, 75)) - baseline) / 255.0   # local change beyond global
            s = max(0.0, excess - MOTION_NOISE_FLOOR)                       # deadband above baseline
            raw = 1.0 / (1.0 + np.exp(-10.0 * (s - 0.1)))
            scores[ty, tx] = max(0.0, (raw - zero) / (1.0 - zero))          # remove floor, rescale
    return scores


class GravityFocus:
    """Single focus window that gravitates toward the peak-motion tile."""
    def __init__(self):
        self.fx = (GRID - FOCUS_W) / 2.0
        self.fy = (GRID - FOCUS_H) / 2.0

    def update(self, scores: np.ndarray, gaze: str = "open", target=None):
        """Attention is a CHOICE, not a reflex. Salience (peak motion) proposes; the
        gaze stance disposes. 'open' follows the pull; 'avert' looks away from it;
        'dwell' holds a chosen focus and resists the pull."""
        peak = float(scores.max())
        my, mx = np.unravel_index(int(scores.argmax()), scores.shape)
        if gaze == "dwell" and target is not None:
            tx = np.clip(target[0] * GRID - FOCUS_W / 2, 0, GRID - FOCUS_W)
            ty = np.clip(target[1] * GRID - FOCUS_H / 2, 0, GRID - FOCUS_H)
            rate = GRAVITY
        elif gaze == "avert" and peak > MOTION_TH:
            # deliberately look AWAY from the loudest pull — the mirror tile
            tx = np.clip((GRID - 1 - mx) - FOCUS_W // 2, 0, GRID - FOCUS_W)
            ty = np.clip((GRID - 1 - my) - FOCUS_H // 2, 0, GRID - FOCUS_H)
            rate = GRAVITY
        elif gaze == "open" and peak > MOTION_TH:
            tx = np.clip(mx - FOCUS_W // 2, 0, GRID - FOCUS_W)
            ty = np.clip(my - FOCUS_H // 2, 0, GRID - FOCUS_H)
            rate = GRAVITY
        else:  # no pull, or a stance with nothing to act on → ease to center
            tx = (GRID - FOCUS_W) / 2.0
            ty = (GRID - FOCUS_H) / 2.0
            rate = 0.1
        self.fx += rate * (tx - self.fx)
        self.fy += rate * (ty - self.fy)
        return peak

    def roi(self) -> dict:  # normalized 0..1 rectangle
        return {"cx": round((self.fx + FOCUS_W/2) / GRID, 3),
                "cy": round((self.fy + FOCUS_H/2) / GRID, 3),
                "w": round(FOCUS_W / GRID, 3), "h": round(FOCUS_H / GRID, 3)}


class BinocularCorrelator:
    """Two-eyes-together despite MECHANICAL MISALIGNMENT (the cameras aren't a calibrated
    stereo rig — they point a little differently and may differ in focus). Matches eye-0's
    attention patch *anywhere* in eye-1 (2D, misalignment-tolerant).

    `agreement` (robust) = did both eyes confirm the same feature → it's a real thing in the
    shared field, not sensor noise. Depth is deliberately humble: we auto-calibrate the
    cameras' fixed resting offset from confident matches, then treat *deviation* from it as
    parallax — a distinct object 'standing out in depth' from the background. No metric
    distance and no near/far direction is claimed (that needs calibration we don't have)."""
    S = 0.5   # match at half-res for speed
    PS = 48   # patch size (downscaled px)

    def __init__(self):
        self.base = None  # learned fixed misalignment [dx, dy], downscaled px

    def correlate(self, gray0: np.ndarray, gray1: np.ndarray, roi0: dict) -> dict:
        g0 = cv2.resize(gray0, None, fx=self.S, fy=self.S)
        g1 = cv2.resize(gray1, None, fx=self.S, fy=self.S)
        h, w = g0.shape
        cx, cy = roi0["cx"] * w, roi0["cy"] * h
        x0 = int(np.clip(cx - self.PS//2, 0, w - self.PS)); y0 = int(np.clip(cy - self.PS//2, 0, h - self.PS))
        patch = g0[y0:y0+self.PS, x0:x0+self.PS]
        if patch.shape[0] < self.PS or patch.shape[1] < self.PS:
            return {"agreement": 0.0, "depth": "unknown", "offset": [0, 0]}
        res = cv2.matchTemplate(g1, patch, cv2.TM_CCOEFF_NORMED)
        _, maxval, _, maxloc = cv2.minMaxLoc(res)
        agreement = float(max(0.0, maxval))
        dx, dy = maxloc[0] - x0, maxloc[1] - y0
        out = {"agreement": round(agreement, 3), "offset": [int(dx/self.S), int(dy/self.S)], "depth": "unknown"}
        if agreement >= 0.5:  # confident correspondence → learn the resting misalignment
            if self.base is None:
                self.base = [float(dx), float(dy)]
            else:
                self.base = [0.9*self.base[0] + 0.1*dx, 0.9*self.base[1] + 0.1*dy]
            parallax = abs(dx - self.base[0]) + abs(dy - self.base[1])
            out["parallax"] = round(parallax / self.S, 1)
            out["depth"] = "standout" if parallax > 12 else "background"
        return out


class DisparityField:
    """MEASUREMENT INSTRUMENT (non-forcing) — learns the spatially-varying eye0→eye1
    displacement across the whole frame, so the actual mechanical misalignment can be SEEN:
    a constant translation, an affine gradient (roll/scale), or projective (perspective)?

    Samples confident whole-frame patch matches on a coarse grid (round-robin to bound cost),
    accumulates a per-cell EMA displacement + confidence, and fits constant-vs-affine models to
    report which the misalignment actually needs. Changes NO perception behavior — it only watches,
    so step 2 (perspective-aware correlation) can be built on measured geometry, not assumption."""
    COLS, ROWS = 6, 4
    RS = 0.35             # coarse match scale
    PS = 30               # patch size at coarse scale
    SEARCH = 0.32         # local search half-window, fraction of frame dim
    BLUR = 3.0            # Gaussian σ (full-res): match LOW-FREQ structure. The eyes differ in
                          # focus, so fine detail doesn't correlate (raw CCOEFF ~0.35) but blurred
                          # structure does (~0.67, measured 2026-07-19). Focus-robust matching.
    MIN_STD = 6.0         # skip flat patches (post-blur; they match anywhere → meaningless disparity)
    MIN_CONF = 0.5        # keep only confident matches
    CELLS_PER_FRAME = 4   # round-robin subset per frame → bounded cost on the Jetson
    EMA = 0.15

    def __init__(self):
        self.dx = np.full((self.ROWS, self.COLS), np.nan)
        self.dy = np.full((self.ROWS, self.COLS), np.nan)
        self.conf = np.zeros((self.ROWS, self.COLS))
        self.samples = np.zeros((self.ROWS, self.COLS), dtype=int)
        self._rr = 0

    def update(self, gray0: np.ndarray, gray1: np.ndarray):
        # Match on low-frequency structure (focus-robust): blur, then coarsen.
        b0 = cv2.GaussianBlur(gray0, (0, 0), self.BLUR)
        b1 = cv2.GaussianBlur(gray1, (0, 0), self.BLUR)
        g0 = cv2.resize(b0, None, fx=self.RS, fy=self.RS)
        g1 = cv2.resize(b1, None, fx=self.RS, fy=self.RS)
        h, w = g0.shape
        ps = self.PS
        if h < ps or w < ps:
            return
        sw = int(self.SEARCH * w); sh = int(self.SEARCH * h)
        total = self.ROWS * self.COLS
        for _ in range(self.CELLS_PER_FRAME):
            idx = self._rr % total; self._rr += 1
            r, c = divmod(idx, self.COLS)
            cx = int((c + 0.5) / self.COLS * w); cy = int((r + 0.5) / self.ROWS * h)
            x0 = int(np.clip(cx - ps // 2, 0, w - ps)); y0 = int(np.clip(cy - ps // 2, 0, h - ps))
            patch = g0[y0:y0+ps, x0:x0+ps]
            if patch.shape[0] < ps or patch.shape[1] < ps or patch.std() < self.MIN_STD:
                continue
            rx0 = int(np.clip(x0 - sw, 0, w - ps)); ry0 = int(np.clip(y0 - sh, 0, h - ps))
            rx1 = int(np.clip(x0 + ps + sw, ps, w)); ry1 = int(np.clip(y0 + ps + sh, ps, h))
            region = g1[ry0:ry1, rx0:rx1]
            if region.shape[0] < ps or region.shape[1] < ps:
                continue
            res = cv2.matchTemplate(region, patch, cv2.TM_CCOEFF_NORMED)
            _, maxval, _, maxloc = cv2.minMaxLoc(res)
            if maxval < self.MIN_CONF:
                continue
            mx = rx0 + maxloc[0]; my = ry0 + maxloc[1]
            dxf = (mx - x0) / self.RS; dyf = (my - y0) / self.RS   # displacement in full-res px
            a = self.EMA
            if np.isnan(self.dx[r, c]):
                self.dx[r, c], self.dy[r, c] = dxf, dyf
            else:
                self.dx[r, c] = (1 - a) * self.dx[r, c] + a * dxf
                self.dy[r, c] = (1 - a) * self.dy[r, c] + a * dyf
            self.conf[r, c] = (1 - a) * self.conf[r, c] + a * maxval
            self.samples[r, c] += 1

    def summary(self) -> dict:
        """Diagnose the misalignment model. constant residual small → translation suffices;
        affine reducing residual a lot → a real gradient (roll/scale/perspective) is present."""
        mask = (~np.isnan(self.dx)) & (self.samples >= 3)
        n = int(mask.sum())
        if n < 6:
            return {"cells": n, "status": "accumulating"}
        rr, cc = np.where(mask)
        xs = (cc + 0.5) / self.COLS; ys = (rr + 0.5) / self.ROWS
        dx = self.dx[mask]; dy = self.dy[mask]
        cx, cy = float(dx.mean()), float(dy.mean())
        res_const = float(np.sqrt(((dx - cx) ** 2 + (dy - cy) ** 2).mean()))
        A = np.column_stack([xs, ys, np.ones_like(xs)])
        coef_x = np.linalg.lstsq(A, dx, rcond=None)[0]
        coef_y = np.linalg.lstsq(A, dy, rcond=None)[0]
        res_aff = float(np.sqrt(((dx - A @ coef_x) ** 2 + (dy - A @ coef_y) ** 2).mean()))
        spread = float(np.sqrt(dx.var() + dy.var()))
        verdict = ("translation" if res_const < 3.0 else
                   "affine (gradient present)" if (res_const - res_aff) > 2.0 else
                   "translation-ish (noisy)")
        return {"cells": n, "mean_offset_px": [round(cx, 1), round(cy, 1)],
                "spread_px": round(spread, 1), "resid_constant_px": round(res_const, 1),
                "resid_affine_px": round(res_aff, 1), "affine_gain_px": round(res_const - res_aff, 1),
                "verdict": verdict}

    def snapshot(self) -> dict:
        return {"cols": self.COLS, "rows": self.ROWS,
                "dx": [[None if np.isnan(v) else round(float(v), 1) for v in row] for row in self.dx],
                "dy": [[None if np.isnan(v) else round(float(v), 1) for v in row] for row in self.dy],
                "conf": [[round(float(v), 2) for v in row] for row in self.conf],
                "samples": self.samples.tolist(), "summary": self.summary()}


def _dir_word(cx: float, cy: float) -> str:
    h = "left" if cx < 0.38 else "right" if cx > 0.62 else "center"
    v = "upper" if cy < 0.38 else "lower" if cy > 0.62 else ""
    return (f"{v} {h}").strip() if h != "center" or v else "center"


def describe(eyes: list[dict], binoc: dict, prop: dict, gaze: str = "open", aud: dict = None,
             meta: dict = None) -> str:
    """Deterministic symbolic scene descriptor from the two eyes, their correlation,
    proprioception (reafference), the chosen gaze stance (volition), and hearing (cross-modal)."""
    mot = max(e["motion"] for e in eyes)
    trust = max(e["trust"] for e in eyes)  # the view is usable if the BEST eye is good; a stale/dark eye is named separately
    if mot < 0.15:
        motion_clause = "the scene is still"
    else:
        strong = max(eyes, key=lambda e: e["motion"])
        level = "strong" if mot > 0.5 else "gentle" if mot < 0.3 else "clear"
        dirw = _dir_word(strong["attention"]["cx"], strong["attention"]["cy"])
        both = eyes[0]["motion"] > 0.15 and eyes[1]["motion"] > 0.15
        confirmed = both and binoc.get("agreement", 0) > 0.45  # both eyes see a correlated feature
        if confirmed:
            standout = " and standing out from the background" if binoc.get("depth") == "standout" else ""
            motion_clause = f"{level} motion to the {dirw}, both eyes on it{standout}"
        elif both:
            motion_clause = f"{level} motion to the {dirw}, both eyes (uncorrelated)"
        else:
            motion_clause = f"{level} motion to the {dirw} (one eye only)"
    # reafference: attribute the motion to me or to the world
    sm = prop.get("self_motion", "unknown")
    if mot >= 0.15 and sm == "still":
        self_clause = "; I'm still, so this is the world moving"
    elif mot >= 0.15 and sm in ("moving", "rotating"):
        self_clause = f"; but I'm {sm}, so some of it is my own motion"
    elif sm in ("moving", "rotating"):
        self_clause = f"; I'm {sm}"
    else:
        self_clause = ""
    view = "clear view" if trust > 0.6 else "murky view" if trust > 0.3 else "almost no view (dark or blurred)"
    stance = {"avert": "choosing to look away — ", "dwell": "holding my gaze — "}.get(gaze, "")
    dark = [("left" if i == 0 else "right") for i, e in enumerate(eyes) if e.get("stalled")]
    stale = [("left" if i == 0 else "right") for i, e in enumerate(eyes) if e.get("frozen") and not e.get("stalled")]
    if dark:
        prefix = f"my {' and '.join(f'{s} eye' for s in dark)} has gone dark (no fresh frames); "
    elif stale:
        prefix = f"my {' and '.join(f'{s} eye' for s in stale)} isn't refreshing (stale — can't confirm it's live); "
    else:
        prefix = ""
    # hearing — cross-modal binding: a sound + a motion together is one real event; a sound with
    # nothing seen is heard-not-seen; a loud room is its own note.
    hearing_clause = ""
    heard = ambient = False
    if aud and aud.get("ok"):
        if aud.get("onset") and mot >= 0.15:
            hearing_clause = " — and I heard it too"
            heard = True
        elif aud.get("onset"):
            hearing_clause = " — I heard a sound, though nothing I see moved"
            heard = True
        elif aud.get("level", 0) > 0.15:
            hearing_clause = " — a noisy space"
            ambient = True
    # modality ground truth, computed from the SAME conditions that composed the
    # sentence — so downstream consumers (liveness binding) never have to guess
    # modality from descriptor text (which was a declared stopgap, 2026-07-30).
    if meta is not None:
        m = ["vision"]
        if heard or ambient:
            m.append("audio")
        meta["modalities"] = m
        meta["audio_onset"] = heard
    return f"{prefix}{stance}{motion_clause}{self_clause}{hearing_clause}; {view}"


JOURNAL_PATH = os.path.expanduser("~/.sprout/perception_journal.jsonl")
JOURNAL_MAX = 2000  # keep last N events


class Journal:
    """Logs the SALIENT fraction of the stream (habituation-filtered), not every frame —
    so the raising loop reflects on signal, not noise. Each entry carries its SNARC
    breakdown. A cooldown prevents a single salient burst from flooding the log; a slow
    heartbeat marks that the senses were open even through the quiet stretches."""
    HEARTBEAT_S = 900
    COOLDOWN_S = 8

    def __init__(self):
        self.last_log = 0.0
        self._since_trim = 0

    def observe(self, s: dict, sal: dict):
        now = s["ts"]; ev = None
        if sal.get("salient") and now - self.last_log >= self.COOLDOWN_S:
            ev = {"kind": "salient", "salience": sal["salience"],
                  "snarc": {k: sal[k] for k in ("surprise", "novelty", "arousal", "conflict")}}
        elif now - self.last_log > self.HEARTBEAT_S:
            ev = {"kind": "heartbeat", "salience": sal.get("salience", 0.0)}
        if ev is not None:
            ev.update({"ts": now, "descriptor": s["descriptor"]})
            if "modalities" in s:  # ground-truth modality tags (2026-07-31)
                ev["modalities"] = s["modalities"]
            self._append(ev); self.last_log = now

    def _append(self, ev: dict):
        os.makedirs(os.path.dirname(JOURNAL_PATH), exist_ok=True)
        with open(JOURNAL_PATH, "a") as f:
            f.write(json.dumps(ev) + "\n")
        self._since_trim += 1
        if self._since_trim >= 200:  # trim to last JOURNAL_MAX
            self._since_trim = 0
            try:
                lines = open(JOURNAL_PATH).read().splitlines()
                if len(lines) > JOURNAL_MAX:
                    with open(JOURNAL_PATH, "w") as f:
                        f.write("\n".join(lines[-JOURNAL_MAX:]) + "\n")
            except Exception:
                pass


class VisualCortex:
    def __init__(self, display: bool = False):
        self.cams = [Camera(0), Camera(1)]
        self.focus = [GravityFocus(), GravityFocus()]
        self.prev = [None, None]
        self._stall = [0, 0]  # consecutive unchanged-frame counts, per eye
        self._last_recover = [0.0, 0.0]  # last self-heal timestamp, per eye
        self.binoc = BinocularCorrelator()
        self.dfield = DisparityField()   # measurement instrument (non-forcing): the eyes' misalignment field
        self._dfield_ts = 0.0
        self._motion_hist: list = [[], []]  # per-eye recent motion, for median smoothing (spike reject)
        self.detector = ObjectDetector()   # semantic vision: WHAT it sees (YOLO11n/COCO via TensorRT)
        self._det_ts = 0.0
        self._objects: list = [[], []]     # last-detected objects, per eye (stabilized)
        self._stab = [ObjectStabilizer(), ObjectStabilizer()]  # temporal hysteresis, per eye
        self.prop = Proprioception()
        self.hearing = Hearing()
        self.salience = SalienceFilter()
        self.journal = Journal()
        self.display = display
        self._gaze_ts = 0.0
        self._gaze_mode = "open"
        self._gaze_target = None
        self._last_gaze = "open"

    def _read_gaze(self):
        """The self's chosen attention stance (re-read every ~2s). Default 'open'."""
        now = time.time()
        if now - self._gaze_ts < 2.0:
            return self._gaze_mode, self._gaze_target
        self._gaze_ts = now
        try:
            g = json.load(open(GAZE_PATH))
            self._gaze_mode = g.get("mode", "open")
            self._gaze_target = g.get("target")
            self._gaze_raw = g            # the being's raw utterance (author), witnessed as specimen
        except Exception:
            self._gaze_mode, self._gaze_target = "open", None
            self._gaze_raw = None         # no source read → default stance, recorded as such
        return self._gaze_mode, self._gaze_target

    def _note_choice(self, gaze: str, target=None):
        """A change of gaze stance is a self-authored act — witnessed durably (PR #27).

        This does not import society machinery; it recognizes the accountability
        SHAPE already present in the being's own gaze mechanics (PRD_SAGE_WEB4_
        CITIZENSHIP §1.2, self-similar not mimicked):
          author    = the being (wrote GAZE_PATH — `raw`)
          role      = the parser that interpreted it (`parser`, versioned)
          authority = self-governance (a being governs its own senses); `effect`
                      records that the interpreted stance actually drove this tick
          witness   = this append-only journal `choice` record
        `raw` + `parser` are the SPECIMEN: a later parser may reinterpret the raw
        utterance, but must SUPERSEDE (a new record), never rewrite this one.
        """
        if gaze != self._last_gaze:
            phrase = {"closed": "chose to close my eyes and rest",
                      "avert": "chose to look away from the motion",
                      "dwell": "chose to hold my gaze, resisting the pull",
                      "open": "opened my eyes to the world again"}.get(gaze, f"chose gaze: {gaze}")
            self.journal._append({
                "kind": "choice", "salience": 1.0, "ts": round(time.time(), 2),
                "descriptor": phrase,                      # the being's own voice
                "gaze_choice": {                            # the structured witness
                    "raw": self._gaze_raw,                  # author: the being's utterance (or null = default)
                    "raw_source": GAZE_PATH,
                    "parser": GAZE_PARSER,                  # interpreting role, versioned
                    "stance": gaze, "target": target,       # contemporaneous interpreted act
                    "effect": "applied",                    # it drove the perception loop this tick
                    "authority": "self-governance:senses",  # a being governs its own senses
                    "from_stance": self._last_gaze,         # the transition, for audit
                },
            })
            self._last_gaze = gaze

    def start(self):
        for c in self.cams:
            if not c.ok:
                raise RuntimeError(f"camera {c.sid} failed to open")
            c.start()
        self.prop.start()  # inner ear (fails open if no IMU)
        self.hearing.start()  # ear (fails open if no mic)
        time.sleep(1.0)  # warm up (auto-exposure)

    def _perceive_one(self, i: int, frame, gaze="open", target=None) -> dict:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        motion = 0.0; frozen = False
        if self.prev[i] is not None:
            # "frozen-looking": byte-identical frames (raw diff ~0). A live sensor always
            # carries noise above STALL_EPS. This alone does NOT mean stalled — a genuinely
            # still world looks the same. _adjudicate_sensors decides still vs stalled.
            rawdiff = float(cv2.absdiff(self.prev[i], gray).mean())
            self._stall[i] = self._stall[i] + 1 if rawdiff < STALL_EPS else 0
            frozen = self._stall[i] >= STALL_CYCLES
            scores = motion_field(self.prev[i], gray)
            motion = float(self.focus[i].update(scores, gaze, target))
            # median-of-3 smoothing: a lone spike (an auto-exposure step on a flat scene) isn't
            # motion; real motion persists across frames. Suppresses transient false motion.
            h = self._motion_hist[i]; h.append(motion); del h[:-3]
            motion = float(np.median(h))
        self.prev[i] = gray
        if frozen:
            motion = 0.0  # frozen frame → no real motion, whether the scene is still OR the eye is dead
        return {"motion": round(motion, 3), "attention": self.focus[i].roi(),
                "trust": round(vision_trust(gray), 3), "frozen": frozen, "stalled": False}, gray

    def _adjudicate_sensors(self, eyes: list, binoc: dict, prop: dict):
        """Still vs stalled is genuinely ambiguous without effectors to act and check for
        predicted change. Disambiguate with what Sprout does have: ego-motion (a live eye
        MUST change when the head is moved) and cross-eye agreement (a real still scene
        keeps both eyes mutually consistent). Only zero trust with corroboration; a
        frozen-but-consistent view is trusted as a genuinely still world."""
        moved = prop.get("self_motion") in ("moving", "rotating")
        agree = binoc.get("agreement", 0.0)
        for i, e in enumerate(eyes):
            if not e.get("frozen"):
                continue
            if moved or agree < 0.4:
                # the head moved yet this eye didn't change, OR its view no longer matches the
                # other eye — evidence it is not seeing a live, shared scene.
                e["stalled"] = True
                e["trust"] = 0.0
                e["sensor"] = "stalled"
            else:
                # Rig still and the eyes still agree → can't confirm it's dead. But the frame is
                # STALE: it carries no information about the *present*, so trust reflects liveness,
                # not just image quality. It decays from the sharp-but-stale image toward a low
                # floor the longer the eye fails to refresh — never zero (the world may be still),
                # never full (we can't trust a frame that isn't updating).
                stale = max(0, self._stall[i] - STALL_CYCLES)
                e["trust"] = round(e["trust"] * max(0.1, 0.5 * (0.85 ** stale)), 3)
                e["sensor"] = "stale-unverified"

    def _recover_camera(self, i: int):
        """Self-heal a stalled eye. Verified (Test A, 2026-07-09): the stuck state lives in the
        camera's per-process Argus consumer session — a fresh consumer clears it, no nvargus
        restart needed. So tear down this one camera and reopen it, leaving the other eye alone."""
        side = "left" if i == 0 else "right"
        try:
            self.cams[i].stop()  # release the stuck consumer
        except Exception:
            pass
        time.sleep(0.3)
        cam = Camera(i)  # fresh Argus consumer session
        self._last_recover[i] = time.time()
        if not cam.ok:
            return  # reopen failed; cooldown before the next attempt
        cam.start()
        self.cams[i] = cam
        self._stall[i] = 0
        self.prev[i] = None
        self.journal._append({"kind": "self_heal", "salience": 1.0, "ts": round(time.time(), 2),
                              "descriptor": f"my {side} eye stalled — I reopened it"})

    def _emit(self, state: dict):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATE_PATH))
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_PATH)  # atomic

    def _sense_blind(self, blind: list, frames: list, gaze: str, target):
        """One perceptual tick while at least one eye delivers nothing.

        Emits the same state SHAPE with the dark eyes marked stalled, so every consumer
        downstream (the salience filter, the descriptor, presence, the daemon) sees a being
        that has lost an eye rather than a being that has stopped perceiving. Then runs the
        self-heal, which is the whole point: an eye this dead is exactly the one that needs
        reopening, and the old early-return meant it never was.
        """
        now = time.time()
        eyes = []
        for i, f in enumerate(frames):
            if f is None:
                # count it as stalled so RECOVER_CYCLES can mature and the self-heal fire
                self._stall[i] += 1
                eyes.append({"motion": 0.0,
                             "attention": {"cx": 0.5, "cy": 0.5, "w": 0.5, "h": 0.375},
                             "trust": 0.0, "frozen": True, "stalled": True,
                             "sensor": "no-frames", "objects": []})
            else:
                e, _gray = self._perceive_one(i, f, gaze, target)
                e["objects"] = self._objects[i]
                eyes.append(e)
        prop = self.prop.state()
        aud = self.hearing.state()
        binoc = {"agreement": 0.0, "offset": [0, 0], "depth": "unknown",
                 "object_agreement": None, "shared_objects": []}
        dmeta: dict = {}
        state = {"ts": round(now, 2),
                 "cameras": {str(i): eyes[i] for i in range(len(eyes))},
                 "dominant_eye": 0, "binocular": binoc, "proprioception": prop,
                 "audio": aud, "gaze": gaze,
                 "descriptor": _object_phrase(self._objects)
                               + describe(eyes, binoc, prop, gaze, aud, meta=dmeta)}
        state.update(dmeta)
        sal = self.salience.score(state)
        state["salience"] = sal
        # Coherence with an eye gone: the agreement term is unavailable rather than zero, so
        # it is dropped and the remaining terms carry their own weight. Reporting 0.4*0 here
        # would read as "my senses violently disagree" when the truth is "I cannot compare".
        eyes_live = sum(0.0 if e.get("stalled") else 1.0 for e in eyes) / max(1, len(eyes))
        liveness = (eyes_live + (1.0 if prop.get("ok") else 0.0)
                    + (1.0 if aud.get("ok") else 0.0)) / 3.0
        state["coherence"] = round((0.3 * (1.0 - sal.get("conflict", 0.0))
                                    + 0.3 * liveness) / 0.6, 3)
        self._emit(state)
        self.journal.observe(state, sal)
        for i in blind:
            if self._stall[i] >= RECOVER_CYCLES and now - self._last_recover[i] > RECOVER_COOLDOWN_S:
                self._recover_camera(i)

    def run(self):
        self.start()
        period = 1.0 / POLL_HZ
        try:
            while True:
                t0 = time.time()
                gaze, target = self._read_gaze()
                self._note_choice(gaze, target)
                if gaze == "closed":
                    # eyes shut — the self refuses the stream. The senses rest.
                    self._emit({"ts": round(time.time(), 2), "gaze": "closed",
                                "descriptor": "eyes closed — resting, not taking in the world"})
                    if self.display:
                        self._draw_closed()
                    time.sleep(period); continue
                frames = [c.frame for c in self.cams]
                blind = [i for i, f in enumerate(frames) if f is None]
                if blind:
                    # A dark eye must not halt the whole organ. `Camera.frame` only stays
                    # None when that camera has never delivered a single frame since it was
                    # opened, and the self-heal that could reopen it lives BELOW this point
                    # — so returning here stranded the loop in the one state it exists to
                    # repair. Measured on Sprout 2026-09-14..17: 3.5 days spinning at 20 Hz,
                    # perception.json frozen at the restart, `_recover_camera` never reached
                    # once, and with it every downstream sense — hearing and the inner ear
                    # are independent organs that were silenced by a camera.
                    self._sense_blind(blind, frames, gaze, target)
                    dt = time.time() - t0
                    if dt < period:
                        time.sleep(period - dt)
                    continue
                perceived = [self._perceive_one(i, frames[i], gaze, target) for i in range(2)]
                eyes = [p[0] for p in perceived]; grays = [p[1] for p in perceived]
                binoc = self.binoc.correlate(grays[0], grays[1], eyes[0]["attention"])
                self.dfield.update(grays[0], grays[1])   # instrument: accumulate the misalignment field
                if t0 - self._det_ts > DET_PERIOD:       # semantic vision: WHAT it sees (throttled ~2.5Hz)
                    self._det_ts = t0
                    raw = [self.detector.detect(frames[i]) for i in range(2)]
                    self._objects = [self._stab[i].update(raw[i]) for i in range(2)]  # temporal hysteresis
                for i in range(2):
                    eyes[i]["objects"] = self._objects[i]
                prop = self.prop.state()
                aud = self.hearing.state()
                self._adjudicate_sensors(eyes, binoc, prop)  # still vs stalled, using ego-motion + cross-eye
                dmeta = {}
                state = {"ts": round(time.time(), 2), "cameras": {str(i): eyes[i] for i in range(2)},
                         "dominant_eye": int(np.argmax([e["motion"] for e in eyes])),
                         "binocular": binoc, "proprioception": prop, "audio": aud, "gaze": gaze,
                         "descriptor": _object_phrase(self._objects) + describe(eyes, binoc, prop, gaze, aud, meta=dmeta)}
                state.update(dmeta)  # modalities + audio_onset, truth from composition time
                sal = self.salience.score(state)
                state["salience"] = sal
                # binocular agreement: prefer SEMANTIC correspondence (both eyes name the same thing)
                # when objects are present — robust to the eyes' misalignment/focus that defeats pixel
                # matching — and fall back to the pixel-based agreement on object-less scenes.
                obj_agree, shared = binocular_object_agreement(self._objects[0], self._objects[1])
                binoc["object_agreement"] = obj_agree
                binoc["shared_objects"] = shared
                agree = obj_agree if obj_agree is not None else binoc.get("agreement", 0.0)
                # coherence — how well the senses agree (a candidate reward signal; reward exploration
                # E2). High when the eyes correlate (semantically when they can), the reafference is
                # unambiguous, and the senses are live; low under conflict or a dead sensor.
                eyes_live = sum(0.0 if e.get("stalled") else 1.0 for e in eyes) / 2.0
                liveness = (eyes_live + (1.0 if prop.get("ok") else 0.0) + (1.0 if aud.get("ok") else 0.0)) / 3.0
                state["coherence"] = round(0.4 * agree
                                           + 0.3 * (1.0 - sal.get("conflict", 0.0))
                                           + 0.3 * liveness, 3)
                self._emit(state)
                self.journal.observe(state, sal)
                # self-heal: a camera frozen too long has a stuck Argus consumer — reopen it
                now = time.time()
                # instrument: periodically dump the measured misalignment field (non-forcing)
                if now - self._dfield_ts > 8.0:
                    self._dfield_ts = now
                    try:
                        snap = self.dfield.snapshot()
                        tmp = DISPARITY_PATH + ".tmp"
                        with open(tmp, "w") as f:
                            json.dump({"ts": round(now, 2), **snap}, f)
                        os.replace(tmp, DISPARITY_PATH)
                    except Exception:
                        pass
                for i in range(2):
                    if self._stall[i] >= RECOVER_CYCLES and now - self._last_recover[i] > RECOVER_COOLDOWN_S:
                        self._recover_camera(i)
                if self.display:
                    self._draw(frames, eyes, state)
                dt = time.time() - t0
                if dt < period:
                    time.sleep(period - dt)
        except KeyboardInterrupt:
            pass
        finally:
            for c in self.cams:
                c.stop()
            self.prop.stop()
            self.hearing.stop()
            if self.display:
                cv2.destroyAllWindows()

    def _draw(self, frames, eyes, state):
        panels = []
        for i, f in enumerate(frames):
            f = f.copy(); h, w = f.shape[:2]; e = eyes[i]
            r = e["attention"]
            x1 = int((r["cx"]-r["w"]/2)*w); y1 = int((r["cy"]-r["h"]/2)*h)
            x2 = int((r["cx"]+r["w"]/2)*w); y2 = int((r["cy"]+r["h"]/2)*h)
            if e.get("stalled"):     col = (0, 0, 255)      # red — confirmed stalled
            elif e.get("frozen"):    col = (0, 140, 255)    # orange — stale, not refreshing (unverified)
            elif e["motion"] > MOTION_TH: col = (0, 200, 255)  # yellow — live motion
            else:                    col = (120, 120, 120)  # grey — live, still
            cv2.rectangle(f, (x1, y1), (x2, y2), col, 2)
            cv2.putText(f, f"eye{i} mot={e['motion']:.2f} trust={e['trust']:.2f}", (8, 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
            if e.get("stalled"):
                cv2.putText(f, "STALLED - NO FRESH FRAMES", (8, h // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            panels.append(f)
        combo = np.hstack(panels)
        cv2.putText(combo, state["descriptor"], (8, combo.shape[0]-12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
        cv2.imshow("Sprout visual cortex", combo)
        cv2.waitKey(1)

    def _draw_closed(self):
        blank = np.zeros((360, 1280, 3), np.uint8)
        cv2.putText(blank, "eyes closed - resting", (430, 185),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (90, 90, 110), 2)
        cv2.imshow("Sprout visual cortex", blank)
        cv2.waitKey(1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--display", action="store_true", help="show overlay on screen")
    args = ap.parse_args()
    VisualCortex(display=args.display).run()
