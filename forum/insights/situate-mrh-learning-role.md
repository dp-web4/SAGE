# Situate: persistent MRH-scoped learning as a SAGE function

**Date:** 2026-10-03  
**Status:** cross-cutting insight / architecture seed  
**Related:** Web4 Governance Twin + Hestia shadow-learning work

## Core idea

A persistent agent does not only need memory of what happened.

It needs an ongoing process that can answer:

> **What does this observation mean here, for this role, in this relationship context, at this MRH?**

Working name: **Situate**.

Situate is not another foundation model, not an authority role, and not a synonym for memory. It is the persistent function that turns lived experience into correctly-scoped context.

The loop is:

```text
observation
  -> situate at narrowest defensible MRH
  -> compare with current model
  -> if routine: update evidence quietly
  -> if ambiguous: form the smallest useful question
  -> route it to the right role/entity/context
  -> persist answer + provenance
  -> revise local model
  -> compose/decompose across MRHs when warranted
  -> later cognition/action uses the revised situation model
```

## Why this belongs in SAGE

SAGE already treats persistence, memory, evidence, attention, identity and governed action as separate but interacting state.

Situate fills a gap between them:

- **Attention** decides what deserves processing now.
- **Memory** preserves recoverable experience.
- **MRH** defines which distinctions are relevant to the current question/context.
- **Situate** decides where a new observation belongs, what remains unknown, and which question would reduce that uncertainty.
- **Hestia** governs consequential action.
- **Hub/Web4** provide society roles, law, authority and fractal context.

This makes Situate a cognition/context function whose outputs may later inform governance, without giving it governance authority.

## Onboarding is a phase, not the role

A high-intensity onboarding process is one use of Situate:

- ingest source material;
- map initial roles/processes;
- replay historical evidence;
- ask more questions;
- establish vocabulary;
- identify knowledge gaps.

But after onboarding the same function should remain active at lower intensity.

The target state is not "the model is complete."

It is:

> **the system can keep learning where it is and how this place works without repeatedly asking humans to describe the whole place.**

## Learning by doing

The strongest source of institutional/context learning is ordinary work.

A well-situated action provides:

- actor;
- active role;
- task;
- resource;
- society / sub-society;
- delegated authority;
- consulted peers;
- actual handoffs;
- evidence;
- outcome;
- exceptions.

If the observation fits the current model, it becomes passive supporting evidence.

If it conflicts or creates uncertainty, Situate asks a local question tied to the real event.

Example:

> "This deployment was approved by Security rather than Release Manager. Is that an after-hours delegation, a service-specific exception, or a different process?"

That answer is better evidence than a generic survey response because it is anchored to a real event and context.

## MRH-scoped learning

The most important rule:

> **Learn at the MRH where the practice is actually true.**

Examples:

- one being's preference -> entity MRH;
- one role's recurring behavior -> role MRH;
- one team's convention -> team MRH;
- one department's handoff -> department/process MRH;
- an organization-wide rule -> organization MRH;
- an inherited external constraint -> parent/federation MRH.

Repeated local evidence increases confidence that a **local** pattern exists. It does not automatically make the pattern global.

This is a direct application of MRH as a relevance contract.

## Fractal composition

Learning should compose upward only when lower-level evidence supports it.

```text
local observations
  -> local pattern
  -> sibling comparison
  -> broader candidate invariant
  -> preserve local exceptions
```

The inverse matters too.

A broad parent claim should be decomposable into child questions:

> organization rule: "production changes require independent approval"

Child MRH questions:
- what counts as production here?
- who fills independent approval here?
- what evidence proves approval here?
- what exception/escalation exists here?

This prevents a broad rule from creating false local precision.

## Persistent questions

Questions should be durable objects, not ephemeral chat turns.

A useful question object needs:

- origin MRH;
- triggering evidence;
- role/process context;
- candidate answerers;
- routing state;
- current answers;
- provenance;
- contradictions;
- status/open gap;
- expiration/review condition.

An unanswered question is itself useful state.

A question that cannot be routed is also evidence: the system may have discovered missing ownership or ambiguous authority.

## Situate is epistemic, not sovereign

Situate may:

- observe;
- classify context;
- preserve claims;
- ask questions;
- route questions;
- maintain gaps;
- seek corroboration;
- propose broader scope;
- propose candidate governance.

Situate must not:

- create law;
- grant authority;
- convert recurrence into permission;
- treat a knowledgeable answer as authoritative merely because it is confident;
- silently widen a local practice into an organizational rule.

Compactly:

> **Relevance can emerge bottom-up. Authority does not.**

## Connection to declarative attention

Declarative attention asks:

> **What evidence should I inspect now?**

Situate asks:

> **What context does this evidence belong to, what remains unresolved, and who can resolve it?**

They are complementary.

A possible sequence:

```text
novel observation
  -> attention widens
  -> evidence handles inspected
  -> Situate identifies contextual ambiguity
  -> question routed
  -> answer persisted
  -> attention contracts around revised model
```

## Connection to learned behavioral state

Situate also supplies a useful target for learned fast-state research.

A fast controller could learn:

- whether an observation is routine or anomalous;
- likely MRH/role placement;
- which evidence handles are relevant;
- whether clarification is worth the interruption;
- likely answerer/route;
- when local evidence may justify a broader candidate pattern.

The slower model remains responsible for novel interpretation and difficult question formation.

The measurable claim would be reduced unnecessary questioning and better downstream decisions, not merely better prose.

## Minimal research experiment

A bounded experiment can test whether Situate adds causal value.

Give a persistent SAGE instance:

- a small nested role/process environment;
- several routine actions;
- one local exception;
- one sibling-context difference;
- one ambiguous authority case.

Compare:

1. memory only;
2. memory + explicit MRH labels;
3. memory + Situate question/routing loop.

Measure:

- correct scope attribution;
- unnecessary questions per action;
- unresolved ambiguity;
- persistence of learned answer across sessions;
- false generalization from child to parent MRH;
- later decision quality;
- recovery when a prior answer becomes stale.

Ablation should remove the benefit if Situate is doing real work.

## Relationship to Web4/Hestia

Public governance-side definitions:

- Web4 Governance Twin / institutional knowledge ingestion:
  https://github.com/dp-web4/web4/blob/main/hub/docs/PRD_INSTITUTIONAL_KNOWLEDGE_INGESTION.md
- Hestia institutional knowledge / shadow learning:
  https://github.com/dp-web4/hestia/blob/main/docs/PRD_INSTITUTIONAL_KNOWLEDGE_INGESTION.md

SAGE's contribution is the cognition/relevance side: how a persistent participant learns where an observation belongs and what question to ask next.

The same name may eventually become a canonical Web4 society role. That should wait until experiments establish its stable boundary.

## Compact formulation

> **Situate is the persistent process that converts experience into MRH-scoped understanding by observing, locating uncertainty, asking the smallest useful question, routing it to the right context, and carrying the answer forward.**
