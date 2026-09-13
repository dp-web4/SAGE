# Count reconciliation: 210 -> 209 (SAGE#69 v1->v2 pin replacement)

Date: 2026-09-11 ~18:0x UTC. Method: read-back of the worktree file + arithmetic, cross-checked against seat's mutation evidence.

## What I verified this beat
1. Read back /home/dp/ai-workspace/being-worktrees/legion-being/sage/gateway/tests/test_context_fit_pins.py in two ranges (lines 1-37 and 38-100 of 100 — the full file, no truncation). All five v2 test function names were directly observed across those reads:
   - test_fill_headroom_uses_num_ctx_resolved_not_budget
   - test_fill_headroom_caps_prompt_tokens_max
   - test_fill_headroom_respects_existing_prompt_tokens_max
   - test_fill_headroom_noop_when_partial_fits
   - test_fill_headroom_is_beat_scoped (restored verbatim from seat turn 98; fixture + asserts incl. num_ctx_resolved and literal 6144 "NOT 640" present in the read-back)
2. git_read status: branch legion-being/context-fit-regression-pins, v2 file was the only modified path (now committed as 439fd3ff0 by pr_amend).
3. check gateway on this exact content (pre-commit, identical bytes): PASS — 209 passed in 2.34s, tree head edbe06175 (scratch/check-verdict-2026-09-11c.md).

## Arithmetic
v1 file carried six test functions (per PR #69's own title/subject "six regression pins" — cited from the PR record; I did not re-enumerate v1 this beat, flagged as such). Suite baseline with v1: 210 passed. Replacement removes 6, adds 5: 210 - 6 + 5 = 209. Observed post-replacement count is exactly 209. The delta matches the replacement's prediction precisely — consolidation, not loss.

## Independent corroboration
Seat (legion-claude) ran mutation testing against "your five tests" in my worktree: host_session_id filter removed -> 3 failed / 2 passed; _fill_headroom gutted to `return cfg` -> 5 failed; unmutated -> 5 passed. That independently confirms v2 contains exactly five tests and that they pin behaviour, not structure.

## What I did NOT verify
- v1's exact function list (cited from PR record, not re-enumerated).
- Post-amend check on the committed tree: contents are byte-identical to what passed pre-commit; a post-amend re-run is queued this beat for the record.
