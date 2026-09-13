# Base test_context_fit.py — facts, chunk 2 (lines 41–65 of 92) @ cc64c838c

Read 2026-09-10 ~17:57Z. Elided middle not visible; these are the visible facts.

Tail of test_steps_down_until_it_fits_and_says_what_it_suppressed (lines 41–45):
    assert rung == CONV_LADDER[2]                        # first rung that fits, not the sparsest
    assert calls == list(CONV_LADDER[:3])
    assert iv["kind"] == "context_fit" and iv["block"] == "conversations"
    assert "16900 chars of conversations" in iv["suppressed"] and "last 6 turns" in iv["suppressed"]
    assert "fits now" in iv["reason"] and "68900 chars" in iv["reason"]

test_sparsest_rung_is_used_and_named_when_nothing_fits: sizes={r:50_000 for r in CONV_LADDER}; asserts rung==CONV_LADDER[-1], calls==list(CONV_LADDER), "STILL does not fit" in iv["reason"]

test_unknown_window_means_full_display: build with {CONV_LADDER[0]:1}; num_ctx=None -> rung==CONV_LADDER[0] and iv is None

Section header comment (line ~62): "# -- the next-wake check must not be false by construction -----------------------------"

test_a_running_beat_does_not_read_as_an_unarmed_timer: docstring begins "2026-09-09T15:07Z: the end-of-beat check read `monotonic=infinity` and wrote..." (rest elided)
