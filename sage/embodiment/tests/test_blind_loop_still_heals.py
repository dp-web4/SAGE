"""Hermetic: an eye that delivers nothing must not strand the loop that could reopen it.

Measured on Sprout, 2026-09-14..17. `Camera.frame` stays None only while that camera has
never produced a single frame, and the perceptual loop's guard

    if any(f is None for f in frames): time.sleep(0.05); continue

sat ABOVE both the emit and the self-heal. So the one state `_recover_camera` exists to
repair was the exact state in which it could never run: 3.5 days spinning at 20 Hz, the
perceptual state frozen at the restart, and every other sense silenced with it.

No cameras are opened here — the cortex is built without `__init__` and handed fakes.
"""
import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.embodiment import visual_cortex as vc  # noqa: E402


class _Journal:
    def __init__(self):
        self.seen = []

    def observe(self, state, sal):
        self.seen.append((state, sal))

    def _append(self, ev):
        self.seen.append(ev)


def _cortex(stall=(0, 0)):
    """A VisualCortex with no hardware: no __init__, so no Camera() and no GStreamer."""
    c = object.__new__(vc.VisualCortex)
    c.cams = [types.SimpleNamespace(frame=None), types.SimpleNamespace(frame=None)]
    c._stall = list(stall)
    c._last_recover = [0.0, 0.0]
    c._objects = [[], []]
    c.prop = types.SimpleNamespace(state=lambda: {"self_motion": "still", "gyro_mag": 0.0,
                                                  "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
                                                  "accel_mag": 1.0, "ok": True})
    c.hearing = types.SimpleNamespace(state=lambda: {"level": 0.0, "onset": False,
                                                     "baseline": 0.0, "ok": True, "trust": 1.0})
    c.salience = vc.SalienceFilter()
    c.journal = _Journal()
    c.display = False
    c.emitted = []
    c._emit = c.emitted.append
    c.recovered = []
    c._recover_camera = c.recovered.append
    return c


def test_a_tick_with_no_frames_still_emits_a_perceptual_state():
    c = _cortex()
    c._sense_blind([0, 1], [None, None], "open", None)
    assert len(c.emitted) == 1, "the organ reports, rather than falling silent"
    s = c.emitted[0]
    assert s["cameras"]["0"]["stalled"] is True and s["cameras"]["1"]["stalled"] is True
    assert s["proprioception"]["ok"] is True, "the inner ear is still reported"
    assert s["audio"]["ok"] is True, "so is hearing"
    assert "salience" in s and "coherence" in s
    assert s["descriptor"], "and it says, in words, what has happened to it"


def test_the_self_heal_the_old_guard_made_unreachable_now_fires():
    # already past RECOVER_CYCLES, and the cooldown long expired
    c = _cortex(stall=(vc.RECOVER_CYCLES, 0))
    c._last_recover = [0.0, 0.0]
    c._sense_blind([0], [None, None], "open", None)
    assert c.recovered == [0], "the eye whose stall has matured is reopened"
    assert 1 not in c.recovered, "and only that one"


def test_a_young_stall_is_left_alone_to_mature():
    c = _cortex(stall=(0, 0))
    c._sense_blind([0, 1], [None, None], "open", None)
    assert c.recovered == [], "one missed frame is not a dead camera"
    assert c._stall[0] == 1 and c._stall[1] == 1, "but it counts toward becoming one"


def test_blindness_does_not_report_violent_disagreement():
    """Coherence is renormalised over the terms that remain. Multiplying an unavailable
    binocular agreement by its weight would read as 'my senses conflict' when the truth is
    'I cannot compare them'."""
    c = _cortex()
    c._sense_blind([0, 1], [None, None], "open", None)
    coh = c.emitted[0]["coherence"]
    assert 0.0 <= coh <= 1.0
    assert coh > 0.3, f"a quiet body with working ears is not incoherent, got {coh}"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")
