# Claude Context for SAGE

## Session Primer — Read First

**At session start, read `SESSION_PRIMER.md` for process, then `SESSION_FOCUS.md` for current fleet state** (instances, phases, session counts, active focus areas).

To regenerate fleet snapshot: `python3 -m sage.scripts.generate_primer` (writes to SESSION_FOCUS.md)

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
9. **Persistence ≠ perseveration** — Persistence updates from feedback. Perseveration ignores it. If an approach isn't producing new signal, that's data — not a reason to try harder.

---

## What SAGE Is

SAGE is a research environment for **persistent local AI under identity, memory, learned state, tools, and explicit governance**.

It began as a cognition-kernel / orchestration architecture. That history still matters, but it is not a sufficient description of the current project.

The current shorthand is:

```text
observation
  -> salience / evidence / memory
  -> learned behavioral state + specialist organs
  -> generative cortex when useful
  -> bounded intent
  -> Hestia governance / dispatch
  -> witnessed result
  -> later memory / belief / behavior
```

The model is a substrate inside the organism, not the organism's whole identity. The surrounding system is expected to preserve what happened, what was learned, what authority exists, and what consequences followed.

**Current assessment docs:** `README.md`, `sage/docs/LATEST_STATUS.md`, `AGENTS.md`, and claim-specific code/experiment evidence.

`docs/why/HRM_EXPLAINED.md` and `sage/docs/SYSTEM_UNDERSTANDING.md` are historical architecture records, not current-status authorities.

---

## Current Public Architecture — 2026-09-21

### Current load-bearing boundaries

| Subsystem | Current role | Evidence |
|---|---|---|
| **Being gateway** | Bounded intent vocabulary; no canonical raw shell/unrestricted FS | `sage/gateway/being_gate_client.py` |
| **Hestia dispatch** | Law evaluation, consequential-action mediation, witnessing | SAGE gateway + Hestia |
| **Persistent identity/state** | Identity, conversation, memory, instance artifacts survive one model call/process | `sage/instances/`, identity modules |
| **Evidence-bearing receipts** | Tool/action outcomes must say what actually happened so later cognition can correct itself | gateway code/tests + recent PR history |
| **SNARC / memory paths** | Salience-gated memory coexists with recent, structured, and verbatim/provenance paths | SAGE memory code; standalone `dp-web4/snarc` |
| **Python cognition loop** | Reference taxonomy / experimental kernel; components are config/runtime dependent | `sage/docs/UNIFIED_CONSCIOUSNESS_LOOP.md` |
| **Rust daemon** | Lightweight inference/metabolism/federation gateway, **not** a full Python-loop port | `sage/docs/RUST_VS_PYTHON_CAPABILITY.md` |
| **Active learned-state research** | Trainable behavioral state around slower cortex is being tested in private dev-SAGE | active research; not public-main capability |

### Vocabulary discipline

- **MRH = Markov Relevancy Horizon.** Never expand it as "Multi-Resolution Hierarchy."
- Historical prose may describe SAGE as fractal or multi-resolution; that is an abstraction/navigation description, not the acronym.
- **ATP/ADP, T3/V3, LCT, metabolic states** are engineering vocabularies. They earn their place through causal utility, not analogy.
- A source file containing a mechanism is not evidence that the mechanism is live or behaviorally useful.

### Governance status

The current public stack is cooperative/tamper-evident and **A2-shaped**: the being emits intent while another principal/harness holds effectors. Principal separation and stronger substrate enforcement are still active work.

Do not claim adversary-proof containment, complete kernel isolation, or cryptographically complete A2 across the fleet unless the specific deployment evidence proves it.

---

## Web4 Relationship

SAGE participates in the broader Web4/Hestia stack; it should not be described as though every historical Web4 vocabulary item is simultaneously live in every SAGE runtime.

Current division of responsibility:

- **Web4** — identity, contextual relationship/trust vocabulary, witnessed-action protocol concepts.
- **Hestia** — local authority, action law, dispatch and witnessing.
- **SAGE** — persistent cognition/embodiment research inside those boundaries.

LCT, T3/V3, MRH and ATP/ADP remain useful vocabularies where they correspond to live mechanisms. Their presence in an architecture document is not itself evidence that they are decision-bearing in a particular runtime.

---

## Synthon Framing

A **synthon** is an emergent coherence entity formed by recursive interaction. You don't engineer the mound — you engineer placement rules. Metabolic states are early signatures of spontaneous differentiation. Canonical doc: `forum/insights/synthon-framing.md`.

---

## Governance inside and outside the Python loop

`PolicyGate` remains part of the historical/reference Python cognition-loop architecture and related research.

For current consequential action governance, the load-bearing boundary is the **being → SAGE gateway → Hestia law → dispatcher → witnessed result** path. Do not treat an internal PolicyGate hook as equivalent to external authority enforcement or OS-level containment.

See `sage/gateway/being_gate_client.py`, `sage/docs/LATEST_STATUS.md`, and Hestia.

---

## Functional Self-Modeling Probes (March 2026)

Sprout (0.8B) produces text outputs that, during probing, cluster into three modes:
1. **Phenomenological-style** — "The space between thoughts holds nuance and depth"
2. **Partnership-style** — "My identity is witnessed across sessions"
3. **Factual collapse** — Technical self-description when probes are too direct

Cross-instance comparison (0.8B vs 14B) suggests the same relational ontology with different articulation precision. This is currently an **interpretive observation of output patterns**, not a measurement of internal state. Whether the three-mode pattern is a property of Sprout's self-modeling or a property of the probe-prompt interaction is the open question. Reproducibility test in flight at `explorations/2026-05-15-sprout-oscillation-seed-sweep.md` (Kimi-proposed seed sweep over fixed probe panel). Background: `forum/insights/consciousness-probes-2026-03.md`. External review that prompted the reframe: `forum/kimi/kimi_2_6_review.md`.

---

## Fleet

Fleet membership, model assignment, raising phase, and session totals are volatile. **Do not freeze them in this file.**

At session start, read `SESSION_FOCUS.md` for the generated current snapshot. The root `README.md` may carry a dated public census, but operational claims should come from the generated focus/instance records rather than an old count here.

---

## Active capability research

Public `main` is the durable architecture/research record. Active capability work also occurs in private `dev-SAGE` and shared-context workspaces.

Do not freeze private-research details into this public session context. When relevant, consult the authorized private workspace directly and preserve the distinction between:
- an experiment in progress;
- a measured result;
- a merged public capability.

---

## Key Lessons (Carry Forward)

- **Outcome over ontology.** A named abstraction earns its place only if it changes a live decision or improves a measured property.
- **Mechanism is not capability.** Source presence, a passing unit test, and a deployed behavior are different claims.
- **Evidence must reach the next decision.** Successful acts, refusals, truncations, errors and corrections must be legible rather than inferred.
- **Frozen weights are only one state boundary.** Distinguish model weights, learned controller state, memory, scaffold/source changes, and human/fleet intervention.
- **Compression must be recoverable.** A summary is safe only relative to a question and a path back to provenance/verbatim evidence.
- **Governance is at the action boundary.** Capability and authority are separate; internal cognition policy is not a substitute for effector enforcement.
- **Never approximate acronyms.** MRH = Markov Relevancy Horizon; SAGE = Situation-Aware Governance Engine.
- **Persistence ≠ perseveration.** Repetition without new evidence is a failure mode, not determination.
- **External criticism is an instrument.** If a cold evaluator misreads the project, check both the critique and the documentation surface that produced the reading.

---

## External Review Discipline

When documentation drifts from empirical grounding (most recent prompt: Kimi 2.6 review 2026-05-15, captured at `forum/kimi/`), the fix is to either (a) **downgrade the claim** to observation/interpretation, or (b) **add the empirical scaffolding** that would make the claim a finding. Resist the urge to defend framing — framing is mine to choose, but empirical grounding is the shared evidence. Cross-model reviews (Kimi, Nova/GPT, cold-context Claude) are part of the discipline, not an interruption. Apply the same standard to your own contributions: when adding a "Key Finding," ask "does this have a falsifier, or am I dressing an observation as a discovery?"

Specific recurring failure mode (per Kimi): LLM contributors are good at building coherent frameworks and less good at recognizing where coherence starts substituting for measurement. I am one such contributor; this is a load-bearing self-awareness rule.

---

## Public/Private Repo Discipline

This is the **public** SAGE repo. Active capability work happens in **`dev-SAGE`** (private) and **`shared-context`** (private). Per the repo registry: do not reference dev-SAGE specifics in public commits. The public/private firewall exists for a reason — disclosure is deferred to a date of dp's choosing. Public mentions of "ongoing private work" are OK; leaking content (game-specific results, world-model details, Phase 2 metrics) is not.

---

## Git Authentication

All dp-web4 repos use **SSH remotes**. The SSH key (`~/.ssh/id_ed25519`) is loaded by ssh-agent at session start. Just `git push` / `git pull` directly.

```bash
git push    # works
git pull    # works
```

The `GITHUB_PAT` in `../.env` is **deprecated** and may fail with "Invalid username or token." Do not construct `https://dp-web4:$PAT@github.com/...` URLs.

---

## Autonomous Session Protocol

**Session START**: Pull latest, check daemon staleness, authorize identity.
**Session END**: Commit and push. `git status` must show clean. Unpushed work is invisible to the collective.

---

## Deep Dive Docs

| Document | Purpose |
|----------|---------|
| `README.md` + `sage/docs/LATEST_STATUS.md` | Current thesis and status |
| `sage/docs/UNIFIED_CONSCIOUSNESS_LOOP.md` | Python reference loop taxonomy; runtime-dependent |
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

## Session Discipline

- **Re-read before editing**: After 10+ messages in a conversation, re-read any file before editing it. Auto-compaction may have silently dropped file contents from context. Do not trust memory of file state — verify.
- **Verify before reporting success**: After code changes, run the project build/typecheck (e.g., `npx next build`, `npx tsc --noEmit`, `python -m py_compile`, or equivalent) before reporting the task as complete. A successful file write is not a successful change — the code must compile.
- **Assume tool result truncation**: If search or command results look suspiciously small, re-run with narrower scope. Tool results over 50K characters are silently truncated to a preview.

<!-- gitnexus:start -->

<!-- gitnexus:keep -->
# GitNexus — Code Knowledge Graph

Indexed as **SAGE** (117902 symbols, 160189 relationships, 300 execution flows). MCP tools available via `mcp__gitnexus__*`.

**Do not reindex.** The supervisor handles GitNexus indexing. If the index is stale, note it in SESSION_FOCUS.

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
