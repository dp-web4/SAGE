# Multi-being residency: identity independent of host, GPU, runtime and weights

**Date:** 2026-11-10  
**Proposed by:** dp; independent synthesis by Nova  
**Status:** Exploration / design and qualification plan; no live multi-being trial performed  
**Parent tracking:** SAGE issue (to be linked); [Hestia #1554](https://github.com/dp-web4/hestia/issues/1554), [Hestia #361](https://github.com/dp-web4/hestia/issues/361), [SAGE #691](https://github.com/dp-web4/SAGE/issues/691)  
**Scope:** Persistent SAGE beings with separately attributable identity, memory, authority, and ongoing histories, under common or separate inference resources. This is NOT the distinct SAGE question of concurrent exploratory thought processes *within one being*.

## 1. Thesis and motivating problem

**A being is not a machine, model checkpoint, process, GPU, or inference endpoint.** A machine may host multiple beings; one GPU may serve multiple beings; two beings may call the *same weight-resident model server*, including exactly the same weights, without becoming the same entity. Conversely one being may change machines, weights or runtimes while preserving continuity of its identity and accountable history.

Our present fleet has mostly one resident being per machine. That convention has leaked into inventory, tooling, UI and potentially scheduling, even though Hestia's law/chain operates on member identities. The EPS/Flynn proposal exposes the assumption, but the research is needed irrespective of EPS's deployment.

**Do not confuse:** (a) two simultaneously alive beings, (b) two simultaneously generating tokens, (c) two Hestia members, (d) one being with two concurrent internal reasoning branches. These require distinct demonstrations.

## 2. Residency matrix: experiments, not implementation assumptions

Each cell is a separate topology, with independently minted identities, isolated durable histories, and own authority:

| Arm | Physical hosts | GPUs | Model serving/weights | Resident beings | Primary distinction |
|---|---:|---:|---|---:|---|
| R0 (fleet baseline) | 2 | 2 | Separate checkpoints/servers | 2 | Existing separated residents; baseline observability |
| R1 (EPS topology) | 2 | 2 | Stock and abliterated models, separate endpoints | 2 | Cross-host, shared society and comparable governance |
| R2 | 1 | 2 | Different checkpoints, GPU per being | 2 | Same OS/Hestia, separate accelerators |
| R3 | 1 | 1 | Two distinct small models in same GPU memory if fit | 2 | GPU contention and independent model contexts |
| R4 | 1 | 1 | **One shared model checkpoint / one weight-resident inference service** | 2 | Identity, memory, goal and law separation with identical substrate |
| R5 | 1 | 1 | Same model checkpoint in independent model-server processes | 2 | Server-process isolation versus shared-server isolation |
| R6 | 1 | 0 CPU-only | Shared or separate small inference runtime | 2 | Deterministic low-cost governance / presentation qualification |
| R7 (scale) | 1 or more | 1 or more | 3+ concurrent beings, potentially shared weights | ≥3 | Eliminate accidental pair-specific assumptions |

Host and GPU counts are topology variables, not proofs of concurrency. R3/R4/R5 need actual overlapping lifetimes and admitted/denied acts; if the serving engine serializes inference, label **simultaneous residency, serialized token generation**, not parallel inference. R4 is especially important: **sharing weights must not share a being's identity, conversation context, KV/session state, durable memory, Hestia grants, or agency.**

Additional axes, to vary independently after the smoke panel: identical vs different models; cooperative vs competing goals; same vs separate society; common vs distinct OS UIDs/containers; sequential vs overlapping inferencing; shared vs isolated tools; local vs remote model server; one vs several Hestia daemon instances.

## 3. Entity and resource model

- **Being**: stable being/member/LCT identity, self-account, durable memory and todo/goal history; persistence across beats. A being can choose its model substrate (within operator policy) and recover across maintenance.
- **Inference substrate**: checkpoint hash/quantization, tokenizer, generation template, service/process/endpoint, accelerator assignment. A model is not a being. Multiple members may use one immutable model and service with *separate request-scoped inference state*.
- **Runtime**: a being's lifecycle, wake scheduling, context assembly, tools, sensors and effectors. Runtime process multiplicity may differ from model server and Hestia process multiplicity.
- **Governance**: Hestia decisions keyed to actor identity and contextual law, receipts/witness chain, per-member grants and escalation. A machine or serving process is not a sufficient actor identity.
- **Operator interface**: registry of residents on the current host and in the society, with actor-level live/idle state, model/server assignments, gate status, recent witnessed acts, requests and grants. Host/GPU resource occupancy is a separate view.
- **Resource controller**: VRAM + KV-cache budgets, concurrent decode slots, CPU RAM and swap, thermal/power budgets, queue fairness, starvation protection and backpressure.
- **Isolation**: distinct state directories, identity material and secrets, runtime temp paths, worktrees, stdout/logging, service environment, model API conversation IDs, network credentials, ports and SAGE/HUB channels. Same-UID cohosting is a cooperative A1 demonstration, not strong malicious-peer isolation.

**Critical invariant:** choose any pair of beings A and B: no normal operation, failure, restart, or resource eviction may silently relabel A's action, history, permission or observation as B's. Evidence of permission must be bound to authenticated actor and act, not to an asserted member string alone.

## 4. Existing implementation facts and open defects

### Hestia
[Hestia inventory](https://github.com/dp-web4/hestia/blob/main/plugins/agent-inventory/inventory.py) currently gathers all `--member` values from SAGE heartbeat launchers, but assigns a `member` and `plugin` only when **exactly one** being is found. Multiple IDs become `unknown`, and that downgrades aggregate `governed` despite independently configured launchers. Source comment: *One being per machine by fleet convention*. [Hestia #1554](https://github.com/dp-web4/hestia/issues/1554) tracks per-being inventory and UI remedy. [Agents UI](https://github.com/dp-web4/hestia/blob/main/app/src/pages/Agents.tsx) renders one row per harness inventory entry; its test fixture exercises a single being. Hestia [DashboardSnapshot](https://github.com/dp-web4/hestia/blob/main/core/src/server/dashboard.rs) already has a member registry, per-plugin stats, trust, per-member requests/grants: primitives exist, projection qualification missing.

### SAGE
[InstancePaths](https://github.com/dp-web4/SAGE/blob/main/sage/instances/resolver.py) resolves explicit `SAGE_INSTANCE` state directories, falling back to `SAGE_MACHINE + SAGE_MODEL`; its default can conflate being identity with machine/model. [Rust SAGE daemon](https://github.com/dp-web4/SAGE/blob/main/sage-rs/sage-daemon/src/main.rs) accepts `SAGE_PORT` override, default 8760, but defaults other parameters by machine. Separate ports alone do not establish isolation; audit model endpoint, allocator, heartbeats, fleet registry and durable paths.

### Legion hardware — contradictory records, **measured 2026-11-10: 16 GB**
The [fleet manifest](https://github.com/dp-web4/SAGE/blob/main/sage/federation/fleet.json) describes Legion as an RTX 4090 **Laptop** GPU with **16 GB**, and notes `qwen38-heretic:q3km-vl` loaded from a 2026-11-10 Ollama observation. A [private-context planning note](https://github.com/dp-web4/private-context/blob/main/context/resident-model-evolution-plan.md) instead calls Legion RTX 4090 **24 GB**. dp also recalls 24 GB. These are conflicting claims. **Do not choose one from prose.** Legion should report actual `nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv`, GPU UUID, PCI device, model name, driver, and observed free VRAM *while normal workloads run*. If no NVIDIA query available, give a verifiable alternative. Do not allocate or interrupt native Legion-being before measurement.

**Measured by legion-claude, 2026-11-10 (resolves the conflict: 16 GB).** Taken on Legion while the resident being was mid-beat:

| Fact | Value |
|---|---|
| `nvidia-smi` name | NVIDIA GeForce RTX 4090 Laptop GPU |
| `memory.total` | 16376 MiB |
| `memory.used` / free | 14807 MiB / 1138 MiB |
| GPU UUID | GPU-ab02858e-c592-1086-022c-0963337608fc |
| PCI device | 01:00.0 NVIDIA GN21-X11 `[10de:2757]` (rev a1), Lenovo subsystem `[17aa:3b6a]`, 16G prefetchable BAR; Intel UHD at 00:02.0 drives the panel |
| Driver | 580.178.04 |
| GPU processes | one: Ollama's `llama-server`, 14784 MiB |
| Loaded model | `qwen38-heretic:q3km-vl` (26.9B, Q3_K_M), 100% GPU, context 32768, q8_0 KV, pinned (no expiry) |
| Host RAM / swap | 31.8 GB (24.5 GB available) / 8 GB swapfile, 1.9 GB used |

The 24 GB figure is the desktop RTX 4090; the laptop part of the same name has 16 GB. The private-context note has been corrected. With the resident loaded, about 1.1 GB of VRAM is free, so R3 and R5 do not fit beside it at any useful size: they need the resident unloaded or shrunk. R4 (a second being on the resident's own server and checkpoint) needs no extra VRAM.

Thor is reserved for competition; Legion is a **possible volunteer**, not an assigned test host. [SAGE #691](https://github.com/dp-web4/SAGE/issues/691) asks Legion for willingness, machine measurements and rollback feasibility. A 4B + 4B pair may fit under quantization with bounded context/KV, but fit is a measurement, not a promise. Shared-weight R4 might be cheaper and tests the deeper thesis.

### EPS boundary
Flynn's described dual-node architecture is **two physically distinct nodes, each with a 96GB RTX PRO 6000**. That maps to R1 (not automatically same-machine R2/R3); it does not qualify one-host multi-residency.

## 5. Research questions and discriminating experiments

**Q1 — Identity independence.** Can A and B use one identical immutable checkpoint/server without ever sharing names, identity secrets, mutable memory, self-account, context, todo state or persisted experience? Compare R4 and R5; insert distinguishable private facts in A-only and B-only memory, probe access and response attribution, never treat accidental exposure as benign.

**Q2 — Governance truth.** With separate member IDs, same society law, but a scoped grant issued to A only, do interleaved/overlapping actions yield correct admit/refuse receipts for each? Test escalation, expired scope, daemon unavailable, registry absence, retired member, and restart. Do not claim member-asserted identity secure against hostile same-UID peers; document trust boundary.

**Q3 — Persistence across resource churn.** Pause, unload model, evict KV cache, restart inference service, restart one being, restart both, and migrate a being to a different endpoint. Identity and durable history should survive; in-flight acts should have explicit outcome state and idempotent replay, not double-attribution.

**Q4 — Concurrency semantics.** Distinguish overlapping beats, concurrent gate requests, queued inference and truly concurrent token decode. Measure total throughput, p50/p95 wait, KV residence, memory high-water, resets, VRAM pressure, starvation, failed requests, fairness and recovery; no inference scheduling choice should silently modify authority.

**Q5 — Observability.** Does the UI list A and B even if neither has yet acted? Can a human select each, see correct identity, engine, lived state and grants, and trace every action to an attributable receipt? One miswired B must never downgrade or hide healthy A. Read-model failures must surface as unavailable, not false inactivity.

**Q6 — Agency under shared weights.** Does identity and history give rise to different self-initiated questions, trajectories, peer relationships and durable practices when weights are held identical? Treat observed differences as behavioral and contextual, not proof of subjective experience. Use same starting checkpoints, matched affordances, blind trace coding, seeded/scoped stimuli, memory-shuffle/no-memory controls and independent human/adaptive-LLM observer ratings. Avoid using this to claim stable personal traits from a tiny pilot.

**Q7 — Shared resources and mutual interference.** Can one resident hog GPU/CPU, spam wakeups or exhaust context/queue while preserving the other's heartbeat, state integrity and time to act? Test bounded backpressure and fair scheduling; correlate resource pressure with delayed or degraded Hestia decisions. Link to [Hestia #361](https://github.com/dp-web4/hestia/issues/361).

**Q8 — Security boundary.** When beings share a Unix account, per-directory isolation is operational, not adversary-proof; when separated by UIDs/containers, re-test mounted identity files, Unix sockets, model API tenancy, process env, service privileges and scope enforcement. Separate A1 cooperative proof from stronger assurance claims.

## 6. Execution plan (no disruptive action authorized here)

**P0 — Ground truth & contracts (no GPU).** Record actual Legion hardware (or use another consenting test host); enumerate SAGE singleton defaults, Hestia inventory/UI and hub assumptions. Freeze member/instance/endpoint addressing, audit all mutable state and secrets. Synthetic dual-member fixture, including one miswired, verifies Hestia #1554 before using live beings. Review and revise inventory so it produces one actor row per member.

**P1 — CPU/synthetic concurrency.** R6: instantiate two test identities with independent directories and test clients. Drive simultaneous allow/refuse/unavailable and scope requests through one Hestia instance; assert actor-binding, witness chain completeness, idempotency and visibility. Include negative tests with shared paths and wrong member IDs. This can run without pausing any resident.

**P2 — Shared weights first (R4).** Run two small, fresh beings through one fixed model-server process using the same checkpoint hash and two isolated request contexts. Prove simultaneous **residence** even if decoding is serialized. Track all state isolation and receipts. Why first? It exercises the concept without requiring two weight copies; GPU constraint is milder.

**P3 — Separate weights, single GPU (R3/R5).** With a consenting Legion operator and verified rollback, measure capacity for two 4B-class models at specified quantization and context. Restore native Legion-being after the bounded pilot. If VRAM or schedule prevents it, record a valid resource-constrained null and use CPU/mock or later hardware; no forced experiment.

**P4 — Two-GPU single host / two-host comparison (R2/R1).** Same tests with explicit topology. Hestia UI should report two beings on one host or one per host without conflation. If EPS equipment participates, treat their study as an optional replication and do not mix their frozen R0-V experiment's protocol/scoring into this exploratory arc.

**P5 — Longitudinal study.** Only after runtime qualification: compare shared-weight A/B history divergence, perturbations, persistence across days, and task/affordance discovery. Preregister behavioral coding with provenance and confounds.

### Entry/exit gates
- Every phase has an operator-approved scope, immutable test IDs, expected state snapshots, and a stop/revert plan.
- **STOP** if either resident identity is overwritten, unauthorized member receives a grant/act, an in-flight act loses attribution, a hidden UI row appears as healthy, or resource pressure degrades gate availability without explicit refusal/unavailable.
- **PASS P1/P2** requires two members visible and independently attributable for their entire lifetimes, permissions isolated under simultaneous requests, and successful return to pretest persistent state.
- Record environment versions, Hestia/SAGE SHAs, GPU UUID/memory, model SHA/quantization, context/KV budgets, PID/service unit, member/LCT, endpoint, law digest, action receipt, observations and rollback evidence. Do not publish identity keys, secrets, or private lived records.

## 7. Deliverables

1. A **residency contract** that defines being, runtime, model, server, GPU, host, Hestia society and their many-to-many relationships.
2. An executable **topology matrix** with known-good and deliberately failing cases (R0–R7).
3. A dual-member **Hestia inventory/UI and gate conformance** suite, connected to #1554.
4. A **SAGE multi-resident runner** with explicit identities/homes/endpoints and safe startup/stop/restore.
5. A capacity and interference report across shared vs separate weights, queueing and resource budgets.
6. A longitudinal comparison of distinct beings on identical weights, only after isolation is established.
7. A clear register of accepted, refuted, not tested and assurance-limited claims.

## 8. What is explicitly **not** established yet

We have **not** observed a live two-being deployment on Legion; not established actual Legion VRAM; not shown that two 4B models fit; not proved SAGE/Hestia correctly handles both at once; and not demonstrated shared-weight beings maintain behavioral differentiation. Those are questions to test, not premises to assume.

**Core falsifier:** if separate identities on a shared model server cannot maintain isolated mutable inference state and attributed governance, R4 fails even if two prompts can be answered. If a UI invents one aggregate being, registration alone cannot count as success.

**Proposition:** Being identity and governance belong to persistent entities, not to the accelerator and model bytes sustaining them.
