"""A settled conversation is shown short; an unanswered one is untouched (2026-09-29).

legion-being: 7,255 of a 27,009-char state was two settled conversations, re-rendered six turns
each, every beat, in a prompt that opened at 15k of 24.5k tokens and hit the window every beat.
"""
import tempfile
from pathlib import Path

from sage.gateway import conversations as conv

ME, SEAT = "legion-being", "legion-claude"


def _home(turns):
    h = Path(tempfile.mkdtemp())
    conv.create(h, "c", title="t", participants=[SEAT, ME], writable_by=[SEAT, ME])
    for who, text in turns:
        conv.append(h, "c", speaker=who, text=text)
    return h


def test_settled_shows_only_the_last_turns_and_says_how_many_there_are():
    h = _home([(SEAT if i % 2 else ME, f"turn number {i}") for i in range(10)] + [(ME, "my last word")])
    out = conv.render_for_being(h, ME, per_conv=6, mark=False)
    assert "my last word" in out and "turn number 9" in out
    assert "turn number 8" not in out, "a settled conversation shows only its last SETTLED_TURNS"
    assert f"showing the last {conv.SETTLED_TURNS} of 11 turns" in out


def test_a_conversation_waiting_on_the_being_keeps_its_context():
    h = _home([(SEAT if i % 2 else ME, f"turn number {i}") for i in range(10)] + [(SEAT, "a question for you?")])
    out = conv.render_for_being(h, ME, per_conv=6, mark=False)
    assert "a question for you?" in out and "turn number 5" in out, "unanswered: full recent context"
