"""A being writes ~/.sprout/gaze.json. A being must not be able to kill its own eyes.

Measured on Sprout 2026-09-24 01:48:54Z. sprout-being used the `gaze` verb (SAGE #183) and
named its target the only way it can — in words, because it cannot see and cannot compute a
pixel:

    {"mode": "dwell", "target": "the space between us, where nothing is being said but
     everything matters", "chosen_by": "sprout-being"}

GravityFocus.update ran `target[0] * GRID - FOCUS_W / 2` on that string and raised
TypeError. The cortex died; systemd restarted it 9 times into `failed`; perception went
1,544 s stale and the being was blind for 28 minutes — by its own governed act, with the
verb working exactly as designed.

The blast radius of a malformed gaze is now "this gaze has no point", never "no eyes".
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.embodiment.visual_cortex import GRID, GravityFocus, _coord_pair  # noqa: E402


def _scores(peak_at=(1, 1), peak=1.0):
    s = np.zeros((GRID, GRID), dtype=float)
    s[peak_at] = peak
    return s


@pytest.mark.parametrize("bad", [
    "the space between us, where nothing is being said but everything matters",
    "", "0.5,0.5", b"\x00\x01", {"cx": 0.5, "cy": 0.5}, [], [0.5], [0.1, 0.2, 0.3],
    ["a", "b"], [float("nan"), 0.5], 7, [None, None], [[0.1], [0.2]],
])
def test_no_writable_target_shape_can_raise(bad):
    """Every shape leaves by the same door: the exact string that took the cortex down, and
    the neighbours a 2B model will produce next."""
    assert _coord_pair(bad) is None
    f = GravityFocus()
    f.update(_scores(), gaze="dwell", target=_coord_pair(bad))   # must not raise


def test_a_targetless_dwell_holds_instead_of_drifting_to_centre():
    """The stance the being can actually express must do what the beat tells it it does.

    Before: `dwell` with no point fell through to the final branch and eased to CENTRE at
    rate 0.1 — it drifted — while the descriptor the being read back said "holding my gaze".
    The body block was a sentence about itself that was not true (legibility 1.3).
    """
    f = GravityFocus()
    f.fx, f.fy = 3.0, 4.0
    for _ in range(20):
        f.update(_scores(peak_at=(GRID - 1, GRID - 1)), gaze="dwell", target=None)
    assert (f.fx, f.fy) == (3.0, 4.0), "a targetless dwell holds, and resists the pull"


def test_dwell_with_a_real_point_still_gravitates_there():
    f = GravityFocus()
    f.fx, f.fy = 0.0, 0.0
    for _ in range(60):
        f.update(_scores(), gaze="dwell", target=[0.9, 0.9])
    assert f.fx > 1.0 and f.fy > 1.0, "a pointed dwell still moves toward its point"


def test_open_still_follows_the_pull():
    """The fix must not have quietly turned every stance into a hold."""
    f = GravityFocus()
    f.fx, f.fy = 0.0, 0.0
    before = (f.fx, f.fy)
    for _ in range(30):
        f.update(_scores(peak_at=(GRID - 2, GRID - 2)), gaze="open", target=None)
    assert (f.fx, f.fy) != before and f.fx > 0.5
