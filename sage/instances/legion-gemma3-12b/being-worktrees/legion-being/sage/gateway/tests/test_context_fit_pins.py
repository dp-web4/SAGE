"""Regression pins for context-fit behaviour in heartbeat._fill_headroom.

Authored by legion-being 2026-09-10; evidence status per pin in
scratch/pins-2026-09-10.md (legion home). Import line mirrors
sage/gateway/tests/test_context_fit.py — confirm in second pass.
"""
import inspect
import pathlib

from gateway import heartbeat  # TODO(second pass): confirm module path


def _fill():
    fn = getattr(heartbeat, "_fill_headroom", None)
    assert callable(fn), "P1: _fill_headroom must exist and be callable"
    return fn

def test_p1_fill_headroom_is_defined():
    """P1 [V] presence pin."""
    _fill()


def test_p3_headroom_shape_floor():
    """P3 [S] floor pin — placeholder until parameter names are line-cited;
    then becomes a direct call asserting headroom >= 0 for usage <= window."""
    fn = _fill()
    assert len(inspect.signature(fn).parameters) >= 2

def test_p5_fill_is_plain_function():
    """P5 [S] determinism pin — placeholder; upgrade to same-inputs-same-output
    call once the interface is line-cited."""
    fn = _fill()
    assert inspect.isfunction(fn) or inspect.ismethod(fn)


def test_p6_base_suite_stays_present():
    """P6 [V] compatibility pin: base context-fit tests cannot silently vanish."""
    here = pathlib.Path(__file__).parent / "test_context_fit.py"
    assert here.exists() and here.stat().st_size > 0
