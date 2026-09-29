"""The --gpu card check in seat_run_requests.

Fleet policy 2026-09-13 gives the being priority on the GPU. Before this, `--gpu` documented
itself as "for a seat that has checked the card has room" and nothing checked — the safeguard
was a seat remembering. Measured on CBP 2026-09-25: 630 MiB free of 8,192 with the being's
qwen3.8-distill:4b resident at 4.8 GB, while the being's own training script asks for CUDA.
"""
import importlib.util
import os
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "scripts" / "seat_run_requests.py"
_spec = importlib.util.spec_from_file_location("seat_run_requests", _SRC)
srr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srr)


def _with(free, resident):
    srr._free_vram_mib = lambda: free
    srr._resident_models = lambda: resident


def test_a_full_card_is_refused_and_names_what_holds_it():
    _with(630, [("qwen3.8-distill:4b", 4.8)])
    why = srr.why_the_card_cannot_take_a_job()
    assert why, "a card with 630 MiB free must be refused"
    assert "630" in why and "qwen3.8-distill:4b" in why, why
    assert "thinks with that model" in why, "the refusal must say why it matters, not just no"


def test_an_empty_card_is_allowed():
    _with(7800, [])
    assert srr.why_the_card_cannot_take_a_job() is None


def test_unknown_is_not_free():
    """THE LOAD-BEARING ONE. A seat that cannot read the card is exactly the seat that should
    not load it, and the failure this prevents is a host crash, not a slow job."""
    _with(None, [])
    why = srr.why_the_card_cannot_take_a_job()
    assert why and "not an idle one" in why, why


def test_the_floor_is_a_floor_not_a_zero():
    """Refusing only at 0 free would still evict the model: it needs room to stay resident and
    to grow a little between beats."""
    _with(srr.GPU_HEADROOM_MIB - 1, [("qwen3.8-distill:4b", 4.8)])
    assert srr.why_the_card_cannot_take_a_job(), "just under the floor must refuse"
    _with(srr.GPU_HEADROOM_MIB + 1, [])
    assert srr.why_the_card_cannot_take_a_job() is None, "just over the floor must allow"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"PASS: {len(tests)} gpu-guard tests")
