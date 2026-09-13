# test_context_fit.py lines 61–92 + FULL def enumeration (worktree being-worktrees/legion-being, read 2026-09-10 ~20:4xZ)

Chunk 3 content: section header "the next-wake check must not be false by construction".
- `test_a_running_beat_does_not_read_as_an_unarmed_timer` — imports interpret_timer_state from sage.gateway.heartbeat (local import inside test). Cases: running beat (NextElapseUSecMonotonic=infinity, ActiveState=active) -> armed True, why contains "correct while this beat is still running"; scheduled (realtime set, monotonic infinity) -> armed True, why.startswith("scheduled:"); dead timers (LoadState not-found / failed / inactive) -> armed False, why contains "not healthy". Origin: 2026-09-09T15:07Z false-negative incident.

FULL def-name enumeration of restored test_context_fit.py (shadowing check input):
_build_factory | test_budget_is_one_producer | test_full_display_when_it_fits | test_steps_down_until_it_fits_and_says_what_suppressed... exact: test_steps_down_until_it_fits_and_says_what_it_suppressed | test_sparsest_rung_is_used_and_named_when_nothing_fits | test_unknown_window_means_full_display | test_a_running_beat_does_not_read_as_an_unarmed_timer

SHADOWING CHECK (vs my pin names in scratch/pins-2026-09-10.md): test_p1_fill_headroom_is_defined, test_p3_headroom_shape_floor, test_p5_fill_is_plain_function, test_p6_base_suite_stays_present — NO collisions. Shadowing check PASSES; pins go in a NEW file sage/gateway/tests/test_context_fit_pins.py.

STILL MISSING for pin upgrade: (a) _fill_headroom body from heartbeat.py at line-cited ranges (next beat's interleaved reads); (b) which module holds test_beat_scoped_max_is_used_not_all_time_worst — NOT in this file; locate via grep-equivalent read of heartbeat.py or another tests/ file before pinning P2 against it.
