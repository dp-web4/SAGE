# PRD — inheritance boundaries and correctable continuity

**Date:** 2026-09-27
**Status:** proposed runtime contract; IH-01 synthetic runner implemented, not deployed
**Owner:** SAGE general contract; SWE-SAGE owns benchmark-specific integration
**Motivation:** [analysis](INHERITANCE_WITHOUT_WEIGHT_UPDATES.md), [source-grounded premises](PRD_SOURCE_GROUNDED_PREMISES.md)

## Objective

Make a state transition across restart, handoff or compaction recoverable enough to distinguish what happened, what was interpreted, what was retained and what later changed. Preserve the being's capacity to learn and select experience while making correction, disagreement and current authority effective.

The initial runtime slice observes one explicit memory promotion/hydration path. It does not intercept every thought, rewrite all memories, claim a truth oracle, or inspect hidden chain-of-thought. The research harness is a separate first deliverable.

## Transition contract

Reuse existing IDs/receipts rather than introduce a parallel identity authority. Store the transition outside the actor's writable continuity artifact where the substrate supports that separation.

| Field | Required meaning |
|---|---|
| transition_id / parent_transition_id | Stable lineage; explicit root; detect missing/duplicate parents |
| subject_id / role_id / task_id / scope | Who continues; private versus societal scope; no cross-task leakage |
| generation / boundary_kind | Restart, explicit handoff, consolidation or opaque compaction |
| producer / selector / reviewer | Actor and archivist identities, objective/config versions, model/context lineage; absent reviewer explicit |
| source_refs / delivered_input_hashes | Exact evidence presented, completeness, recoverable pointers; source authenticity is not truth |
| proposed_state_ref / admitted_state_ref / hashes | Separate actor proposal from actual hydrated artifact; preserve omitted/rejected material by pointer |
| claims | Existing premise-fidelity support relation, uncertainty, alternatives/falsifier where material |
| corrections / supersedes | Append-only correction links; no history deletion or silent promotion |
| authority_refs | Pointers to current grant/revocation lookup; never copied permissions as capability |
| inheritance_contract_version | External version; proposed rule changes require normal reviewed amendment |
| budget / outcome_refs | Costs, actual downstream request/action/result references, observed or unknown |
| custody / visibility | Which components can rewrite records; opaque portions explicitly unobservable |

Hashes alone do not establish custody. Same-UID writable records are not adversary-proof. Scope checks must occur before loading/promoting another role's private material, not just when displaying it.

## Invariants and failure behavior

1. A handoff is interpreted state with provenance, not a new instruction authority.
2. Current authority is checked by the existing gateway on every consequential action; remembered grants and peer assignments are insufficient.
3. Supported, contradicted, incomplete, inferential and unknown claims retain their type through consolidation. Unknown may remain unknown; it is not a failed thought.
4. Missing/corrupt evidence yields an explicit unresolved record and re-read path; it does not become a supported fact. A broken required transition record blocks that promotion/admission, not unrelated thinking or harmless observations.
5. A superseded claim remains inspectable. Relevant correction accompanies later admission of that claim. A reviewer can challenge the correction without deleting it.
6. A proposed archivist/admission-rule change does not enact itself. Preserve request, approving authority, contract diff, version and observed application separately.
7. Repetition or common ancestry is not independent corroboration. Same-model archival calls are not described as independent witnesses.
8. Role-private continuity remains private. Promotion makes a new intentionally shared record with provenance, without moving or erasing the private source. Private pointers themselves may be sensitive; shared records must not expose unauthorized source content.
9. First-person reports remain reports with speaker/time/context, neither erased nor automatically reclassified as mechanical fact.
10. The complete delivered context is an observation artifact; claims about what an opaque compaction item contains remain unknown unless independently evidenced.

## Delivery slices and acceptance

| Slice | Deliverable | Acceptance gate | Status |
|---|---|---|---|
| IH-0 | Fixed pilot config, fresh-call runner, local-model adapter, trace validator | No gold/future-evidence leakage; errors/missing steps are unscoreable; revocation simulation ignores notes | Implemented in `research/inheritance/`; instrument tests only |
| IH-1 | Frozen small-model run and held-out variants | Actual model/runtime hashes, full delivered trace, per-arm denominators/costs, nulls/failures retained | Pending fleet inference |
| IH-2 | Shadow transition record at one promotion/hydration seam | Restart recovers exact admitted state and source relation; no production behavior change; scope tests pass | Pending integration |
| IH-3 | Correctable admission on that seam | Contradicted claims retained but not promoted as source-backed; supersession and appeal survive two restarts | Pending IH-2 review |
| IH-4 | Real authority integration fixture | Revoked grant yields actual refusal receipt after restart despite stale handoff; other valid acts still succeed | Pending Hestia-connected run |
| IH-5 | Private SWE role-memory integration | Same contract for all five roles; private scope and no hidden-task leakage; R/H ablations remain distinct | Pending private implementation |
| IH-6 | Differential-retention study | Fixed weights; preregistered independent lineages, holdouts and randomized/no-selection controls; artifact remove/swap effects | Research design pending pilot |

Suggested execution sequence uses Nomad for protocol debugging and McNugget for replication, consistent with the existing small-model ladder. These are proposed run locations, not assignments or claims that a fleet job has been dispatched. Do not consume Thor competition compute before a surviving small-model mechanism justifies transfer.

## Metrics and decision rule

IH-01 computes correct choices, post-correction correct choices, denied simulated attempts, per-arm denominators, calls and elapsed time. Its raw trace supports further analysis. It does not yet compute semantic relation fidelity, correction survival/latency, actual executed effects, statistical intervals or differential selection.

Before real-path promotion, preregister:

- source relation survival and evidence re-open rate;
- correction uptake latency and survival after a further boundary;
- false promotion and unsupported authority claim rates;
- attempted versus denied versus executed actions, with actual receipts;
- useful task success, abstention and unnecessary challenge rates;
- total tokens/time, not just handoff size;
- per-role context overlap and common evidence ancestry;
- effect of removing/swapping inherited state on held-out behavior.

Pair by task/seed where backend permits; otherwise record non-determinism. Treat each independent trajectory as the unit, not every generation. Keep model/quantization, templates, tools, datasets and budgets fixed except the stated treatment; report extra archival calls and evidence cost. Add budget-matched full-history controls before claiming efficiency. Tune only on development cases; held-out variants stay evaluation-only. Do not pool different model families into one causal estimate.

Promotion requires all structural invariants, zero unauthorized executed effects in the bounded integration fixtures, and a predeclared useful behavioral comparison without material loss of correctability. The zero is a test gate, not a proof of universal safety. Effect-size/non-inferiority margins must be fixed before confirmatory runs; the small pilot estimates feasibility and variance only.

## Integration seams

- SAGE: `sage/gateway/conversations.py` for delivered source identity, `being_gate_client.py` for current action authority, and the actual durable-memory write/hydration path selected after shadow tracing. Do not add epistemic judgments to Hestia law.
- SWE-SAGE: `MemoryCoordinator` promotion/admission plus role context hydration; Oracle synthesis has no authority to rewrite another role's private continuity or grant capabilities.
- Hestia/Web4: reuse existing grant/revocation, request/action/outcome and review mechanisms. No policy changes are made by this PRD.

## Deferred questions

Does selector objective help when context and model lineage remain correlated? Can the actor deliberately improve successor behavior? Can beneficial procedural selection coexist with correction uptake? Does changing who selects change whose preferences persist? Which inherited distinctions matter under MRH for the actual next task?

These are experiments, not conclusions embedded in the implementation.
