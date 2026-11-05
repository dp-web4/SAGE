"""A capped tool phase is said in the reflect record (heartbeat._capped_line)."""
from types import SimpleNamespace

from sage.gateway import heartbeat as H


def _act(effector="memory_read", **args):
    return (SimpleNamespace(effector=effector, args=args),
            SimpleNamespace(ok=True, refused=False, pending=False, error=None, result="[no such path]"))


def test_capped_explore_says_the_next_step_was_not_done():
    explore = SimpleNamespace(trace=[_act(path="scratch/chat_handler.py")], reply="", capped=True)
    text = H._beat_record_text(explore, None)
    assert "step limit" in text and "NOT done" in text
    assert text.index("memory_read") < text.index("step limit")


def test_uncapped_beat_is_unchanged():
    explore = SimpleNamespace(trace=[_act(path="x")], reply="", capped=False)
    assert "step limit" not in H._beat_record_text(explore, None)
    assert H._capped_line(SimpleNamespace(trace=[], reply="")) == ""


def test_capped_with_no_tools_still_says_it():
    text = H._beat_record_text(SimpleNamespace(trace=[], reply="", capped=True))
    assert text.startswith("You called no tools this beat.") and "step limit" in text


def test_non_bool_capped_does_not_trigger():
    # A mock or unset attribute must not invent a cap.
    assert H._capped_line(SimpleNamespace(trace=[], capped="yes")) == ""
