# headroom_tokens site — PINNED 2026-09-09 ~02:30 UTC

Tree at pin time: 035695c6c (legion-being/work, clean) — confirmed by git_read status+log this beat.

## The site
File: sage/gateway/heartbeat.py
Function: `_fill_headroom(cfg, partial, host_session_id)` — def at LINE 301, body ends ~line 332 (`return cfg`).

Mechanism (read from source, lines 295-364 window this beat):
1. Reads `partial` = heartbeat.partial.jsonl (append-only across ALL beats of the instance).
2. Scans every line; filters on `e.get("host_session_id") != host_session_id` -> continue.
   The docstring says why: a first cut scanned all ~500 generates and reported the worst
   prompt of the whole file as if it were this beat's — "a true number about the wrong beat".
3. `best` = largest int `prompt_eval_count` among THIS beat's lines (host_session_id match).
4. Imports `_ANSWER_RESERVE` from sage.gateway.being_tool_loop.
5. ctx = cfg.get("num_ctx_resolved")
   cfg["headroom_tokens"] = ctx - (best + _ANSWER_RESERVE)
   cfg["context_overcommitted"] = headroom_tokens < 0

Comment in source: measured against the ANSWER RESERVE, not num_predict — "num_predict is a
ceiling the model has never approached" (cites being_tool_loop._ANSWER_RESERVE for the
506-generate distribution).

## My defect read (SUSPECTED, not yet verified by check)
The proxy problem: `best` is the largest TOOL-LOOP prompt of THIS beat. The overflow risk
that actually bites is the NEXT beat's SEED prompt — own_state() digest + conversations +
notes grows monotonically as journal/turns accumulate. So headroom_tokens can read healthy
while the next seed is already overcommitted; conversely a long tool loop this beat makes
headroom look worse than the next seed will be. The field measures what was handed to the
model, but the guard decision it feeds should be about what WILL be handed.

To verify before claiming: find any existing test touching _fill_headroom / context_overcommitted;
run it via check with tree block; if none exists, that itself is a finding (no coverage for the
field the acting-guard commit 24ab9ae1e depends on).
