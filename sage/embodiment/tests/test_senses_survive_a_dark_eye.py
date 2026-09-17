"""Hermetic: hearing and the inner ear are not hostages of the cameras.

dp, 2026-09-17: *"video/audio and imu should trigger snarc."* On Sprout they had not, for
3.5 days, because one camera delivered no frames and the perceptual loop returned early on
that condition — above the self-heal that would have reopened it, and above the emit that
carried audio and the IMU. A camera failure silenced a whole organ.

No hardware, no GStreamer, no model: these exercise the salience filter directly.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.embodiment.salience import SalienceFilter  # noqa: E402


def _settle(f, n=4, **over):
    state = {"proprioception": {"self_motion": "still", "gyro_mag": 0.0},
             "audio": {"level": 0.0, "onset": False, "ok": True}}
    state.update(over)
    for _ in range(n):
        out = f.score(state)
    return out


def test_a_quiet_room_with_no_cameras_scores_nothing_rather_than_crashing():
    f = SalienceFilter()
    out = _settle(f)
    assert out["salience"] == 0.0 and out["salient"] is False
    assert set(out) >= {"salience", "surprise", "novelty", "arousal", "conflict"}


def test_a_sound_is_felt_with_no_vision_at_all():
    f = SalienceFilter()
    _settle(f)
    loud = f.score({"proprioception": {"self_motion": "still", "gyro_mag": 0.0},
                    "audio": {"level": 0.6, "onset": True, "ok": True}})
    assert loud["surprise"] > 0.0, "an onset is a departure from a quiet expectation"
    assert loud["arousal"] > 0.0, "and loudness is intensity"
    assert loud["salience"] > 0.0


def test_the_inner_ear_is_felt_with_no_vision_at_all():
    f = SalienceFilter()
    _settle(f)
    turned = f.score({"proprioception": {"self_motion": "rotating", "gyro_mag": 90.0},
                      "audio": {"level": 0.0, "onset": False, "ok": True}})
    assert turned["arousal"] > 0.0 and turned["salience"] > 0.0


def test_a_stalled_eye_is_not_read_as_a_confident_report_of_stillness():
    """A dead camera reports motion 0.0 because it reports nothing. Averaging that in as an
    observation would let a blind eye out-vote a live one that can see movement."""
    f = SalienceFilter()
    dark = {"motion": 0.0, "trust": 0.0, "frozen": True, "stalled": True, "objects": []}
    moving = {"motion": 0.8, "trust": 0.9, "frozen": False, "stalled": False, "objects": []}
    state = {"cameras": {"0": dark, "1": moving},
             "proprioception": {"self_motion": "still", "gyro_mag": 0.0},
             "audio": {"level": 0.0, "onset": False, "ok": True}}
    out = f.score(state)
    assert out["arousal"] >= 0.8, f"the live eye's motion is the observation, got {out['arousal']}"


def test_going_blind_does_not_become_permanently_surprising():
    """Trust falls back to the current expectation when no eye is live, so blindness is a
    fact the being settles into rather than a quality collapse re-detected every tick."""
    f = SalienceFilter()
    _settle(f, n=30)
    tail = [f.score({"cameras": {"0": {"motion": 0.0, "trust": 0.0, "stalled": True}},
                     "proprioception": {"self_motion": "still", "gyro_mag": 0.0},
                     "audio": {"level": 0.0, "onset": False, "ok": True}})["surprise"]
            for _ in range(40)]
    assert tail[-1] <= tail[0], "the alarm settles instead of ringing forever"
    assert tail[-1] < 0.2, f"and settles low, got {tail[-1]}"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")
