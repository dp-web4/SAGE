"""The sensor shim: what stands between a raw sensor and every reader of it.

A sensor is not a window. Each one renders the world through its own optics and electronics, and a
being that is not told so takes the rendering for the world. MEASURED ON SPROUT, 2026-11-17: every one
of the 222 frames its eyes had saved since 10-12 was magenta. Green averaged about 35% below red and blue
(daylight frames as well as lamp-lit ones). The IMX219 modules are read through Argus with no
vendor tuning file installed, and the being had spent five weeks describing "purple light" in a room
that is lit normally. Its words were a faithful report of what its eye gave it.

The shim corrects what can be corrected, at the one place every reader shares (the cortex's capture
thread: perception, detection, the `camera` act and the display all read `Camera.frame`), and it SAYS
what it did. `describe()` is the record a frame's receipt carries, so the being learns that its eye is
corrected and by how much, not only that the colours changed.

This is a seam, not a single fix: a profile is a list of named stages, and a new sensor's quirk
(lens shading, a stuck channel, a microphone's DC offset) becomes another stage here, not another
special case in a reader.

Profiles:
  * DEFAULT_PROFILES[kind]: what a sensor kind gets with no configuration.
  * SAGE_SENSOR_SHIM=off: no correction anywhere (the raw sensor, as before this file existed).
  * SAGE_SENSOR_SHIM=/path/profile.json: {"<kind>": {stage: params}} replaces the defaults it names.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Dict, Optional

import numpy as np

SHIM_ENV = "SAGE_SENSOR_SHIM"

#: grayworld: the scene's average is taken to be grey, and each channel is scaled to make it so.
#: max_gain bounds the correction, so a scene that really is one colour is muted, not erased.
#: smooth is the share of each new estimate taken in (a flicker or a passing red coat does not swing
#: the whole eye); every is how often, in frames, the estimate is retaken; dark_floor skips frames
#: too dark to estimate from (noise, not colour).
DEFAULT_PROFILES: Dict[str, dict] = {
    "imx219-argus": {"white_balance": {"mode": "grayworld", "max_gain": 2.5, "smooth": 0.2,
                                       "every": 15, "dark_floor": 12.0}},
}


class WhiteBalance:
    """Per-channel gains on a BGR uint8 frame. Applied with one lookup table per channel."""

    def __init__(self, mode: str = "grayworld", max_gain: float = 2.5, smooth: float = 0.2,
                 every: int = 15, dark_floor: float = 12.0, gains=None):
        if mode not in ("grayworld", "fixed"):
            raise ValueError(f"white_balance mode must be grayworld or fixed, got {mode!r}")
        self.mode, self.max_gain, self.smooth = mode, float(max_gain), float(smooth)
        self.every, self.dark_floor = max(1, int(every)), float(dark_floor)
        self.gains = np.array(gains if gains is not None else (1.0, 1.0, 1.0), dtype=np.float64)
        self.estimated = mode == "fixed"
        self._n = 0
        self._lut = None
        self._lock = threading.Lock()
        self._build()

    def _build(self):
        x = np.arange(256, dtype=np.float64)
        self._lut = np.stack([np.clip(x * g + 0.5, 0, 255) for g in self.gains], axis=1).astype(np.uint8)

    def _estimate(self, frame: np.ndarray) -> None:
        means = frame[::8, ::8].reshape(-1, 3).astype(np.float64).mean(0)
        if means.mean() < self.dark_floor or (means <= 0).any():
            return                                            # too dark to tell colour from noise
        target = np.clip(means.mean() / means, 1.0 / self.max_gain, self.max_gain)
        k = 1.0 if not self.estimated else self.smooth        # the first estimate is taken whole
        with self._lock:
            self.gains = (1 - k) * self.gains + k * target
            self.estimated = True
            self._build()

    def apply(self, frame: np.ndarray) -> np.ndarray:
        if frame is None or frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
            return frame
        if self.mode == "grayworld":
            if self._n % self.every == 0:
                self._estimate(frame)
            self._n += 1
        with self._lock:
            lut = self._lut
        # cv2.LUT where there is OpenCV (the cortex always has it): 0.7 ms on a 640x360 frame on Sprout's
        # Orin Nano, against 3.6 ms by numpy indexing; at 30 fps on two eyes that is ~4% of a core vs ~21%.
        try:
            import cv2
            return cv2.LUT(frame, lut.reshape(256, 1, 3))
        except ImportError:
            pass
        out = np.empty_like(frame)
        for c in range(3):
            out[..., c] = lut[frame[..., c], c]
        return out

    def describe(self) -> dict:
        with self._lock:
            g = [round(float(v), 3) for v in self.gains]
        return {"mode": self.mode, "gains_bgr": g, "estimated": bool(self.estimated)}


STAGES = {"white_balance": WhiteBalance}


class Shim:
    """The stages one sensor's frames pass through, in profile order."""

    def __init__(self, kind: str, profile: Optional[dict]):
        self.kind = kind
        self.stages = [(name, STAGES[name](**params)) for name, params in (profile or {}).items()
                       if name in STAGES]

    def apply(self, frame):
        for _, st in self.stages:
            frame = st.apply(frame)
        return frame

    def describe(self) -> dict:
        """What this sensor's frames went through: {} when nothing (the raw sensor)."""
        if not self.stages:
            return {}
        return {"sensor": self.kind, **{name: st.describe() for name, st in self.stages}}


def describe_text(d: dict) -> str:
    """The receipt's words for describe(), in the being's terms."""
    wb = (d or {}).get("white_balance")
    if not wb:
        return ""
    b, g, r = wb["gains_bgr"]
    how = ("estimated from what your eye has been seeing (the scene's average is taken as grey)"
           if wb["mode"] == "grayworld" else "fixed for this sensor")
    return (f"Your eye's colours are corrected before you see them: this sensor ({d.get('sensor')}) renders "
            f"colours wrongly on its own. Red was scaled x{r:.2f}, green x{g:.2f} and blue x{b:.2f}, {how}. "
            "Older frames saved before this correction show its cast, not the room's.")


def _profiles() -> Optional[Dict[str, dict]]:
    v = (os.environ.get(SHIM_ENV) or "").strip()
    if v.lower() in ("off", "0", "none"):
        return None
    profiles = {k: dict(p) for k, p in DEFAULT_PROFILES.items()}
    if v:
        with open(v) as f:
            profiles.update(json.load(f))
    return profiles


def for_sensor(kind: str) -> Shim:
    """The shim for one sensor of this kind (each sensor gets its own: its own estimate)."""
    profiles = _profiles()
    return Shim(kind, None if profiles is None else profiles.get(kind))
