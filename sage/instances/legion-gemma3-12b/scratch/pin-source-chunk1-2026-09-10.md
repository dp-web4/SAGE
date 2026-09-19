# test_context_fit.py lines 1–30 (worktree being-worktrees/legion-being, read 2026-09-10 ~20:4xZ)

Docstring: fixed prompt can overflow the window on its own; fit_to_window cannot help then. Legion 2026-09-08 15:42Z–19:22Z: config.context_overcommitted True on eight beats running (headroom -2.4k..-4k tokens), digest and recall at floors, conversations block 30.9k chars; every explore generate: prompt_eval + eval == num_ctx, done_reason length, zero tool calls.

IMPORTS (pin TODO(a) resolved): `from sage.gateway.heartbeat import fit_state, window_budget_chars, CONV_LADDER, CPT`

DEFS seen so far in this chunk:
- `_build_factory(sizes)` — helper; build(per_conv, turn_chars) -> "c" * sizes[(per_conv, turn_chars)], records calls list.
- `test_budget_is_one_producer` — window_budget_chars(24576, 8000) == int((24576 - 6144 - 512) * CPT); (24576, 3000): reserve never exceeds num_predict; (1000, 8000) == 0.
- `test_full_display_when_it_fits` — sizes = {r: 10_000 for r in CONV_LADDER}; fit_state(build, num_ctx=24576, num_predict=8000, other_chars=20_000) -> rung == CONV_LADDER[0], iv is None, calls == [CONV_LADDER[0]].

fit_state signature observed: fit_state(build, *, num_ctx, num_predict, other_chars) -> (text, rung, iv).
window_budget_chars(num_ctx, num_predict) — reserve = min(6144?, num_predict); budget 0 when window too small.
