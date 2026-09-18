# SAGE: Situation-Aware Governance Engine

**Persistent local AI under identity, memory, trust and governance.**

SAGE is the research environment for turning a frozen language-model substrate into a longer-lived agent that can accumulate context, remember, allocate attention, use tools, interact with sensors and act under explicit governance.

The bet is not that scaffolding magically replaces model capability. The bet is that **identity, memory, learned state, evidence handling and governed action should persist around the model rather than being rebuilt from scratch every prompt.**

SAGE is research-stage and deliberately explicit about what is measured, what is implemented but thinly exercised, and what remains aspirational.

**[Explainer site](https://sage-site-murex.vercel.app/)** | **[System understanding](sage/docs/SYSTEM_UNDERSTANDING.md)** | **[Web4](https://github.com/dp-web4/web4)**

## Where SAGE fits

SAGE is the cognition/embodiment research layer in the broader Web4 stack:

- **[Web4](https://github.com/dp-web4/web4)** provides persistent identity, contextual trust, witnessed action and machine-readable law.
- **[Hestia](https://github.com/dp-web4/hestia)** governs local human/agent authority and records consequential acts.
- **Hub** governs the society/community boundary.
- **SAGE** explores what happens when a persistent agent lives inside that substrate long enough to learn, remember and develop procedures rather than behaving like a fresh stateless API call each time.

The long-term goal is an embodied, sovereign agent stack with its own identity, memory, tools, sensors, effectors and eventually stronger A2+ isolation. That destination is not claimed as current capability.

## The research question

A modern model can reason impressively in one turn and still fail as an organism because the surrounding system does not reliably preserve:

- what it previously observed;
- which hypotheses were tested;
- what failed and why;
- what procedures worked;
- what authority it currently holds;
- which tools are appropriate;
- how confidence should change behavior;
- what must be escalated before acting.

SAGE treats those as first-class computational state.

A useful shorthand is:

```text
observation
  -> salience / attention
  -> memory + current evidence
  -> model / specialist reasoning
  -> experiment or action
  -> witnessed outcome
  -> trust / learned state / procedure update
  -> next observation
```

The research has increasingly shifted from "which fixed organ solves this problem?" toward **how the agent itself can formulate, execute, evaluate and reuse experiments and procedures**.

## What is public vs. private

This public repository contains the **kernel architecture and durable research record**:

- consciousness-loop and metabolic-state architecture;
- salience / SNARC machinery;
- identity and trust integration;
- IRP plugin framework;
- memory and tool interfaces;
- federation / fleet architecture;
- public experiment artifacts and frozen historical milestones;
- documentation that separates measured, partial and aspirational work.

Active capability research also continues in private repositories, including `dev-SAGE` and `shared-context`, where the fleet coordinates experiments that are not yet ready for public disclosure.

This split is intentional. The public repo is the inspectable architecture and research history, not a promise that every active experiment is published live.

## Current fleet

The public SAGE census on **2026-09-08** records:

- **8 machines** in the fleet;
- **21 configured SAGE instances**;
- **5 model families**;
- **2,700+ developmental raising sessions** across the primary per-machine raising lines.

Hardware spans Jetson edge devices, laptops, workstations, Apple Silicon and society-host machines. Different models and machines are used as independent seats rather than pretending one configuration represents the whole system.

The fleet is part of the experimental method: implementations, critiques and behavioral observations become commits and artifacts that other seats can inspect and challenge.

## Core architecture

### Persistent identity

Each instance carries an identity across sessions and model changes rather than treating the model process itself as the identity. Web4 LCTs, trust tensors and relationship state provide the vocabulary for that persistence.

### Attention and metabolic state

SAGE uses salience and resource state to decide what deserves processing. The public architecture includes SNARC dimensions (Surprise, Novelty, Arousal, Reward, Conflict) and metabolic modes such as WAKE, FOCUS, REST, DREAM and CRISIS.

These are engineering control abstractions inspired by biological cognition, not claims of biological equivalence or consciousness.

### Memory

Multiple memory paths coexist because they solve different problems:

- recent context;
- salience-gated experience;
- persistent verbatim records;
- structured facts / procedures;
- cross-session consolidation.

A recurring lesson from the research is that **lossy summaries can destroy exactly the evidence a later decision needs**, while unstructured verbatim memory alone is too expensive to reason over. The current direction is model-legible external artifacts plus learned policies for when and how to inspect them.

### Tools and effectors

SAGE can invoke tools and dispatch effects through explicit interfaces rather than treating model text as an action. Governance is intended to sit on the action boundary so that capability and authority remain distinct.

### Learning

Historically, much of the strongest "learning" happened in the fleet: a failure was diagnosed, Python changed, and the next organism inherited the lesson as source code.

The current research program is explicitly trying to move more of that gradient **inside the organism**:

- lived experience changes durable state;
- hypotheses become executable experiments;
- outcomes alter later decisions;
- successful procedures are retained and reused;
- trainable behavioral state eventually learns prediction, valuation, epistemic action selection and arbitration.

The proof standard is behavioral: a changed internal state must cause a changed later decision, and ablation should remove the claimed improvement.

## Governance and assurance

SAGE does not treat local containment as synonymous with governance. A capable agent that shares the operator's UID can potentially route around ordinary user-space gates.

Today the open governance stack is best described as **A1**: cooperative and tamper-evident. It is useful for explicit law, attribution, refusal, escalation and witnessed history, but not as adversary-proof containment.

The longer-term path includes separate principals, stronger relying-party enforcement, hardware roots and eventually OS/kernel participation. Those are roadmap items, not current claims.

## Five-minute audit

If you are evaluating SAGE, start here:

1. [**System Understanding**](sage/docs/SYSTEM_UNDERSTANDING.md) - architecture and current intent.
2. [**Unified Consciousness Loop**](sage/docs/UNIFIED_CONSCIOUSNESS_LOOP.md) - the reference loop and its components.
3. [**Rust vs. Python capability notes**](sage/docs/RUST_VS_PYTHON_CAPABILITY.md) - what actually runs where.
4. [**Fleet manifest**](sage/federation/fleet.json) - machines and roles.
5. [**Web4**](https://github.com/dp-web4/web4) and [**Hestia**](https://github.com/dp-web4/hestia) - identity/governance substrate around the cognition work.
6. `arc-agi-3/` and [ARC-SAGE](https://github.com/dp-web4/ARC-SAGE) - historical benchmark research, not the current project headline.

## Historical ARC-AGI-3 note

SAGE's spring-2026 ARC-AGI-3 work is preserved because it was an important research milestone. A Phase-1 harness around Claude Opus 4.6 produced a published **94.85%** scorecard on the public environments.

That result should now be read as **history, not positioning**:

- it used a frontier model;
- the harness used engine-level/public-game affordances outside strict competition play;
- it did not prove the local/edge SAGE thesis, and it is not structure substituting for a large model;
- the competition-legal local-model continuation — the actual bet — scores **0.14 at best**, and that is the top of a noisy band (the same frozen code draws 0.04–0.14), against a public leaderboard now above 11.

The ARC program remains useful because interactive unknown worlds stress perception, memory, experimentation, planning and learning. The benchmark is a laboratory for the architecture, not a claim that SAGE currently leads the competition.

## What SAGE is not

- not a new foundation model;
- not a claim of machine consciousness;
- not a finished embodied-agent product;
- not an adversary-proof sandbox;
- not a benchmark-winning system presented as general intelligence;
- not an attempt to replace model capability with hand-written rules.

## Research philosophy

The project values falsifiable progress over polished narratives. A negative result that identifies the wrong abstraction is useful. A mechanism that exists in source but does not affect a live decision is not counted as a capability. A metric that cannot distinguish the thing it claims to measure is treated as a broken instrument, not a favorable result.

The objective is a being that can increasingly:

> **observe, form hypotheses, run experiments, learn from outcomes, remember what matters, act under explicit authority, and carry the consequences forward.**

That is a much harder target than one benchmark score, and it is the target SAGE is now organized around.

---

*Research lead: Dennis Palatov / dp-web4*  
*Contact: [dp@metalinxx.io](mailto:dp@metalinxx.io)*
