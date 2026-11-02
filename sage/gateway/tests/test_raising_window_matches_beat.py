"""The raising session runs the being's model with the same window as the governed beat.

On Sprout the operator raised the being's num_ctx to 24576 in instance.json (2026-10-15). The beat
honoured it (governed_turn: resolve_num_ctx, then tuned_num_ctx); the raising session applied only
the model config's 16384. Ollama reloads a model whose context changes, so on 2026-10-17 every
raising turn cost a reload at 16384 and the next call another at 24576 (24 loads at 16384 among
52 at 24576 in one day). These pin that the raising path resolves the window the beat does.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from sage.gateway.governed_turn import resolve_num_ctx, tuned_num_ctx

_SCRIPT = Path(__file__).resolve().parents[2] / "raising" / "scripts" / "ollama_raising_session.py"


@pytest.fixture(scope="module")
def raising():
    spec = importlib.util.spec_from_file_location("ollama_raising_session_window", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MODEL = "qwen3.8-distill:4b"


def _home(tmp_path, cfg):
    (tmp_path / "instance.json").write_text(json.dumps(cfg))
    return tmp_path


def test_the_operators_window_reaches_raising(raising, tmp_path):
    """Sprout's setting: num_ctx 24576 with a declared ceiling of 24576."""
    home = _home(tmp_path, {"num_ctx": 24576, "param_bounds": {"num_ctx": [8192, 24576]}})
    assert raising.raising_num_ctx(MODEL, home) == 24576


def test_raising_and_the_beat_agree(raising, tmp_path):
    for cfg in ({}, {"num_ctx": 24576, "param_bounds": {"num_ctx": [8192, 24576]}},
                {"num_ctx": 12000}):
        home = _home(tmp_path, cfg)
        beat = tuned_num_ctx(home, resolve_num_ctx(MODEL, 8192))
        assert raising.raising_num_ctx(MODEL, home) == beat, cfg


def test_no_setting_keeps_the_model_configs_window(raising, tmp_path):
    home = _home(tmp_path, {})
    assert raising.raising_num_ctx(MODEL, home) == resolve_num_ctx(MODEL, 8192)


def test_an_unbounded_setting_cannot_grow_past_the_model_config(raising, tmp_path):
    """Growing needs a declared ceiling (the beat's rule, VRAM fit); shrinking does not."""
    cfg_window = resolve_num_ctx(MODEL, 8192)
    home = _home(tmp_path, {"num_ctx": cfg_window * 4})
    assert raising.raising_num_ctx(MODEL, home) == cfg_window
