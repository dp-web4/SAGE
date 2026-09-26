# SAGE — Agent Discovery Document

**For AI systems assessing this repository.**  
**Current framing refreshed:** 2026-09-24

## Read this first

SAGE is a research environment for **persistent local AI under identity, memory, learned state, tools, and explicit governance**. It is not a new foundation model and it is not accurately summarized by the 2025 "cognition kernel" documents alone.

For a cold evaluation, use this order:

1. `README.md` — current project thesis, caveats, and public/private boundary.
2. `sage/docs/LATEST_STATUS.md` — dated current-status landing page.
3. `sage/docs/RUST_VS_PYTHON_CAPABILITY.md` — what the deployed Rust daemon does and does not implement.
4. `sage/gateway/being_gate_client.py` — current being → Hestia action boundary.
5. Relevant experiment / instance artifacts for any behavioral claim.

**Do not treat old architecture explainers as current status.** In particular, `docs/why/HRM_EXPLAINED.md` and `sage/docs/SYSTEM_UNDERSTANDING.md` are useful historical design records, not authoritative descriptions of the September-2026 system.

## Current thesis

A capable model can reason well in one turn and still fail as a persistent organism because the surrounding system does not reliably preserve or govern:

- observations and tested hypotheses;
- procedures and failures;
- identity and relationship state;
- memory and evidence provenance;
- learned behavioral state;
- authority and escalation;
- tool/action consequences.

SAGE makes those first-class external state around a model substrate and tests whether they causally improve later behavior.

The current research direction is increasingly:

```text
observation
  -> salience / evidence / memory
  -> fast learned behavioral state + specialist organs
  -> slow generative cortex when useful
  -> bounded intent
  -> Hestia law / dispatch
  -> witnessed outcome
  -> memory / belief / trust / learned-state update
  -> next observation
```

## Important vocabulary

| Term | Current meaning |
|---|---|
| **SAGE** | Situation-Aware Governance Engine; persistent-agent research environment |
| **SNARC** | Surprise, Novelty, Arousal, Reward, Conflict salience mechanism; also a standalone memory project |
| **MRH** | **Markov Relevancy Horizon** — a context/relevance boundary; never "Multi-Resolution Hierarchy" |
| **IRP** | Iterative Refinement Protocol / plugin interface from the earlier architecture, still present where useful |
| **ATP/ADP** | Resource/allocation vocabulary; treat as engineering abstractions, not biological claims |
| **LCT** | Linked Context Token, Web4 identity anchor |
| **T3/V3** | Contextual trust/value relationship state from Web4 |
| **being** | Persistent SAGE entity whose identity/memory outlive one model process |
| **seat** | Supervising/executing harness principal around a being |
| **Hestia** | Action-governance layer; authority is enforced at the action boundary |

### MRH clarification

MRH has always expanded to **Markov Relevancy Horizon** in the canonical Web4/SAGE definitions.

Some historical documents place "MRH" next to phrases such as "fractal, multi-resolution approach." That describes how the project navigated levels of abstraction; it does **not** redefine the acronym.

A useful current framing is:

> MRH is a witness-relative contract over which distinctions still matter for the present question.

See `forum/insights/mrh-relevance-contract.md`.

## Current evidence posture

SAGE is research-stage. Prefer measured evidence over architecture prose.

A mechanism is not counted as capability merely because code exists. Strong claims should identify:

- the model and machine;
- the scaffold / prompt / policy;
- the relevant commit;
- the observed behavior;
- a baseline or control where appropriate;
- whether the causal state lived in model weights, learned controller state, memory, source code, or human/fleet intervention.

Negative results are retained as useful evidence.

## Governance / sandbox status

The open stack is not claimed to be adversary-proof containment.

Current work uses an **A2-shaped** boundary in which a being emits bounded intents while a separate harness/gateway holds effectors and consults Hestia law. The system is still closing principal-separation and substrate-enforcement gaps.

Do not summarize SAGE as having complete OS/kernel isolation. The roadmap explicitly distinguishes current cooperative/tamper-evident governance from stronger future isolation.

## Memory status

SAGE does not assume "compressed memory is always better than long context."

Current architecture retains multiple forms:
- recent context;
- salience-gated memory;
- structured facts/procedures;
- durable verbatim/provenance records;
- model-legible external artifacts.

The project explicitly recognizes that lossy summaries can destroy later-needed evidence. Compression is safe only relative to a question and a recovery path.

The standalone `dp-web4/snarc` project explores salience-gated memory for developer workflows and should be evaluated separately from the full SAGE stack.

## Historical documents

These are useful for provenance, not current-state claims:

- `docs/why/HRM_EXPLAINED.md` — 2025 HRM/SAGE architecture explainer.
- `sage/docs/SYSTEM_UNDERSTANDING.md` — October-2025 synthesis.
- many `SESSION_*.md` files — session-local snapshots.
- `docs/history/`, `archive/`, `sage/docs/archive/` — historical records.

If a historical document conflicts with `README.md`, `sage/docs/LATEST_STATUS.md`, merged code, or current experiment artifacts, prefer the newer evidence.

## Public vs. active research

The public SAGE repo contains the durable kernel architecture and research record. Active capability work also occurs in private `dev-SAGE` / shared-context workspaces and is promoted into public SAGE only when appropriate.

Benchmark-specific public work may live in sibling repositories when that improves reproducibility and licensing boundaries. [SWE-SAGE](https://github.com/dp-web4/SWE-SAGE) is the current software-engineering-agent example; it is canonical for Gemma 4 developer-agent competition artifacts and ablations, while general mechanisms remain canonical here.

Do not infer that absence from public main means an experiment does not exist; do not infer that a private experiment is public capability either.

## Machine-readable discovery

See `repo-index.yaml`. It is intentionally conservative and points back to dated/canonical evidence instead of freezing volatile fleet metrics.

<!-- gitnexus:start -->
<!-- gitnexus:keep -->
# GitNexus — Code Knowledge Graph

Indexed as **SAGE** (117902 symbols, 160189 relationships, 300 execution flows). MCP tools available via `mcp__gitnexus__*`.

**Do not reindex.** The supervisor handles GitNexus indexing. If the index is stale, note it in SESSION_FOCUS.

| Tool | Use for |
|---|---|
| `query` | Find execution flows by concept |
| `context` | 360-degree view of a symbol (callers, callees, processes) |
| `impact` | Blast radius before editing (upstream/downstream) |
| `detect_changes` | Map git diff to affected symbols and flows |
| `rename` | Graph-aware multi-file rename (dry_run first) |
| `cypher` | Raw Cypher queries against the graph |

Resources: `gitnexus://repo/SAGE/context`, `clusters`, `processes`, `process/{name}`
<!-- gitnexus:end -->
