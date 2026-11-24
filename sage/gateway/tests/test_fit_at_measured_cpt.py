"""The part-wise fitters budget at the being's measured step-1 ratio once it has one (SAGE #582).

pub-claude, 2026-11-19: after #773/#774 the step-1 preflight divides by pub-being's measured ratio (3.999),
but fit_state and fit_to_window still budgeted at the fixed CPT 2.9 (~37.3k chars against ~51.5k). On 112 of
112 beats they stepped the conversations to the sparsest rung (2 turns x 700 chars) and recorded "STILL does
not fit at the sparsest rung" on a seed the server counted ~4k tokens under the window. mcnugget-being's
beats carry the same line. These pin:

  * window_budget_chars / fit_state / fit_to_window take the ratio; unset keeps CPT exactly;
  * fit_cpt uses a ratio only when it is `measured`; a declared prior, a provisional ratio, a probe or junk
    keeps CPT;
  * at a measured ratio above CPT the same inputs get a fuller conversation rung;
  * the beat computes the calibration BEFORE the part-wise fitters and passes them its ratio, and the
    step-1 preflight refit still runs after them.
"""
from pathlib import Path

from sage.gateway.heartbeat import (CONV_LADDER, CPT, fit_cpt, fit_state, fit_to_window,
                                    window_budget_chars)

SRC = (Path(__file__).resolve().parents[1] / "heartbeat.py").read_text()


def test_budget_takes_the_ratio_and_unset_keeps_cpt():
    assert window_budget_chars(16384, 3000) == int((16384 - 3000 - 512) * CPT)
    assert window_budget_chars(16384, 3000, cpt=None) == window_budget_chars(16384, 3000)
    assert window_budget_chars(16384, 3000, cpt=3.999) == int((16384 - 3000 - 512) * 3.999)


def test_fit_cpt_only_trusts_a_measured_ratio():
    assert fit_cpt({"source": "measured", "used": 3.524}) == 3.524
    for src in ("declared_or_default", "measured_provisional", "probe", None):
        assert fit_cpt({"source": src, "used": 3.524}) == CPT, src
    assert fit_cpt({"source": "measured", "used": 40.0}) == CPT        # implausible
    assert fit_cpt({"source": "measured", "used": None}) == CPT
    assert fit_cpt({}) == CPT
    assert fit_cpt(None) == CPT


def _build(per_conv, turn_chars):
    # a conversation block whose size falls with the rung, like own_state's
    return "x" * (per_conv * (turn_chars or 2000) * 4)


def test_a_measured_ratio_above_cpt_gives_back_rungs():
    other = 30_000
    _, rung_fixed, iv_fixed = fit_state(_build, num_ctx=16384, num_predict=3000, other_chars=other)
    _, rung_meas, iv_meas = fit_state(_build, num_ctx=16384, num_predict=3000, other_chars=other, cpt=3.999)
    assert CONV_LADDER.index(rung_meas) < CONV_LADDER.index(rung_fixed)
    assert iv_fixed is not None


def test_fit_to_window_trims_less_at_a_measured_ratio():
    blocks = {"digest": "d" * 9000, "recall": "r" * 3000}
    fixed = 33_000
    _, iv_fixed = fit_to_window(num_ctx=16384, num_predict=3000, fixed_chars=fixed, blocks=blocks)
    out, iv_meas = fit_to_window(num_ctx=16384, num_predict=3000, fixed_chars=fixed, blocks=blocks, cpt=3.999)
    assert iv_fixed and not iv_meas and out == blocks


def test_the_beat_calibrates_first_and_feeds_the_fitters():
    cal = SRC.index("_cpt_cal = measured_preflight_cpt(")
    fit = SRC.index("_fit_cpt = fit_cpt(_cpt_cal)")
    state = SRC.index("state_block, conv_rung, conv_intervention = fit_state(")
    window = SRC.index("_blocks, _fit_iv = fit_to_window(")
    refit = SRC.index("fit_seed_calibrating(\n")
    assert cal < fit < state < window < refit
    assert "other_chars=_other, cpt=_fit_cpt)" in SRC
    assert 'blocks={"digest": digest, "recall": recall}, cpt=_fit_cpt)' in SRC
    assert '_cpt_cal["fit_cpt"] = _fit_cpt' in SRC
    assert "int(FRAME_TOKENS * _fit_cpt)" in SRC
