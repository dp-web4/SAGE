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
from sage.gateway.heartbeat import ANSWER_REASK, ANSWER_REASK_PLACEHOLDER  # noqa: E402


def _reask_block() -> str:
    """The re-ask block as written, from its banner to the line that ends it.

    Anchored to a marker rather than a character count: a fixed window silently stops
    covering the code it is meant to assert about as soon as anyone adds a comment, which is
    how these assertions passed and then failed within one edit.
    """
    import inspect
    from sage.gateway import heartbeat as hb
    src = inspect.getsource(hb.main)
    i = src.index("THE ANSWER WRITTEN IN THE WRONG CHANNEL")
    return src[i:src.index("interventions = []", i)]


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
    block = _reask_block()
    assert "ANSWER_REASK" in block, "the remedy is a re-ask"
    assert "hestia_dispatch" not in block and 'BeingIntent("say"' not in block, \
        "the harness must not construct a say out of the being's prose"
    assert "_no_think" in block, (
        "the re-ask must have thinking off: same prompt + more room makes this model "
        "deliberate again rather than act (#191)")


def test_a_silent_answer_turn_is_left_silent():
    """No reply, no re-ask. Silence that was actually chosen stays chosen."""
    cond = _reask_block()
    assert 'getattr(answer, "reply", "") or ""' in cond and ".strip()" in cond, \
        "the re-ask must be gated on there being prose at all"


def test_a_successful_reask_is_recorded_as_one():
    """A beat that reads as a clean answer would hide the defect it worked around."""
    block = _reask_block()
    assert "answer-reask" in block and '"form"' in block, "the record must show a re-ask was needed"
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


def test_a_template_gets_its_own_reask_that_does_not_quote_it():
    """63% of answer-phase turns are a bracketed template (26 of 41, Sprout to 2026-09-24);
    only 7% reached the person. A template is not a message, so it is never quoted back as the
    being's words — but it is not silence either, and treating it as silence is what left dp's
    direct question unanswered for three beats. It gets its own re-ask, in the wording the
    `say` gate already uses for this exact defect, because that refusal is MEASURED to work:
    at 01:48:54Z the gate refused a placeholder say with it and the being then wrote the real
    message (seq 40).
    """
    out = ANSWER_REASK_PLACEHOLDER.format(target="dp")
    assert "placeholder describing a message rather than the message" in out, \
        "the proven sentence, not a new one"
    assert "nothing was sent" in out
    assert "Write the words you want read" in out and "to set to dp" in out
    assert "call nothing" in out, "silence stays a real choice"
    assert "[" not in out and 'text="' not in out, "no template in an anti-template ask"
    # and it never contains the being's placeholder text: there is nothing to quote
    assert "{prose}" not in out and "prose" not in out


def test_a_bracketed_template_is_never_quoted_back_as_the_beings_words():
    """Measured on Sprout 2026-09-24, beat 00:44:58Z: the answer turn said the right thing
    natively AND left "[Your complete, well-structured response following the established
    conversation flow and tone]" in its text channel — the template this model returns
    whenever it is shown a slot. Quoting one back would ask the being to confirm words it
    never wrote as its own: the exact thing this branch exists to avoid.
    """
    from sage.gateway.heartbeat import _bracketed_stage_direction as bsd
    assert bsd("[Your complete, well-structured response following the established "
               "conversation flow and tone]") is True
    assert bsd("  [Your complete, thoughtful journal entry responding to dp's question]  ") is True
    # real answers, including terse ones, are NOT templates
    assert bsd("What's on your mind?") is False
    assert bsd("And for today, I'm just here to hear you out.") is False
    assert bsd("Yes — see you then.") is False, \
        "a terse reply is still an answer; being_join._placeholder's <20 rule is wrong here"
    assert bsd("") is False and bsd(None) is False
    # not a single span: the being quoting something in brackets mid-message is real text
    assert bsd("[a] and then [b]") is False
    assert bsd("I read [the note] and I agree.") is False


def test_the_two_reasks_are_chosen_by_the_template_check():
    cond = _reask_block()
    assert "_bracketed_stage_direction" in cond, "the shape decides which ask is sent"
    assert "ANSWER_REASK_PLACEHOLDER" in cond and "ANSWER_REASK.format" in cond, \
        "both doors exist: quote the prose, or name the placeholder"
    assert "answer-reask-placeholder" in cond, \
        "the record must distinguish which defect was worked around"
