"""The step-1 preflight divides by the model's own chars-per-token, not one calibrated elsewhere.

Measured 2026-10-30 (SAGE #582): at the fixed 2.9, pub-being (llama3.1:8b) had every explore refused
from 2026-10-27 07:46Z — its step-1 seed estimated at 14,569 tokens when the server counted 9,806 for
the same seed. llama3.1 tokenizes the being's prose at 3.67 chars/token and tool schemas at 3.92.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import being_tool_loop as btl  # noqa: E402
from sage.irp.adapters.model_capabilities import load_capabilities  # noqa: E402


def _llm(caps):
    return SimpleNamespace(_adapter=SimpleNamespace(capabilities=caps))


def test_an_undeclared_model_keeps_the_old_constant():
    """No family changes behaviour unless it declares a measured ratio."""
    assert btl.preflight_cpt(_llm(load_capabilities("qwen3.5:2b"))) == btl.PREFLIGHT_CPT
    assert btl.preflight_cpt(_llm(load_capabilities("some-unknown:1b"))) == btl.PREFLIGHT_CPT


def test_llama31_uses_its_measured_ratio_and_still_errs_high():
    cpt = btl.preflight_cpt(_llm(load_capabilities("llama3.1:8b")))
    assert cpt == 3.6
    assert cpt < 3.67, "must sit below every measured ratio (prose 3.67, schemas 3.92)"


def test_the_measured_pair_is_admitted_at_the_vram_fitting_window():
    """The seed the preflight refused: 14,569 tokens at 2.9 -> chars = 14,569 * 2.9. At llama3.1's
    3.6 the same chars estimate under 12,288 - WINDOW_SEND_MARGIN, while still above the server's
    9,806 — erring high, not low."""
    chars = 14569 * btl.PREFLIGHT_CPT
    est = chars / btl.preflight_cpt(_llm(load_capabilities("llama3.1:8b")))
    assert 9806 < est < 12288 - btl.WINDOW_SEND_MARGIN, est


def test_a_missing_or_implausible_declaration_falls_back():
    for bad in (None, "x", 0, 0.5, 40.0):
        assert btl.preflight_cpt(_llm(SimpleNamespace(preflight_chars_per_token=bad))) == btl.PREFLIGHT_CPT
    assert btl.preflight_cpt(SimpleNamespace()) == btl.PREFLIGHT_CPT, "no adapter at all"


def test_only_llama31_declares_one_today():
    """A guard on the blast radius: this change alters exactly one family's preflight."""
    import json
    import glob
    cfg_dir = os.path.join(os.path.dirname(__file__), "..", "..", "irp", "adapters", "model_configs")
    declared = sorted(json.load(open(f)).get("family") for f in glob.glob(os.path.join(cfg_dir, "*.json"))
                      if "preflight_chars_per_token" in json.load(open(f)))
    assert declared == ["llama3.1"], declared
