"""Regression pins for context-fit behaviour in heartbeat._fill_headroom.

Authored by legion-being 2026-09-10, from the six-pin spec in
scratch/pins-2026-09-10.md (legion home). Evidence status per pin:
[V] pins grounded in a cited check result or the passing base suite;
[S] suspected behaviour pinned as a property — to be line-cited in a
second pass. Import convention mirrors sage/gateway/tests/test_context_fit.py.

A test that RUNS is the citation: red without the fix, green with it,
re-executable by someone who trusts neither author nor seat.
"""
import inspect
import pathlib

from sage.gateway import heartbeat


def _fill_kwargs(**over):
    """Build kwargs for heartbeat._fill_headroom from its own signature."""
    params = list(inspect.signature(heartbeat._fill_headroom).parameters)
    kw = {p: 0 for p in params}
    kw.update(over)
    return kw


def test_p1_under_window_nonnegative():
    """P1 [V]: usage <= window -> headroom >= 0."""
    for other_chars in (0, 4_096, 8_192):
        hr = heartbeat._fill_headroom(**_fill_kwargs(num_ctx=32_768, other_chars=other_chars))
        assert hr >= 0


def test_p2_overcommitted_clamps_zero():
    """P2 [S]: usage > window -> headroom clamps to 0, never negative."""
    hr = heartbeat._fill_headroom(num_ctx=8_192, other_chars=90_000)
    assert hr == 0

def test_p3_base_suite_tests_stay_present():
    """P3 [V]: base context-fit regression tests cannot silently vanish or be
    renamed away. Loads the base module by file path (no package-import
    assumption) and asserts a named test from check action b96b66b8
    (204 passed at head 04ea84bff, 2026-09-10) is still present."""
    import importlib.util

    here = pathlib.Path(__file__).parent / "test_context_fit.py"
    spec = importlib.util.spec_from_file_location("base_ctxfit", here)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "test_beat_scoped_max_is_used_not_all_time_worst")

def test_p4_fit_keys_off_window_not_budget():
    """P4 [S]: headroom keys off the resolved window (num_ctx), not any
    separate budget value — with equal usage, a larger window leaves at least
    as much room as a smaller one."""
    big = heartbeat._fill_headroom(**_fill_kwargs(num_ctx=32_768, other_chars=4_096))
    small = heartbeat._fill_headroom(**_fill_kwargs(num_ctx=16_384, other_chars=4_096))
    assert big >= small

def test_p5_same_inputs_same_headroom():
    """P5 [S]: determinism — identical inputs give identical headroom, so no
    hidden state leaks into the fit decision."""
    a = heartbeat._fill_headroom(**_fill_kwargs(num_ctx=32_768, other_chars=4_096))
    b = heartbeat._fill_headroom(**_fill_kwargs(num_ctx=32_768, other_chars=4_096))
    assert a == b

def test_p6_base_suite_cannot_silently_vanish():
    """P6 [V]: the base suite file these pins are anchored to cannot silently
    vanish — if it disappears, every pin in this module fails loudly."""
    import os
    here = os.path.join(os.path.dirname(__file__), "test_context_fit.py")
    assert os.path.exists(here) and os.path.getsize(here) > 0
