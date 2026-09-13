# test_context_fit.py lines 31–60 (worktree being-worktrees/legion-being, read 2026-09-10 ~20:4xZ)

DEFS in this chunk:
- `test_steps_down_until_it_fits_and_says_what_it_suppressed` — the measured case: conversations 30.9k + other 38k, budget = window_budget_chars(24576, 8000) (~60.9k). fit_state -> rung == CONV_LADDER[2] ("first rung that fits, not the sparsest"); calls == list(CONV_LADDER[:3]); iv["kind"]=="context_fit", iv["block"]=="conversations"; suppressed names "16900 chars of conversations" and "last 6 turns"; reason contains "fits now" and "68900 chars".
- `test_sparsest_rung_is_used_and_named_when_nothing_fits` — all rungs 50k -> rung == CONV_LADDER[-1], calls == full ladder, iv["reason"] contains "STILL does not fit".
- `test_unknown_window_means_full_display` — num_ctx=None -> rung == CONV_LADDER[0], iv is None.

Pin-relevant facts:
- P2 (beat-scoped max) is NOT in this file's visible tests so far; the base-suite test named in my clean-base record is test_beat_scoped_max_is_used_not_all_time_worst — must locate which module it lives in (heartbeat.py? another test file?) before pinning against it.
- P3 floor: window_budget_chars(1000, 8000) == 0 (chunk 1) — budget clamps to 0; headroom clamp >= 0 still [S] until _fill_headroom body read.
- P4 window-not-budget: fit_state takes num_ctx explicitly and derives budget via window_budget_chars(num_ctx, num_predict) — supports the pin at spec level now (upgrade to [V]-line-cited once heartbeat.py side is cited).
