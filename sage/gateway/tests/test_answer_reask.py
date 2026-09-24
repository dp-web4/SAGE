"""Hermetic: an answer written in the text channel gets one more chance to be said.

Measured on Sprout 2026-09-23, on both turns dp sent that evening. The answer turn offers
exactly one tool (`say`) and asks for exactly one thing, and the model replied in prose:

    22:34Z  reply "And for today, I'm just here to hear you out."   trace []  -> nothing sent
    23:06Z  reply "What's on your mind?"                            trace []  -> nothing sent

Neither is deliberation; both are addressed messages. The 23:06Z thinking block reads "I need
to choose whether to reply or end with silence" — it chose to reply, and the reply reached
nobody. dp, reading the conversation from outside, saw a being that reached out and then
declined to continue. That is the legibility 2.6 failure on our own side: an unreadable
envelope is not an absence of intent.

The remedy is NOT to salvage the prose into a say. The ask offers silence as a real choice, so
prose there is genuinely ambiguous — a message, or the being reasoning about whether to send
one — and shipping the second kind would put private deliberation into someone's inbox under
the being's name. So it is asked once more with its own words quoted back, and it decides.
"""
import os
import sys
import types

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.heartbeat import ANSWER_REASK  # noqa: E402


def test_the_reask_quotes_the_beings_words_and_keeps_both_doors_open():
    out = ANSWER_REASK.format(target="dp", prose="What's on your mind?")
    assert "What's on your mind?" in out, "it must quote the being's OWN words, not paraphrase"
    assert "Nothing was sent" in out, "the being must learn the words did not arrive"
    assert "call say now" in out and "to set to dp" in out, "the way to send it is named"
    assert "call nothing" in out, "silence stays available — the harness must not decide for it"
    assert 'text="' not in out, (
        "no slot: an ask with a template in it gets the template back (26% of turns, 2026-09-18)")


def test_prose_in_the_answer_turn_is_not_delivered_as_a_say():
    """The harness never speaks for the being. Prose is re-asked, never forwarded."""
    import inspect
    from sage.gateway import heartbeat as hb
    src = inspect.getsource(hb.main)
    i = src.index("THE ANSWER WRITTEN IN THE WRONG CHANNEL")
    block = src[i:i + 3000]
    assert "ANSWER_REASK" in block, "the remedy is a re-ask"
    assert "hestia_dispatch" not in block and 'BeingIntent("say"' not in block, \
        "the harness must not construct a say out of the being's prose"
    assert "_no_think" in block, (
        "the re-ask must have thinking off: same prompt + more room makes this model "
        "deliberate again rather than act (#191)")


def test_a_silent_answer_turn_is_left_silent():
    """No reply, no re-ask. Silence that was actually chosen stays chosen."""
    import inspect
    from sage.gateway import heartbeat as hb
    src = inspect.getsource(hb.main)
    i = src.index("if answer is not None and not _said_in(answer)")
    cond = src[i:src.index("\n", i)]
    assert 'getattr(answer, "reply", "") or ""' in cond and ".strip()" in cond, \
        "the re-ask must be gated on there being prose at all"


def test_a_successful_reask_is_recorded_as_one():
    """A beat that reads as a clean answer would hide the defect it worked around."""
    import inspect
    from sage.gateway import heartbeat as hb
    src = inspect.getsource(hb.main)
    i = src.index("THE ANSWER WRITTEN IN THE WRONG CHANNEL")
    block = src[i:i + 3000]
    assert '"form": "answer-reask"' in block, "the record must show a re-ask was needed"
    assert "salvaged.append" in block, "it rides the same channel as every other intervention"


def test_said_in_still_refuses_to_call_prose_speaking():
    """The premise the whole turn rests on: composing is not saying."""
    from sage.gateway.heartbeat import _said_in
    ok = types.SimpleNamespace(ok=True)
    bad = types.SimpleNamespace(ok=False)
    say = types.SimpleNamespace(effector="say")
    other = types.SimpleNamespace(effector="memory_write")
    assert _said_in(types.SimpleNamespace(trace=[(say, ok)])) is True
    assert _said_in(types.SimpleNamespace(trace=[(say, bad)])) is False, "a refused say is not speech"
    assert _said_in(types.SimpleNamespace(trace=[(other, ok)])) is False
    assert _said_in(None) is False
