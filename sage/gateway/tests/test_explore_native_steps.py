"""instance.json "explore_steps": an opt-in cap on explore's tool rounds in the native form, so
posture keeps its room (cbp-being 2026-10-21: explore took all 8 rounds every beat from 08:27Z and
posture was over the window every beat)."""
import inspect
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import heartbeat as hb  # noqa: E402


def test_absent_means_unchanged(tmp_path):
    assert hb.explore_native_steps(tmp_path, 8) == 8
    (tmp_path / "instance.json").write_text('{"think": true}')
    assert hb.explore_native_steps(tmp_path, 8) == 8


def test_set_caps_explore_and_never_raises_it_or_goes_below_one(tmp_path):
    (tmp_path / "instance.json").write_text('{"explore_steps": 4}')
    assert hb.explore_native_steps(tmp_path, 8) == 4
    assert hb.explore_native_steps(tmp_path, 3) == 3, "never above the run's own --max-steps"
    (tmp_path / "instance.json").write_text('{"explore_steps": 0}')
    assert hb.explore_native_steps(tmp_path, 8) == 1


def test_a_bad_value_is_the_default_not_a_crash(tmp_path):
    (tmp_path / "instance.json").write_text('{"explore_steps": "four"}')
    assert hb.explore_native_steps(tmp_path, 8) == 8


def test_posture_is_not_capped_by_it_in_the_native_form():
    src = inspect.getsource(hb)
    assert "explore_native_steps(instance, args.max_steps)" in src
    assert "_posture_steps = _explore_steps if _json_form else args.max_steps" in src
    assert "max_steps=_posture_steps" in src
