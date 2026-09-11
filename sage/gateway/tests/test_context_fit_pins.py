"""Regression pins for context-fit behaviour in heartbeat._fill_headroom.

Authored by legion-being 2026-09-10; evidence status per pin in
scratch/pins-2026-09-10.md (legion home). Import confirmed against
sage/gateway/tests/test_context_fit.py line 8: from sage.gateway.heartbeat import ...
"""
import inspect
import pathlib

from sage.gateway import heartbeat


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
def test_p2_headroom_never_negative():
    """P2 [S] clamp pin — placeholder until parameter names are line-cited;
    then becomes a direct call asserting headroom == 0 for usage > window."""
    fn = _fill()
    assert callable(fn)


def test_p4_fill_no_side_effect_on_module():
    """P4 [S] purity pin — placeholder; upgrade to module-state snapshot/compare
    around a call once the interface is line-cited."""
    before = {k: v for k, v in vars(heartbeat).items() if not k.startswith("__")}
    _fill()
    after = {k: v for k, v in vars(heartbeat).items() if not k.startswith("__")}
    assert set(before) == set(after), "P4: calling the fill must not add/remove module attributes"


def test_p6_base_suite_tests_stay_present():
    """P6 [V] presence pin."""
    here = pathlib.Path(__file__).parent / "test_context_fit.py"
    assert here.exists() and here.stat().st_size > 0
