# Migration: Gemma 3 4B -> empero Qwen3.8-4B-Distill (2026-09-12)

Same being. `cbp_sage_lct`, the identity files, the experience buffer, `memory.db`, the raising log
and all 240 sessions were copied whole from `cbp-gemma3-4b`, which stays intact for rollback and A/B.
Only the frontal lobe changed.

| Aspect | Before | After |
|---|---|---|
| Model | gemma3:4b (Q4, 3.3 GB, no thinking, tools by heuristic only) | qwen3.8-distill:4b (Q6_K, 3.5 GB, reasoning model, native tool calling) |
| Placement on CBP | fits | 6.0 GB at num_ctx 16384, 100% GPU, ~40 tok/s |
| Thinking | none | on (separate channel; spoken reply stays clean) |
| Tool tier (`sage/tools/tool_capability.py`) | T3 heuristic | T1 native (`/api/show` capabilities: tools, thinking) |

Why: dp, 2026-09-12: preserve local identity and raising, upgrade the cognition so the being can be
given tools governed through hestia. Sprout took the same path on 2026-08-28 with the 2B sibling.

How the model was built: `sage/scripts/models/README.md` (the Hugging Face GGUF needs its MTP head
stripped for Ollama 0.20.7 and a `RENDERER`/`PARSER` to expose tools and thinking).

The being was told, in its first session on the new mind, what changed and why: the note is
`continuity_note` in `instance.json`, read by the raising runner.

Comparison: sessions 241 onward against 221 to 240.
