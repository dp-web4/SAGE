"""`requires_gate_core`: skip, WITH the reason, a test that needs the real hestia gate law.

A test that builds a real BeingGateClient needs `hestia_gate_core`. Inside a being's sandboxed
`check` (--clearenv, HOME=/tmp, only the worktree mounted) there is none to import, and such tests
failed with "'NoneType' object has no attribute 'NormalizedEvent'" on every check the being ran:
five permanent reds that legion-being spent a beat diagnosing as stale fixtures (2026-09-29). A
skip that names its reason is honest about what could not run; a red that is not about the code
is noise the being has to reason through every time.
"""
import importlib.util
import sys

import pytest


def gate_core_importable() -> bool:
    try:
        from sage.gateway.being_gate_client import _resolve_hestia_shared
        shared = _resolve_hestia_shared()
        if not shared:
            return False
        if shared not in sys.path:
            sys.path.insert(0, shared)
        return importlib.util.find_spec("hestia_gate_core") is not None
    except Exception:
        return False


requires_gate_core = pytest.mark.skipif(
    not gate_core_importable(),
    reason="the hestia gate law is not importable here (e.g. inside a sandboxed check); "
           "run outside the sandbox to exercise this")


def standalone_skip_reason(fn):
    """For a plain-script runner (`python test_x.py`), which pytest marks never reach: the reason
    `fn` must be skipped here, or None. GPT on #266: the script mode should SAY the gate core is
    missing, not report it as a failure."""
    for m in getattr(fn, "pytestmark", []):
        if m.name == "skipif" and m.args and m.args[0]:
            return m.kwargs.get("reason", "skipped")
    return None
