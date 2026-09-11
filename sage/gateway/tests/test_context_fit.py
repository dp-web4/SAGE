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
    """The measured case: 30.9k of conversations, 38k of everything else, 60.9k budget."""
    budget = window_budget_chars(24576, 8000)
    sizes = {CONV_LADDER[0]: 30_900, CONV_LADDER[1]: 24_000, CONV_LADDER[2]: 14_000,
             CONV_LADDER[3]: 9_000, CONV_LADDER[4]: 6_000}
    build, calls = _build_factory(sizes)
    text, rung, iv = fit_state(build, num_ctx=24576, num_predict=8000, other_chars=38_000)
    assert 38_000 + len(text) <= budget
    assert rung == CONV_LADDER[2]                        # first rung that fits, not the sparsest
    assert calls == list(CONV_LADDER[:3])
    assert iv["kind"] == "context_fit" and iv["block"] == "conversations"
    assert "16900 chars of conversations" in iv["suppressed"] and "last 6 turns" in iv["suppressed"]
    assert "fits now" in iv["reason"] and "68900 chars" in iv["reason"]


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
