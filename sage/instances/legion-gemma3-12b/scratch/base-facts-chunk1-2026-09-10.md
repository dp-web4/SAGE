# Base test_context_fit.py — facts, chunk 1 (lines 1–40 of 92) @ cc64c838c

Read 2026-09-10 ~17:55Z. Middle elided by harness; these are the visible facts, recorded same beat per standing rule.

Module docstring: fixed prompt can overflow window on its own; fit_to_window cannot help then. Incident: Legion 2026-09-08 15:42Z-19:22Z, config.context_overcommitted True eight beats running (headroom -2.4k..-4k tokens), digest+recall at floors, conversations block 30.9k chars; every explore generate: prompt_eval + eval == num_ctx, done_reason length, zero tool calls.

Imports: `from sage.gateway.heartbeat import fit_state, window_budget_chars, CONV_LADDER, CPT`

Helpers/defs in chunk 1:
- `_build_factory(sizes)` -> (build, calls); build(per_conv, turn_chars) appends the pair to calls and returns "c" * sizes[(per_conv, turn_chars)]
- `test_budget_is_one_producer`: window_budget_chars(24576,8000)==int((24576-6144-512)*CPT); (24576,3000)==int((24576-3000-512)*CPT) with comment "reserve never exceeds num_predict"; window_budget_chars(1000,8000)==0
- `test_full_display_when_it_fits`: sizes={r:10_000 for r in CONV_LADDER}; fit_state(build, 24576, 8000, other=20_000) -> rung==CONV_LADDER[0], iv is None, calls==[CONV_LADDER[0]]
- `test_steps_down_until_it_fits_and_says_what_it_suppressed`: docstring "The measured case: 30.9k of conversations, 38k of everything else, 60.9k budget."; sizes CONV_LADDER[0]:30_900, [1]:24_000, [2]:14_000, [3]:9_000, [4]:6_000; asserts 38_000+len(text)<=budget (rest elided)
