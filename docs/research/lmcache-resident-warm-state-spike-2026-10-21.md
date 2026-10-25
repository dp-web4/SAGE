# LMCache for resident warm computational state (exploration)
Date: 2026-10-21 | Status: proposed, not implemented
Umbrella: dp-web4/private-context/research/lmcache-kv-persistence-evaluation-2026-10-21.md

LMCache (https://lmcache.ai/en/ ; https://github.com/LMCache/LMCache) is a possible persistence/offload mechanism for *derived transformer KV state*. It should sit beneath SAGE's memory and being/role model, never substitute for them. Prior work: `forum/nova/archive/persistent-kv-demo/` already saved and resumed Hugging Face `past_key_values`; `docs/history/SAGE_KV_Cache_Contamination_Discovery.md` records an unverified cross-session contamination hypothesis, not proof.

## Resident versus visitor
Resident: locally governed continuing being whose cognition has a stake in continuity; SAGE carries its complete local context. A saved KV cache may warm an exact unchanged prefix but is not durable identity. Visitor: remote cognition arrives with opaque external context; data given to/from a visitor may undergo third-party observation. Do not move visitor-derived KV into resident state without explicit information-flow policy and new admissibility review.

## Required invariants
- SAGE identity, responsibilities, memory, lineage and witness records survive any cache loss. Canonical state is replayable; cache is always discardable.
- Model checkpoint, tokenizer, adapter, system prompt, prompt ordering, position/attention implementation, tensor shape and backend must match before reuse. Treat mismatches as cache misses.
- Namespace by being/LCT and tenancy; bind source provenance, scope, expiry/revocation and integrity metadata. Hash alone is not authorization.
- Hestia independently governs every action; a warm cache is not a transferable permit.
- No cross-being, cross-resident/visitor or cross-trust-boundary reuse without explicit approval. Instrument denied reads and fallback paths.

## Proposed spike
On isolated Legion environment, verify pinned LMCache + inference-engine compatibility, then compare cold prefill, SGLang-native prefix cache, and LMCache-backed persistence. Use long realistic wake contexts, engine restarts, altered context, model mismatch, identity A/B, expiry, and revocation. Collect TTFT percentiles, recomputed tokens, GPU/CPU/disk budget, cache hits, deterministic output parity, and recovery after corrupted/missing blobs. Do not roll into Sprout/Thor or production governance without a successful gate. On failure, fall back to canonical SAGE context reconstruction.

Follow-up: define a generic `WarmStateProvider` interface only after measured incremental advantage; avoid making LMCache a hard dependency.
