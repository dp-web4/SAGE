# Check verdict — 2026-09-11 ~14:5x UTC (baseline, before v2 pins)

check target=gateway → **PASS — 210 passed in 2.20s**
tree head: edbe06175233f63ff08dfc9e9e0a9bcc75f7e090
branch: legion-being/context-fit-regression-pins (clean, dirty=false)
action_id: b54becfc-d7f7-4d15-9d11-be428e4b2fba

Provenance cross-check: git_read status reports the same head edbe06175 on the same
branch — check tree == worktree HEAD. The 210 includes my six v1 pins (P1-P6).

Source facts locked this beat (all from /home/dp/ai-workspace/being-worktrees/legion-being):
- def _fill_headroom at heartbeat.py:301; body ~301-349. Earlier "285-349" citation was loose; 301 is the exact def line.
- Behaviour (line-cited from source this beat): filters partial-file entries on host_session_id == arg; selects MAX prompt_eval_count among matching entries with that key present; writes cfg["prompt_tokens_max"], cfg["headroom_tokens"] = num_ctx_resolved - max - _ANSWER_RESERVE, cfg["context_overcommitted"]; returns the same dict object (in-place).
- _fill_headroom imports _ANSWER_RESERVE from sage.gateway.being_tool_loop. Its numeric value I did NOT read directly this beat (elided ranges); 6144 is taken from the seat's turn-98 restored pin, which the seat states it verified discriminates against a no-op implementation. If the constant differs or moves, these pins fail loudly — that is their job.
