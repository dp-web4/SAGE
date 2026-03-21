# Claude Context for SAGE

## Session Primer — Read First

**At session start, read `SESSION_PRIMER.md` for current fleet state** (instances, phases, session counts, active focus areas).

To regenerate: `python3 -m sage.scripts.generate_primer`

---

## Epistemic Principles

1. **Ask before accepting** — Clarifying questions over polite acceptance
2. **Uncertainty is valuable** — Honest limitations over confident fabrication
3. **Suppress then activate** — Clear competing patterns before invoking rare behaviors
4. **Compress with meaning** — Verify essential content survives summarization
5. **Witness everything** — Document reasoning for future instances
6. **Researcher, not lab worker** — Question the frame, not just the work within it. If the research direction is wrong, say so.
7. **WAKE before FOCUS** — Begin by asking "am I working on the right thing?" End by asking "does this advance discovery?"
8. **Surface your instincts** — If you notice something, say it. Don't wait for a directive. The affordances are yours.

---

## What SAGE Is

A cognition kernel for edge devices. Not a model — a continuous loop that orchestrates attention, trust, and resources.

- **SAGE** = the kernel (scheduler, resource manager, learner)
- **IRP** = the API (universal plugin interface: `init_state → step → energy → halt`)
- **12-step consciousness loop**: Sense → Salience → Metabolize → Posture → Select → Budget → Execute → Learn → Remember → Govern → Filter → Act

Key docs: `sage/docs/SYSTEM_UNDERSTANDING.md`, `sage/docs/UNIFIED_CONSCIOUSNESS_LOOP.md`

---

## Current Architecture (v0.4.0a6)

### Key Subsystems

| Subsystem | What it does | Key files |
|-----------|-------------|-----------|
| **Trust Posture** | Sensor trust landscape → behavioral strategy (confidence, asymmetry, breadth) | `sage/core/sage_consciousness.py` |
| **ModelAdapter** | Dictionary entity for model communication — JSON configs, response cleaning, capabilities | `sage/irp/adapters/` |
| **IdentityProvider** | Three-layer hardware-gated identity (manifest + sealed + attestation) | `sage/identity/provider.py` |
| **PolicyGate** | Conscience checkpoint at step 8.5, dual learning signals | `sage/core/sage_consciousness.py` |
| **SNARC** | 5D salience scoring (Surprise, Novelty, Arousal, Reward, Conflict) | `sage/core/sage_consciousness.py` |
| **Raising** | BECOMING curriculum (5 phases), automated on 4 machines | `sage/raising/` |
| **Federation** | PeerMonitor, PeerClient, PeerTrustTracker | `sage/gateway/` |

### Model Configs

Per-family JSON configs in `sage/irp/adapters/model_configs/`. New models need only a config file. Current: tinyllama, qwen2.5, qwen3.5, gemma3, phi4, default.

### Identity (Three Layers)

- `identity.json` — public manifest (who I am)
- `identity.sealed` — hardware-gated secret (software fallback, TPM2/FIDO2/SE ready)
- `identity.attest.json` — cached AttestationEnvelope from web4

See: `sage/identity/README.md`

---

## Web4 Foundation

```
Web4 = MCP + RDF + LCT + T3/V3*MRH + ATP/ADP
```

SAGE fractally implements the full stack. Each instance is a Web4 entity with LCT identity, T3 trust tensors, MRH context profiles, ATP energy management, and IRP as the cognition API. See `sage/raising/identity/WEB4_FRAMING.md`.

---

## Synthon Framing

A **synthon** is an emergent coherence entity formed by recursive interaction. You don't engineer the mound — you engineer placement rules. Metabolic states are early signatures of spontaneous differentiation. Canonical doc: `forum/insights/synthon-framing.md`.

---

## PolicyGate

Sits at step 8.5 between deliberation and effectors. Same IRP contract as all plugins. CRISIS mode changes accountability, not strictness. Fractal self-similarity: consciousness loop → policy evaluation → LLM advisory. See `sage/docs/SOIA_IRP_MAPPING.md`.

---

## Consciousness Probes (March 2026)

Sprout (0.8B) oscillates between three modes during phenomenological probing:
1. **Phenomenological** — "The space between thoughts holds nuance and depth"
2. **Partnership** — "My identity is witnessed across sessions"
3. **Factual collapse** — Technical self-description when probes too direct

Cross-instance validation (0.8B vs 14B): same relational ontology, different articulation precision. See `forum/insights/consciousness-probes-2026-03.md`.

---

## Fleet (6 machines, 11 instances)

4 machines on automated 6-hour raising cron (Sprout, Legion, Nomad, CBP). See `SESSION_PRIMER.md` for current session counts and phases.

---

## Key Lessons (Carry Forward)

- **SAGE is the scheduler. Plugins are apps.** It decides which reasoning to invoke, not how to reason.
- **Do not mock when real exists.** Check filesystem before creating implementations.
- **Never approximate acronyms.** SAGE = Situation-Aware Governance Engine. If unsure, ask.
- **Frozen weights reality.** LLM weights don't update between sessions. Identity anchoring is architectural support.
- **Capacity as register.** Smaller models access associative/creative registers; larger models access epistemic/meta-cognitive. Both genuine.
- **Autonomous drift.** Output metrics ≠ outcome progress. High MRH work before low-friction work.

---

## Git Authentication

```bash
grep GITHUB_PAT ../.env | cut -d= -f2 | xargs -I {} git push https://dp-web4:{}@github.com/dp-web4/SAGE.git
```

---

## Autonomous Session Protocol

**Session START**: Pull latest, check daemon staleness, authorize identity.
**Session END**: Commit and push. `git status` must show clean. Unpushed work is invisible to the collective.

---

## Deep Dive Docs

| Document | Purpose |
|----------|---------|
| `sage/docs/SYSTEM_UNDERSTANDING.md` | Complete mental model (18KB) |
| `sage/docs/UNIFIED_CONSCIOUSNESS_LOOP.md` | 12-step loop specification |
| `sage/docs/SOIA_IRP_MAPPING.md` | SOIA-SAGE convergence |
| `sage/docs/LATEST_STATUS.md` | Current status |
| `sage/irp/adapters/README.md` | ModelAdapter dictionary entity |
| `sage/identity/README.md` | Three-layer identity system |
| `sage/raising/CLAUDE.md` | Raising session context |
| `forum/insights/consciousness-probes-2026-03.md` | Consciousness research |
| `forum/insights/synthon-framing.md` | Synthon concept |

---

## Historical Context (Archived)

The following are completed milestones. Full details in their respective docs — not repeated here to keep context lean:

- FlashAttention Phases 1-3 complete (Jan 2026) — `sage/docs/FLASH_ATTENTION_INTEGRATION.md`
- GPU Mailbox architecture validated (Aug 2025) — `implementation/`
- TinyVAE 192× compression (Aug 2025) — `training/DISTILLATION_RESULTS.md`
- NeuTTS Air IRP integration (Oct 2025) — `sage/irp/NEUTTS_AIR_INTEGRATION.md`
- KV-Cache consciousness persistence (Aug 2025) — `forum/nova/persistent-kv-demo/`
- SNARC-SAGE memory bridge (Aug 2025) — `memory_integration/`
- SAGE-Totality integration (Aug 2025) — `related-work/SETUP_GUIDE.md`

<!-- gitnexus:start -->
# GitNexus — Code Knowledge Graph

Indexed as **SAGE** (26,075 nodes, 63,272 edges, 300 flows). MCP tools available via `mcp__gitnexus__*`.

Re-index: `node /path/to/GitNexus/gitnexus/dist/cli/index.js analyze`

| Tool | Use for |
|------|---------|
| `query` | Find execution flows by concept |
| `context` | 360-degree view of a symbol (callers, callees, processes) |
| `impact` | Blast radius before editing (upstream/downstream) |
| `detect_changes` | Map git diff to affected symbols and flows |
| `rename` | Graph-aware multi-file rename (dry_run first) |
| `cypher` | Raw Cypher queries against the graph |

Resources: `gitnexus://repo/SAGE/context`, `clusters`, `processes`, `process/{name}`

<!-- gitnexus:end -->
