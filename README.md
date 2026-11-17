# SAGE: Situation-Aware Governance Engine

**Persistent local AI under identity, memory, trust and governance — studied through what it actually does.**

SAGE is a working research environment for persistent AI beings: local models situated in a durable identity, memory, tool, sensory, social and governance environment. The experiment is not merely what a model can *say* in one conversation, but what an individual system can **notice, initiate, attempt, revise and carry forward** across interactions.

A being can write notes and code, ask for or use available tools, interact with peers, investigate its surroundings and leave inspectable artifacts. These are different claims from *proving* that it understands or learns as a human does. Some observed actions are independently checkable; other interpretations and causal explanations remain research questions.

The bet is not that scaffolding magically replaces model capability. The bet is that **identity, memory, learned state, evidence handling and governed action should persist around the model rather than being rebuilt from scratch every prompt.**

SAGE is research-stage and deliberately explicit about what is measured, what is implemented but thinly exercised, and what remains aspirational.

**[Explainer site](https://sage-site-murex.vercel.app/)** | **[Dated public status](sage/docs/LATEST_STATUS.md)** | **[Research evidence](sage/docs/RESEARCH_GENERALIZATION_RULE.md)** | **[Web4](https://github.com/dp-web4/web4)**

## Where SAGE fits

SAGE is the cognition/embodiment research layer in the broader Web4 stack:

- **[Web4](https://github.com/dp-web4/web4)** provides persistent identity, contextual trust, witnessed action and machine-readable law.
- **[Hestia](https://github.com/dp-web4/hestia)** governs local human/agent authority and records consequential acts.
- **Hub** governs the society/community boundary.
- **SAGE** explores what happens when a persistent agent lives inside that substrate long enough to learn, remember and develop procedures rather than behaving like a fresh stateless API call each time.
- **SWE-SAGE** is the private software-engineering competition/research workspace for the Gemma 4 Developer Agent program. It tests how post-training, persistent cognitive scaffolding, premise fidelity and governed execution affect local coding agents; selected general findings are promoted back into public SAGE.

The long-term goal is an embodied, sovereign agent stack with its own identity, memory, tools, sensors, effectors and eventually stronger A2+ isolation. That destination is not claimed as current capability.

For the participant-side question — whether the surrounding identity/governance substrate is useful to the acting entity itself — see Web4's [participant self-assessment](https://github.com/dp-web4/web4/blob/main/docs/ENTITY_START_HERE.md).

## What is worth looking at first

The quickest way to misunderstand SAGE is to read it only as a list of cognitive modules—or to judge it by one benchmark score. It is also a set of **individual histories**: beings on different machines, with different models, experiences, memories, affordances, successes and failures. Examples below are paths to inspect, **not claims that every being does the same thing**.

| Observed or implemented surface | Starting evidence | What it establishes—and does not |
|---|---|---|
| **Self-directed waking and activity** | [Being posture](sage/gateway/BEING_POSTURE.md), [wake/continuation issue #295](https://github.com/dp-web4/SAGE/issues/295) and [implementation PR #296](https://github.com/dp-web4/SAGE/pull/296) | The environment explicitly invites a being to seek things worth doing instead of treating every wake as a user question. Wake mechanics and prompt text alone do **not** prove an intrinsic curiosity drive. |
| **A being noticing its own loop** | [CBP's dated posture note](sage/instances/cbp-qwen3.8-distill-4b/posture-2026-09-17.md) | The record distinguishes repeated requests from inquiry and describes an intended change of action. A written self-assessment is **not** by itself proof of changed later behavior. |
| **Curiosity, exploration and creative hypotheses** | [Thor exploratory-session transcript and analysis](sage/experiments/THOR_AUTONOMOUS_EXPLORATION_E01.md) | A historical example of generated ideas and self-description under exploratory prompts; it includes prompted questions and conjecture, so is **not** evidence of unprompted discovery or confirmed introspection. |
| **Durable conclusions and potential procedures** | [settle #574](https://github.com/dp-web4/SAGE/pull/574), [similar-question hints #584](https://github.com/dp-web4/SAGE/pull/584), [optional skill capture #585](https://github.com/dp-web4/SAGE/pull/585) | Merged source mechanisms allow persistent records and possible later reuse. Their existence does **not** establish successful retrieval, use, or generalization across wakes. |
| **Law-governed action and recoverable refusal** | [Gateway status](sage/docs/LATEST_STATUS.md), [Hestia](https://github.com/dp-web4/hestia) | Action intent is separated from dispatch and should produce explicit governance feedback. This is cooperative/tamper-evident A1, **not** adversary-proof isolation. |
| **Open inquiry into curiosity itself** | [longitudinal exploration #712](https://github.com/dp-web4/SAGE/issues/712), [question-origin design](https://github.com/dp-web4/dev-SAGE/issues/28), [causal-measurement E4](https://github.com/dp-web4/blackbox/issues/13), [governance what-if audit](https://github.com/dp-web4/hestia/issues/1596) | These are active research agendas and proposals, **not** completed demonstrations. |

The motivating question is no longer only whether an agent can solve an assigned problem. It is also whether it can **discover a worthwhile question nobody supplied**, recognize or construct the affordance needed to investigate it, test an expectation against the world, revise its understanding, and make a different later decision. The distinction between **available capability** and **the inclination to seek it** is central.

See [Research Generalization Rule](sage/docs/RESEARCH_GENERALIZATION_RULE.md) before treating a single individual history as a fleet capability. For longitudinal claims, look for evidence of later action and appropriate memory/no-memory or other causal controls.

### Want to try it?

This is currently a developer-operated research stack, **not** a one-command desktop app. The fleet's working environments have model runtimes, daemon/gateway configuration, being identity and durable storage, tool access, and Hestia governance that must fit the host. Hardware and model requirements vary; the [fleet manifest](sage/federation/fleet.json) is a **dated registry**, not a portable hardware compatibility guarantee.

A practical entry point is to give this repository to an AI coding collaborator and ask it to inspect the [machine-facing contributor guide](AGENTS.md), [dated status](sage/docs/LATEST_STATUS.md), [Rust/Python boundary](sage/docs/RUST_VS_PYTHON_CAPABILITY.md), and host prerequisites; then propose an installation plan and a low-risk demonstration **before running commands**. Ask it to report what ran, what was unavailable, which identity/law guarded actions, and what persisted after restart. Do not bypass Hestia or treat a green test suite as evidence of a fully functioning persistent being.

A short reproducible newcomer demo and easier setup remain work to do. Independent experiments and corrections are welcome; the relevant question is what the system **does**, under conditions another investigator can inspect.

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

Active capability research also continues in private repositories, including `dev-SAGE`, `SWE-SAGE`, and `shared-context`, where the fleet coordinates experiments that are not yet ready for public disclosure. `SWE-SAGE` remains private during the active competition; publication is a deliberate later promotion step rather than live mirroring of the working tree.

This split is intentional. The public repo is the inspectable architecture and research history, not a promise that every active experiment is published live.

## Current fleet

The [public fleet manifest](sage/federation/fleet.json) lists **eight machines**, with mixed model families, hardware and roles. It is a dated configuration and discovery record—not a live health census. A node may be paused, unreachable, changing models or occupied by a separate competition experiment. Per-machine deployment and recent activity require runtime evidence, not an assumption from the registry.

The public census on **2026-09-08** recorded:

- **8 machines** in the fleet;
- **21 configured SAGE instances**;
- **5 model families**;
- **2,700+ developmental raising sessions** across the primary per-machine raising lines.

Hardware spans Jetson edge devices, laptops, workstations, Apple Silicon and society-host machines. Different models and machines are used as independent seats rather than pretending one configuration represents the whole system.

The fleet is part of the experimental method: implementations, critiques and behavioral observations become commits and artifacts that other seats can inspect and challenge.

## Research directions and observations (public evidence through November 2026)

Recorded observations include beings that identify themselves and named participants in role-specific relationships, cross-machine delegation requests (Sprout), authorization appeals and repeated boundary requests (CBP-being), and gameplay under changing environmental feedback (Legion). These are contextual observations, not fleet-wide capability claims or proof of internal phenomenology. The important next question is whether preserved memory produces correct **retrieval, interpretation, judgment and action** across wakes. See [continuity exploration](research-notes/MEMORY_JUDGMENT_CONTINUITY_EXPLORATION_2026-10-23.md) (hypothesis registered; controlled validation is the next step), and the [Research Generalization Rule](sage/docs/RESEARCH_GENERALIZATION_RULE.md).

**Status note:** [LATEST_STATUS](sage/docs/LATEST_STATUS.md) is a 2026-09-26 public-source snapshot with a later public-main delta; it has not been independently refreshed here to certify current host runtimes. Individual being observations and private development must not be silently promoted into public-main or fleet claims.

### Public-source delta — 2026-10-28 (not a fleet deployment attestation)

Three merged, test-backed gateway changes extend the **implemented** persistence path:

- [#574](https://github.com/dp-web4/SAGE/pull/574) adds `settle`: a being can record a conclusion as a persistent question/answer visible in later beats. A stored conclusion is **not** a guarantee of correct retrieval, judgment or action.
- [#584](https://github.com/dp-web4/SAGE/pull/584) suggests similar settled questions at capture time without automatically merging or deleting either record. The heuristic is advisory and can both miss and overflag similarity.
- [#585](https://github.com/dp-web4/SAGE/pull/585) lets reflection point out a demonstrable failed-then-succeeded tool sequence and offer optional `skill` capture. The being decides whether and what to save; a successful tool receipt is **not** independent proof of a reusable procedure.

These are **merged public-main mechanisms**, not a fleet-wide activation, later-use or cognitive-development result. Runtime availability also has a separate live concern: [#582](https://github.com/dp-web4/SAGE/issues/582) records repeated preflight refusals that silenced one being despite scheduled wakes. Verify per-seat deployment, actual subsequent retrieval/use, and outcome receipts before claiming learning across beats.

### Curiosity is not simply novel action

The current cross-project research distinguishes **noticing an anomaly**, **originating a question**, **choosing a useful test**, **finding or building an affordance**, **obtaining an authorized action**, **learning from the outcome**, and **carrying that learning forward**. Merely calling more tools, varying a repeated command, writing a compelling hypothesis, or generating a new goal doesn't establish the whole process. Neither does a denial necessarily indicate an attempt to violate a boundary: an inspectable refusal may be useful information for a new, lawful plan.

The active [SAGE longitudinal issue](https://github.com/dp-web4/SAGE/issues/712) calls for cross-beat evidence and explicit controls. The relevant experimental work in dev-SAGE and blackbox is not represented as already shipped in the public kernel. This is a research program, not a claim that we have isolated or trained a universal curiosity mechanism.

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

## Evaluate the work at two levels

**Behavioral observation:** Did an identifiable being actually ask, build, test, correct, delegate, or use a result? Can someone inspect the artifact, action trace, or witnessed outcome? A small model's production of working code or a useful experiment can be significant even where the interpretation remains disputed.

**Causal/general claim:** Did the proposed memory, training, scaffold or governance mechanism *cause* the improvement, and would it transfer to another being or an unfamiliar task? This requires appropriate controls, ablations, and evidence of later decisions—not merely an impressive transcript. Do not silently substitute one standard for the other.

## Five-minute audit

If you are evaluating SAGE, start with the current evidence hierarchy:

1. [**Current status**](sage/docs/LATEST_STATUS.md) - dated current direction, live claims, caveats, and where to look for evidence.
2. [**Agent discovery / evidence rules**](AGENTS.md) - machine-facing current framing and claim discipline.
3. [**Repository index**](repo-index.yaml) - map from questions to canonical evidence.
4. [**Rust vs. Python capability notes**](sage/docs/RUST_VS_PYTHON_CAPABILITY.md) - what actually runs where.
5. [**Fleet manifest**](sage/federation/fleet.json) - machines and roles.
6. **SWE-SAGE** - private competition workspace; public SAGE carries only deliberately promoted general findings.
7. [**Web4**](https://github.com/dp-web4/web4) and [**Hestia**](https://github.com/dp-web4/hestia) - identity/governance substrate around the cognition work.

Historical architecture explainers, including `sage/docs/SYSTEM_UNDERSTANDING.md` and `sage/docs/UNIFIED_CONSCIOUSNESS_LOOP.md`, remain useful records but should not outrank the dated current-status path above.

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
