"""A settled conversation MAY be shown short -- opt-in per instance, and never silently (#265).

GPT's hold on #265: (1) RESEARCH_GENERALIZATION_RULE -- measured on legion-being only, so it is an
instance setting, and the default rendering is unchanged; (2) "my last word is here and nothing is
waiting" is not "nothing is owed": a being that answered "still working on your questions" has open
questions above its last word. The collapse is therefore said, with the assumption and the path.
"""
import tempfile
from pathlib import Path

from sage.gateway import conversations as conv
from sage.gateway.heartbeat import settled_turns_for

ME, SEAT = "legion-being", "legion-claude"


def _home(turns):
    h = Path(tempfile.mkdtemp())
    conv.create(h, "c", title="t", participants=[SEAT, ME], writable_by=[SEAT, ME])
    for who, text in turns:
        conv.append(h, "c", speaker=who, text=text)
    return h


SETTLED = [(SEAT if i % 2 else ME, f"turn number {i}") for i in range(10)] + [(ME, "my last word")]


def test_the_default_rendering_is_unchanged():
    out = conv.render_for_being(_home(SETTLED), ME, per_conv=6, mark=False)
    assert "turn number 5" in out and "not shown" not in out


def test_opted_in_a_settled_conversation_is_short_and_says_what_it_assumed():
    out = conv.render_for_being(_home(SETTLED), ME, per_conv=6, mark=False, settled_turns=2)
    assert "my last word" in out and "turn number 9" in out and "turn number 8" not in out
    assert "4 earlier turn(s) of the recent window are not shown" in out
    assert "That is an assumption" in out and "memory_read conversations/c.jsonl" in out


def test_seen_but_unresolved_questions_are_named_as_possibly_open():
    """GPT's control: five seen questions, then the being: 'still working on your questions'."""
    turns = [(SEAT, f"question {i}?") for i in range(5)] + [(ME, "I am still working on your questions, no answers yet")]
    h = _home(turns)
    assert conv.awaiting(h, "c", ME) == [], "nothing is 'waiting' in the store's sense"
    out = conv.render_for_being(h, ME, per_conv=6, mark=False, settled_turns=2)
    assert "question 1?" not in out, "the collapse did drop them..."
    assert "if an earlier turn asked you something you have not finished" in out, "...and said so"
    assert "question 1?" in conv.render_for_being(h, ME, per_conv=6, mark=False), "default keeps them"


def test_a_waiting_conversation_is_never_collapsed():
    h = _home(SETTLED[:-1] + [(SEAT, "a question for you?")])
    out = conv.render_for_being(h, ME, per_conv=6, mark=False, settled_turns=2)
    assert "a question for you?" in out and "turn number 5" in out and "not shown" not in out


def test_the_instance_setting_is_validated():
    assert settled_turns_for({}) is None and settled_turns_for(None) is None
    assert settled_turns_for({"conversation_settled_turns": 2}) == 2
    for bad in (0, -1, True, "2", 1.5):
        assert settled_turns_for({"conversation_settled_turns": bad}) is None, bad
