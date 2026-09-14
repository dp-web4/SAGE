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
def test_a_running_beat_does_not_read_as_an_unarmed_timer():
    """2026-09-09T15:07Z: the end-of-beat check read `monotonic=infinity` and wrote
    "NOTHING WILL WAKE THE BEING" into the record of a beat whose timer armed correctly
    seconds later. An OnUnitInactiveSec timer CANNOT have a next elapse while the unit it
    watches is running — and this check runs from inside that unit."""
    from sage.gateway.heartbeat import interpret_timer_state

    running = ("NextElapseUSecRealtime=\n"
               "NextElapseUSecMonotonic=infinity\n"
               "LoadState=loaded\nActiveState=active\n")
    armed, why = interpret_timer_state(running)
    assert armed is True, why
    assert "correct while this beat is still running" in why

    scheduled = ("NextElapseUSecRealtime=Wed 2026-09-09 09:03:39 PDT\n"
                 "NextElapseUSecMonotonic=infinity\nLoadState=loaded\nActiveState=active\n")
    armed, why = interpret_timer_state(scheduled)
    assert armed is True and why.startswith("scheduled:")

    # the real failure this exists for: the timer is gone or dead, not merely unscheduled
    for bad in ("NextElapseUSecRealtime=\nNextElapseUSecMonotonic=infinity\n"
                "LoadState=not-found\nActiveState=inactive\n",
                "NextElapseUSecRealtime=\nNextElapseUSecMonotonic=infinity\n"
                "LoadState=loaded\nActiveState=failed\n",
                "NextElapseUSecRealtime=\nNextElapseUSecMonotonic=infinity\n"
                "LoadState=loaded\nActiveState=inactive\n"):
        armed, why = interpret_timer_state(bad)
        assert armed is False, why
        assert "not healthy" in why


def test_the_tool_schemas_are_measured_not_budgeted():
    """`fixed_other` was a flat 4,000 chars for "tool schemas + chat template", set when the
    being had 13 verbs and never revisited. Measured 2026-09-13 at 18 verbs: the explore
    schema JSON alone is 11,717 chars — 7,717 more than budgeted, ~2,600 tokens of a 24,576
    window the fitter did not know it was spending. Every verb added made it worse, and a
    budget is a promise the code makes to itself and never checks."""
    import json
    from sage.gateway.heartbeat import _schema_chars_for, EXPLORE_TOOLS, _config_check
    from sage.gateway.being_gate_client import ollama_tools
    from pathlib import Path
    from types import SimpleNamespace

    n = _schema_chars_for(EXPLORE_TOOLS)
    assert n == len(json.dumps(ollama_tools(EXPLORE_TOOLS)))
    assert n > 4000, "the old budget; if the schemas ever fit in it again, say so deliberately"

    # it GROWS with the verb set — that is the property the constant could not have
    fewer = _schema_chars_for(EXPLORE_TOOLS[:4])
    assert 0 < fewer < n, "a smaller offered set must cost fewer chars"

    assert _schema_chars_for([]) is None and _schema_chars_for(None) is None

    # and _config_check must actually RUN. ollama_tools is imported inside main(), which
    # binds it as a local there; referencing it from _config_check NameErrors at runtime,
    # and no test called _config_check, so nothing would have caught it.
    c = _config_check(Path("."), "m", SimpleNamespace(num_ctx=24576), EXPLORE_TOOLS)
    assert c["tool_schema_chars"] == n

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
