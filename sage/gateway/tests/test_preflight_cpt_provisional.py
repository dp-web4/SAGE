"""A seed still refused under the prior re-fits with the being's own few counts (SAGE #582, after #774).

mcnugget-being, 2026-11-17 22:48Z: 2 counted beats (3.68 chars/token each), so calibration stayed on gemma4's
declared 3.3; the seed measured 16,255 against a line of 16,128 with nothing left to trim, and explore was
refused at step 0. A refused beat records no sample, so five would never arrive. Hermetic: temp dirs only.
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.heartbeat import (CONV_LADDER, MEASURED_CPT_MARGIN, MEASURED_CPT_MIN_SAMPLES,  # noqa: E402
                                    fit_seed_to_preflight, measured_preflight_cpt,
                                    provisional_cpt_for_refused_seed)


def _beat(chars, toks, model="gemma4:12b"):
    return {"model": model, "num_ctx": 16384,
            "explore": {"generates": [{"prompt_chars": chars, "prompt_eval_count": toks}]}}


def _home(tmp_path, records):
    with open(tmp_path / "heartbeats.jsonl", "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return tmp_path


def test_few_samples_offer_a_provisional_ratio_and_no_value(tmp_path):
    recs = [_beat(52990, 14400), _beat(53000, 14402)]          # McNugget's two, ~3.68
    cal = measured_preflight_cpt(_home(tmp_path, recs), "gemma4:12b", prior=3.3)
    assert cal["samples"] == 2 and cal["value"] is None, "five are still needed by default"
    assert cal["provisional"] == round(min(52990 / 14400, 53000 / 14402) * MEASURED_CPT_MARGIN, 3)


def test_enough_samples_give_a_value_and_no_provisional(tmp_path):
    cal = measured_preflight_cpt(_home(tmp_path, [_beat(53000, 14400)] * MEASURED_CPT_MIN_SAMPLES),
                                 "gemma4:12b", prior=3.3)
    assert cal["value"] and "provisional" not in cal


def test_no_samples_offer_nothing(tmp_path):
    cal = measured_preflight_cpt(_home(tmp_path, [_beat(53000, 14400, model="other:1b")]), "gemma4:12b")
    assert "provisional" not in cal and cal["value"] is None


def test_provisional_applies_only_to_a_seed_still_refused_without_a_value():
    cal = {"value": None, "provisional": 3.57}
    assert provisional_cpt_for_refused_seed({"still_refused": True}, cal) == 3.57
    assert provisional_cpt_for_refused_seed({"still_refused": False}, cal) is None, "trimmed to fit: no change"
    assert provisional_cpt_for_refused_seed(None, cal) is None, "accepted under the prior: no change"
    assert provisional_cpt_for_refused_seed({"still_refused": True}, {"value": 3.57}) is None, "already measured"
    assert provisional_cpt_for_refused_seed({"still_refused": True}, {"value": None}) is None, "no counts"
    assert provisional_cpt_for_refused_seed({"still_refused": True},
                                            {"value": None, "provisional": 42.0}) is None, "implausible"


def test_the_2248Z_seed_is_refused_at_the_prior_and_admitted_provisionally():
    """The live numbers: 16,255 tokens at 3.3 is ~53.6k chars, nothing trimmable left."""
    chars = int(16255 * 3.3)
    render = lambda rung, digest, recall: chars          # noqa: E731  (the seed does not shrink)
    def fit(cpt):
        return fit_seed_to_preflight(render, lambda r: r / cpt, num_ctx=16384,
                                     rung_index=len(CONV_LADDER) - 1, digest="", recall="", cpt=cpt)
    *_, iv = fit(3.3)
    assert iv and iv["still_refused"], iv
    prov = provisional_cpt_for_refused_seed(iv, {"value": None, "provisional": round(3.68 * MEASURED_CPT_MARGIN, 3)})
    *_, iv2 = fit(prov)
    assert iv2 is None, f"at {prov} the same seed estimates {chars / prov:.0f}, under 16,128: sent unchanged"
    # and it still errs high against the server's own count of that seed (~14,400)
    assert chars / prov > chars / 3.68
