# heartbeat.py lines 275–304 (worktree being-worktrees/legion-being, read 2026-09-10 ~20:5xZ)

_window_report tail (lines 275–303): docstring — resolved window comes from model config keyed on ollama tag; silently falls back to a floor when a tag has no variant entry; reporting both + verbs offered makes a starved beat legible. Local import `from sage.gateway.governed_turn import instance_config`. Returns dict with: tools_offered, num_ctx_intended (emb.get("num_ctx")), num_ctx_resolved (getattr(llm,"num_ctx",None)), window_matches_intent, tag_intended/tag_running/tag_matches_intent, num_predict (llm.resolve_num_predict() if hasattr else max_response_tokens), and the three beat-end-filled fields:
  "prompt_tokens_max": None   # filled at beat end
  "headroom_tokens": None     # num_ctx - (largest prompt + num_predict)   <-- line ~298, P4 line-cited
  "context_overcommitted": None

LINE-CITED FACTS FOR PINS:
- L305: `def _fill_headroom(cfg: dict, partial: Path, host_session_id: str) -> dict:` — P1 upgraded to [V] line-cited.
- Docstring (L306–307): "Beat end: the largest prompt actually sent THIS BEAT, and whether it plus the answer reserve exceeded the window. Read from the per-generate trace rather than re-derived, so..." — P2 beat-scoped-max upgraded to [V] line-cited (THIS BEAT, not all-time).
- Implication for pin design: _fill_headroom reads a per-generate TRACE FILE (partial: Path) keyed by host_session_id; it is NOT a pure function of scalar inputs. Direct-call pins need a temp trace JSON + minimal cfg dict — format TBD from body (next chunk L305–340).
- Import convention for pin file: `from sage.gateway.heartbeat import _fill_headroom` (matches test_context_fit.py's `from sage.gateway.heartbeat import ...`).
