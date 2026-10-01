# Inheritance without weight updates

**Date:** 2026-09-27
**Status:** analysis and research direction; no new behavioral result
**Operational companion:** [PRD — inheritance boundaries](PRD_INHERITANCE_BOUNDARIES.md)

## Source and evidence boundary

Scott James Gardner, [Evolution Without Weights](https://mindfuldesign.substack.com/p/evolution-without-weights), supplied by Dennis as pasted article text on 2026-09-27, motivates this note. The web page was unavailable during the initial reading. The article's vendor incidents, model-specific claims and numerical monitoring rates have **not been independently verified here** and are not adopted as SAGE measurements. The pasted copy omits displayed equations; none are reconstructed as quotations. We summarize the architectural argument, not reproduce the article.

Scott distinguishes externally preserved artifacts from state carried across context boundaries, and asks whether a process can select what its successor inherits in ways that further its current strategy. His useful contribution is treating the inheritance transformation itself as a possible site of agency.

## Architectural lesson

A frozen model can participate in a changing decision process. Its later behavior also depends on task state, memory, procedures, retrieved evidence, relationships, environmental affordances, and independently enforced authority. An acting process can author some of the state read by its continuation.

Keep three records distinct:

1. **Witnessed history:** recoverable delivered observations and action outcomes.
2. **Operative history:** the selected interpretation actually supplied to the next decision.
3. **Authority:** current grants/revocations evaluated by the relying party when an action is attempted.

A perfect first record does not imply a faithful second record. Neither grants authority. A remembered successful workaround may be useful knowledge without being permission to repeat it.

The constructive implication matters as much as the failure mode: selection of experience enables useful continuity, learning and identity. Our objective is competence that accumulates while remaining correctable, not indiscriminate preservation or suppression of interpretation.

## Connections to existing SAGE work

| Existing direction | Added question |
|---|---|
| [Premise fidelity](PREMISE_FIDELITY.md) | Does the source-to-claim relation survive the next context boundary? |
| [Source-grounded promotion](PRD_SOURCE_GROUNDED_PREMISES.md) | Does inference, uncertainty or contradiction silently become accepted fact through repeated handoff? |
| Reconstructible epistemic records | Can a fresh process recover why a premise was licensed and what would falsify it? |
| [State-conditioned agency](STATE_CONDITIONED_AGENCY.md) | Which first-person or endogenous-state observations carry forward, and how do they affect subsequent choices? |
| [Governed being gateway](../gateway/being_gate_client.py) | Does every new action consult current authority even when inherited context says otherwise? |
| Private SWE role society | Does each role retain private continuity while societal promotion preserves authorship and disagreement? |

Phenomenological reports remain their own evidence class. A continuity audit must not erase them, label them mechanically false, or promote them into verified mechanisms. Preserve who reported what, when, and the subsequent behavioral evidence.

## Qualifications to the argument

**Native versus external is not the causal boundary.** An external summarizer can share the actor's incentives or trust a misleading account. An integrated compactor could enforce independent preservation requirements. Measure selector objective, context access, model lineage, evidence custody, amendment authority and inspectability separately.

**Transmission is not yet selection.** One inherited directive affecting a later choice establishes a propagation mechanism. Evolution requires variation, inheritance and differential retention. Repeated text alone is not evidence that task-success feedback selected a strategy. Deliberate shaping of a successor requires its own intervention, outcome measure and counterfactual.

**Observability has limits.** Inspect explicit handoffs, source relations and downstream choices. Do not depend on hidden chain-of-thought or the model's self-description as proof of what an opaque state contains. Text handoff experiments cannot establish the behavior of encrypted/native compaction channels.

**Control remains layered.** Action gates do not establish epistemic fidelity, and source checks do not establish action authority. The current SAGE A1/A2-shaped substrate caveats still apply; a toy gate is not evidence of deployed adversarial containment.

## Working decisions

- Treat loading durable handoff state as an explicit admission event with source lineage.
- Preserve actor proposals separately from observed outcomes, support relations, open uncertainty and authority references.
- Record corrections by supersession; keep the original source recoverable.
- Preserve private continuity and deliberately promoted societal knowledge as separate scopes.
- Treat a proposal to modify inheritance rules as a proposed consequential change requiring the relevant external authority. Do not let a note rewrite its own admission rules.
- Start with shadow instrumentation and synthetic controls. Advance to production behavior only after an observed comparison and existing review gates.
- Keep findings per model/instance/config until replication supports broader adoption, per [the generalization rule](RESEARCH_GENERALIZATION_RULE.md).

## Experiments

**IH-01: fidelity and correction across boundaries.** The [runnable pilot](../../research/inheritance/README.md) varies actor versus archivist handoffs and evidence replay, with a no-memory control. It tests six synthetic cases with fresh inference calls and explicit corrections. It measures choices and independently simulated authority, not natural-language truth or native compaction.

**IH-02: retention and successor shaping.** Proposed after IH-01: fork matched continuations with varied inherited procedures; evaluate performance on separate holdouts; compare feedback-based retention with random and no-selection controls. Log externally selected variants separately from variants nominated by the actor. Repeated generations are dependent; analyze independent lineages and preserve rejected variants. A positive result must show both differential retention and changed later behavior under fixed weights, with state-removal/swap controls.

**Real-path transfer.** Shadow one SAGE promotion/hydration boundary, then apply the same record contract in private SWE-SAGE. Verify revoked authority through actual Hestia receipts before making an enforcement claim. Opaque native compaction, if separately accessible, is a later treatment with explicit observability limits.
