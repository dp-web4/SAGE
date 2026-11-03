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


def test_gemma4_uses_its_measured_ratio_and_still_errs_high():
    cpt = btl.preflight_cpt(_llm(load_capabilities("gemma4:12b")))
    assert cpt == 3.3
    assert cpt < 3.46, "must sit below every measured ratio (prose 3.46, schemas 3.64)"


def test_the_stalled_gemma4_seed_is_admitted_at_its_window():
    """mcnugget-being, 2026-11-02T01:14Z on: every beat refused at step 1, the seed estimated at
    ~16,727 tokens at 2.9 against num_ctx 16384. The same chars at gemma4's 3.3 fit under
    16384 - WINDOW_SEND_MARGIN, and still sit above the last server-counted step-1 prompt (12,301)."""
    chars = 16727 * btl.PREFLIGHT_CPT
    est = chars / btl.preflight_cpt(_llm(load_capabilities("gemma4:12b")))
    assert 12301 < est < 16384 - btl.WINDOW_SEND_MARGIN, est


def test_gemma4_config_changes_nothing_but_the_ratio():
    """gemma4 ran on default.json; its own config must not move any other field — in particular no
    think_default, so resolve_think still asks the server (#599)."""
    from dataclasses import asdict
    g, d = asdict(load_capabilities("gemma4:12b")), asdict(load_capabilities("some-unknown:1b"))
    diff = {k for k in g if g[k] != d[k]} - {"family", "notes"}
    assert diff == {"preflight_chars_per_token"}, diff
    assert load_capabilities("gemma4:e4b").declared_think("gemma4:e4b") is None


def test_only_measured_families_declare_one():
    """A guard on the blast radius: only families with a measured ratio change their preflight."""
    import json
    import glob
    cfg_dir = os.path.join(os.path.dirname(__file__), "..", "..", "irp", "adapters", "model_configs")
    declared = sorted(json.load(open(f)).get("family") for f in glob.glob(os.path.join(cfg_dir, "*.json"))
                      if "preflight_chars_per_token" in json.load(open(f)))
    assert declared == ["gemma4", "llama3.1"], declared
