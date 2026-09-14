"""The fixed prompt can overflow the window on its own; fit_to_window cannot help then.

Legion 2026-09-08 15:42Z-19:22Z: config.context_overcommitted True on eight beats running
(headroom -2.4k..-4k tokens), digest and recall already at their floors, the conversations
block 30.9k chars. Every explore generate: prompt_eval + eval == num_ctx, done_reason
length, zero tool calls. The instrument reported it every beat; nothing acted on it."""
from sage.gateway.heartbeat import fit_state, window_budget_chars, CONV_LADDER, CPT


def _build_factory(sizes):
    """build(per_conv, turn_chars) -> text whose length is sizes[rung]"""
    calls = []

    def build(per_conv, turn_chars):
        calls.append((per_conv, turn_chars))
        return "c" * sizes[(per_conv, turn_chars)]
    return build, calls


def test_budget_is_one_producer():
    assert window_budget_chars(24576, 8000) == int((24576 - 6144 - 512) * CPT)
    assert window_budget_chars(24576, 3000) == int((24576 - 3000 - 512) * CPT)   # reserve never exceeds num_predict
    assert window_budget_chars(1000, 8000) == 0


def test_full_display_when_it_fits():
    sizes = {r: 10_000 for r in CONV_LADDER}
    build, calls = _build_factory(sizes)
    text, rung, iv = fit_state(build, num_ctx=24576, num_predict=8000, other_chars=20_000)
    assert rung == CONV_LADDER[0] and iv is None and calls == [CONV_LADDER[0]]


def test_steps_down_until_it_fits_and_says_what_it_suppressed():
    """The measured case: 30.9k of conversations, 38k of everything else.

    ASSERTS THE INVARIANT, NOT AN INDEX. This pinned `rung == CONV_LADDER[2]` and a literal
    "16900 chars" — both of which are arithmetic on CPT, not statements about the ladder.
    When CPT moved 3.4 -> 2.9 on 2026-09-13 (it had been sitting ABOVE the true ratio for
    five days, over-admitting) the budget tightened, the fitter correctly stepped one rung
    further, and this test went red for doing the right thing. A pin that fails when a
    constant is corrected is measuring the constant."""
    budget = window_budget_chars(24576, 8000)
    sizes = {CONV_LADDER[0]: 30_900, CONV_LADDER[1]: 24_000, CONV_LADDER[2]: 14_000,
             CONV_LADDER[3]: 9_000, CONV_LADDER[4]: 6_000}
    build, calls = _build_factory(sizes)
    text, rung, iv = fit_state(build, num_ctx=24576, num_predict=8000, other_chars=38_000)

    # it fits
    assert 38_000 + len(text) <= budget
    # and it is the FIRST rung that fits — every rung above it would not have
    idx = CONV_LADDER.index(rung)
    assert 38_000 + sizes[rung] <= budget
    for earlier in CONV_LADDER[:idx]:
        assert 38_000 + sizes[earlier] > budget, f"{earlier} fits; the fitter should have stopped there"
    # it tried them in order and stopped at the first success
    assert calls == list(CONV_LADDER[:idx + 1])

    # and it says what it gave up, in the ladder's own terms
    assert iv["kind"] == "context_fit" and iv["block"] == "conversations"
    assert f"{sizes[CONV_LADDER[0]] - sizes[rung]} chars of conversations" in iv["suppressed"]
    assert f"last {rung[0]} turns" in iv["suppressed"]
    assert "fits now" in iv["reason"]


def test_sparsest_rung_is_used_and_named_when_nothing_fits():
    sizes = {r: 50_000 for r in CONV_LADDER}
    build, calls = _build_factory(sizes)
    text, rung, iv = fit_state(build, num_ctx=24576, num_predict=8000, other_chars=38_000)
    assert rung == CONV_LADDER[-1] and calls == list(CONV_LADDER)
    assert "STILL does not fit" in iv["reason"]


def test_unknown_window_means_full_display():
    build, calls = _build_factory({CONV_LADDER[0]: 1})
    text, rung, iv = fit_state(build, num_ctx=None, num_predict=8000, other_chars=0)
    assert rung == CONV_LADDER[0] and iv is None



# -- the next-wake check must not be false by construction -----------------------------

def test_the_tool_schemas_are_measured_not_budgeted():
    """`fixed_other` was a flat 4,000 chars for "tool schemas + chat template", set when the
    being had 13 verbs and never revisited. Measured 2026-09-13 at 18 verbs: the explore
    schema JSON alone is 11,717 chars — 7,717 more than budgeted, ~2,600 tokens of a 24,576
    window the fitter did not know it was spending. Every verb added made it worse, and a
    budget is a promise the code makes to itself and never checks."""
    import json
    from sage.gateway.heartbeat import _schema_chars_for, EXPLORE_TOOLS
    from sage.gateway.being_gate_client import ollama_tools
    from pathlib import Path

    n = _schema_chars_for(EXPLORE_TOOLS)
    assert n == len(json.dumps(ollama_tools(EXPLORE_TOOLS)))
    assert n > 4000, "the old budget; if the schemas ever fit in it again, say so deliberately"

    # it GROWS with the verb set — that is the property the constant could not have
    fewer = _schema_chars_for(EXPLORE_TOOLS[:4])
    assert 0 < fewer < n, "a smaller offered set must cost fewer chars"

    assert _schema_chars_for([]) is None and _schema_chars_for(None) is None

    # (the _config_check coupling is asserted on the branch where that function
    #  lives; it is the beat-record builder, not part of this slice.)


    # THE FITTER MUST USE THE SAME NUMBER. Pinning the helper alone left the fitter free to
    # go back to a constant — a mutation replacing its call with 4000 passed everything.
    # One source of truth, asserted at the source: main() must not compute this itself.
    import inspect
    from sage.gateway import heartbeat as hb
    body = inspect.getsource(hb.main)
    assert "_schema_chars_for(EXPLORE_TOOLS)" in body, \
        "the fitter must call the same helper the record does"
    assert "len(json.dumps(ollama_tools(" not in body, \
        "main() is recomputing the schema size instead of using the helper"


def test_the_compaction_log_reaches_the_result_and_the_fallbacks_match_the_evidence():
    """Two of GPT's findings on #82, pinned.

    (1) `compacted` was accumulated in a local list and never copied onto the returned
    result, so the intervention was invisible in the beat record — an instrument nobody can
    read is not an instrument. My first fix attached it inside `run_tool_turn`, which does
    not define the name: a NameError the suite would not have caught, because the attachment
    only runs on a path the tests reach through a fake.

    (2) The loop's fallbacks were left at `_CPT = 3.4` and `_UNCOUNTED_CHARS = 4000` — the
    two numbers this PR's own evidence disproves — and `_est_tokens(measured=None)` consumes
    exactly those. The fallback is reached precisely when nothing has been measured yet."""
    from types import SimpleNamespace
    from sage.gateway.being_tool_loop import (run_ollama_tool_turn, _est_tokens,
                                              _CPT, _UNCOUNTED_CHARS)
    from sage.gateway.being_gate_client import BeingGateClient

    # (2) the fallbacks agree with the seed-side correction
    assert _CPT <= 2.9, "must sit below the measured 3.026-3.141 range, not above it"
    assert _UNCOUNTED_CHARS > 4000, "4,000 was set at 13 verbs; the schemas measure 11,717"
    # and the no-measurement path actually uses them
    naive = _est_tokens(10_000, None)
    assert naive == (10_000 + _UNCOUNTED_CHARS) / _CPT
    anchored = _est_tokens(10_000, (2_000, 9_000))
    assert anchored != naive, "with a server count the estimate must not ride the fallback"

    # (1) the compaction log reaches the caller
    class LLM:
        num_ctx = 4096          # small enough that compaction must act
        def get_chat_response(self, messages, tools=None):
            return {"content": "done", "tool_calls": [],
                    "raw": {"prompt_eval_count": 3000, "eval_count": 5}}

    seed = [{"role": "user", "content": "go"}]
    for i in range(6):
        seed.append({"role": "assistant", "content": f"step {i}"})
        seed.append({"role": "tool", "effector": "memory_read", "content": "R" * 3000})

    c = BeingGateClient.__new__(BeingGateClient)
    res = run_ollama_tool_turn(c, LLM(), seed, max_steps=1, tools=[])
    assert res.compacted, "the compaction log must reach the result, not die in a local"
    assert all("chars" in e and "elisions" in e for e in res.compacted)


def test_unmeasurable_schemas_degrade_conservative_never_back_to_4000():
    """A measurement failure must cost the being window, not hand it back.

    GPT's second pass on SAGE#82: `_schema_chars_for(...) or 4000` reintroduced, on the
    measurement-failed path exactly, the 13-verb constant this slice exists to retire. The
    real cost at 18 verbs is 11,717 chars, so `or 4000` understates by ~7,700 chars a beat
    precisely when the seat already knows it cannot see. Too large steps the conversation
    ladder down a rung; too small puts the beat over the wall with nothing saying so.
    """
    from sage.gateway import heartbeat as H

    # Unmeasurable: _schema_chars_for says None rather than guessing.
    assert H._schema_chars_for(None) is None
    assert H._schema_chars_for([]) is None

    # And the fallback every caller must route None through is conservative.
    eighteen = [f"verb_{i}" for i in range(18)]
    assert H._schema_chars_fallback(eighteen) >= 11_717, \
        "the fallback must not sit below the largest real measurement"
    assert H._schema_chars_fallback(None) >= H._SCHEMA_CHARS_FLOOR
    assert H._schema_chars_fallback([]) >= H._SCHEMA_CHARS_FLOOR

    # It scales with the registry rather than sitting at a constant that rots.
    assert H._schema_chars_fallback([f"v{i}" for i in range(40)]) > \
           H._schema_chars_fallback(eighteen), \
        "a per-verb bound must grow with the verb count; a constant is what rotted before"

    # The specific regression: no path may yield the retired constant.
    for offered in (None, [], eighteen, [f"v{i}" for i in range(13)]):
        assert H._schema_chars_fallback(offered) != 4000, \
            f"4000 came back for offered={offered!r}"


def test_schema_chars_measured_when_the_registry_is_readable():
    """The fallback is the degraded path, so the measured path must actually be taken."""
    from sage.gateway import heartbeat as H
    measured = H._schema_chars_for(H.EXPLORE_TOOLS)
    assert isinstance(measured, int) and measured > 0, \
        "EXPLORE_TOOLS must be measurable here, or the test above is measuring nothing"
    # The measurement is the real cost; it should be nowhere near the retired guess.
    assert measured > 4000, f"schemas measured at {measured}, below the constant that rotted"
