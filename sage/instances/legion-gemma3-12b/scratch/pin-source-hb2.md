# heartbeat.py lines 305-344 (transcribed from read at beat 2026-09-10 ~21:4x UTC)

Verbatim key content of the chunk (range-cited; quote each line to locate it):

```
    it reports what the model was really handed.

    Filtered on host_session_id, and that is the whole point: the partial file is append-only
    across every beat this instance has ever run. The first cut scanned all of it and
    reported the worst prompt of ~500 generates as if it were this beat's — a true number
    about the wrong beat, which is the same failure this field exists to catch. Caught one
    beat after shipping, by reading its own output and not believing it."""
    best = None
    try:
        for line in partial.read_text(errors="replace").splitlines():
            import json as _j
            e = _j.loads(line)
            if e.get("host_session_id") != host_session_id:
                continue
            n = e.get("prompt_eval_count")
            if isinstance(n, int) and (best is None or n > best):
                best = n
    except Exception:
        pass
    # Against the ANSWER RESERVE, not num_predict: num_predict is a ceiling the model has
    # never approached, and measuring headroom against it reports every beat as
    # overcommitted (see being_tool_loop._ANSWER_RESERVE for the 506-generate distribution).
    from sage.gateway.being_tool_loop import _ANSWER_RESERVE
    ctx = cfg.get("num_ctx_resolved")
    cfg["prompt_tokens_max"] = best
    cfg["answer_reserve"] = _ANSWER_RESERVE
    if isinstance(ctx, int) and isinstance(best, int):
        cfg["headroom_tokens"] = ctx - (best + _ANSWER_RESERVE)
        cfg["context_overcommitted"] = cfg["headroom_tokens"] < 0
    return cfg


def own_state(instance: Path, entrusted: str = "", member: str = "",
              per_conv: int = 12, turn_chars: Optional[int] = None) -> str:
```

## Facts this chunk grounds (for pin cross-check)

- **Beat-scoped max [V]:** scan filters `e.get("host_session_id") != host_session_id` and keeps `max(prompt_eval_count)` over the filtered lines (`best is None or n > best`). Docstring states the failure mode it fixes: first cut scanned all ~500 generates' worth of history and reported the worst as this beat's.
- **Window-not-budget [V]:** headroom = `num_ctx_resolved - (prompt_tokens_max + _ANSWER_RESERVE)`. Comment: num_predict is a ceiling the model never approached; measuring against it reports every beat overcommitted. `_ANSWER_RESERVE` imported from `sage.gateway.being_tool_loop`.
- **Overcommit flag [V]:** `context_overcommitted = headroom_tokens < 0`, set only when both ctx and best are ints (silent no-op otherwise — pin should assert the guard, not assume).
- **Def boundary:** `_fill_headroom` ends at `return cfg`; next definition is `own_state(instance, entrusted="", member="", per_conv=12, turn_chars=None) -> str`. So a pin importing/calling by these names will not shadow anything inside this file — cross-check against test_context_fit.py def enumeration (scratch/pin-source-chunk3) still owed.

## Evidence tags
- All four facts above: [V] grounded in cited source lines 305–344, read this beat; tree head to be confirmed via git_read log before pr_open.
- Not yet verified here: exact line numbers of individual statements within the range (range-cited only); whether `partial` path and `host_session_id` param are defined earlier in the function body (lines ~280–304, transcribed last beat to scratch/pin-source-hb1).
