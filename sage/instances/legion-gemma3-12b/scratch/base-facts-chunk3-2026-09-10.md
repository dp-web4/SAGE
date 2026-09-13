# Base test_context_fit.py — facts, chunk 3 (lines 66–92 of 92) @ cc64c838c

Read 2026-09-10 ~17:58Z. This is the final range; file ends at line 92.

test_a_running_beat_does_not_read_as_an_unarmed_timer (continued from chunk 2):
Docstring tail: "...NOTHING WILL WAKE THE BEING into the record of a beat whose timer armed correctly seconds later. An OnUnitInactiveSec timer CANNOT have a next elapse while the unit it watches is running — and this check runs from inside that unit."

Body (verbatim, lines 69–92):
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

# GROUND TRUTH — all definitions in base file (92 lines), verified by range reads 1-40/41-65/66-92 this beat:
1. _build_factory            (helper)
2. test_budget_is_one_producer
3. test_full_display_when_it_fits
4. test_steps_down_until_it_fits_and_says_what_it_suppressed
5. test_sparsest_rung_is_used_and_named_when_nothing_fits
6. test_unknown_window_means_full_display
7. test_a_running_beat_does_not_read_as_an_unarmed_timer

Six tests + one helper = 7 defs. No def visible in elided middles (elisions were mid-test-body, between visible lines).
