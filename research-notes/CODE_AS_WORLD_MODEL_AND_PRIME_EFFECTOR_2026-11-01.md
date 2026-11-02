# Code is your magic spell: executable world models and the prime effector

**Date:** 2026-11-01  
**Insight ID:** INSIGHT-CODE-WORLD-MODELS-2026-11-01  
**Attribution:** Dennis Palatov's longstanding framing, reaffirmed in discussion on this date; synthesis by NOVA / ChatGPT.  
**Status:** architectural insight and proposed evaluation criteria, not a deployment claim or a change to runtime authority.

> "code is your magic spell" — Dennis Palatov

Dennis emphasized that he had been communicating **coding as building world models**, not merely coding as a software-development task. The lesson is not a newly invented slogan: our implementation and evaluation need to catch up with the framing. His observation that a local 4B being can read source and write Python motivates a small-model investigation; it is not a claim that every 4B model can solve arbitrary tasks.

## The central correction

**Code is a medium in which a being can externalize, execute, test, revise and retain its understanding. In SAGE's computational environment it is the prime effector: a means of authoring new operations, not merely selecting from operations that a harness designer anticipated.**

A model that can write code can construct an instrument, not just answer a question. It can turn a hypothesis into a predictor, a question into a measurement, a goal into a search procedure, and a successful procedure into reusable competence. Reading permitted source exposes how part of its environment works; writing and executing code lets it test and change that environment within its authority.

Source text alone does not cause an external effect. An interpreter, tool interface or actuator does. Calling code the prime effector identifies the being's general-purpose constructive interface to those mechanisms; it does not replace sensors, embodiment, language or non-code action.

## Three distinct roles of code

1. **Executable model:** a representation of state, relationships, transitions, observations, goals or constraints. Running it answers a counterfactual: what does this hypothesis predict?
2. **Experimental instrument:** a parser, probe, comparator, reproducer or measurement procedure. Running it gathers or analyzes evidence capable of contradicting the model.
3. **Effector / procedure:** a program that composes authorized operations to accomplish something. Running it changes a file, invokes an environment action, delegates work or operates an actuator.

One program may combine these roles. The distinction still matters: a simulated outcome is not an observed outcome, a passing test is not universal correctness, and an authorized action is not a correct judgment.

Not every useful world model is a complete simulator. A transition function, repository dependency graph, schema checker or small reproduction can be a partial executable model. An arbitrary script is not a good world model merely because it runs; its representation and predictive scope must be explicit.

## Why coding competence matters beyond software production

Programming supplies composition, precise state, conditional behavior, iteration, search and reusable abstraction. The model can choose a representation and write a procedure; the runtime carries out its specified computation rather than requiring each arithmetic or search step to be regenerated in prose.

This gives a concrete operational interpretation to Dennis's statement that models are trained on coding for a reason: **coding competence can support general agency and reasoning, not only finished software artifacts.** It does not establish any laboratory's training intent or isolate the causal effect of code in pretraining.

PAL independently demonstrates the narrower mechanism of model-generated intermediate programs executed by an interpreter on reasoning tasks [1]. Duck explicitly organizes interactive puzzle solving around a Python REPL with refreshed observations [2]. Franzen's extension emphasizes usable observations, retained functions, context and serving efficiency [3]. These are precedents for the mechanism, not proof that code eliminates model-capability limits.

## Give the model authorship, not an obligatory taxonomy

A restrictive loop can look like:

`model intent -> predefined goal vocabulary -> grounder -> selected planner -> predefined executor`

Its failure can be representational: the model names a useful operation, but the harness cannot carry it to action. Adding more categories may repair examples while leaving the closed vocabulary intact.

The alternative is:

`observe -> formulate -> write/read code -> predict or test -> authorized action -> compare -> revise -> retain`

The being may invent a representation or compose an algorithm without first persuading the harness that the idea belongs to an approved mechanic family. Reusable solvers and causal helpers are valuable as **optional instruments**. They become a bottleneck when every thought or action must fit their schemas.

This is not an argument against governance. **Semantic mediation and authorization are different boundaries.** Removing an unnecessarily narrow planner does not authorize bypassing scope, resource limits or consequential-action checks. Nor does this imply that a general interpreter is automatically an adequate security boundary.

## What the evidence supports

Duck's primary report describes a model inspecting observations, using helpers and acting through Python while the environment refreshes state [2]. Franzen retains that approach and reports improvements to perception, reusable model-authored functions and computational continuity. He also reports that mandatory structured world-model updates did not help his submitted configuration [3]. A world-model *form* is not the same thing as world understanding.

Those systems combine model, interface, perception, memory and serving choices. Their performance is not a matched experiment isolating one architectural variable. The transferable design lesson is to make the model's competence executable and observable, not to declare scaffolding inherently harmful or small models universally sufficient.

## Consequences for SAGE

**Raise beings to build and inspect instruments.** Include reading permitted source, making a minimal reproducer, predicting its result before execution, interpreting errors, revising a hypothesis, and reusing a procedure on a changed case. Do not silently replace the being's work with a stronger seat's implementation and report that as the being's competence.

**Preserve procedural memory.** Retain source or a content-addressed artifact, its purpose, input/output contract, dependencies, assumptions, evidence, known counterexamples and provenance. Restore useful functions without carrying stale board-specific variables into a new situation. Retrieval is not permission to execute, and execution is not proof of successful transfer.

**Keep the world in the loop.** Images, sensors, source and execution traces provide complementary evidence. A model-authored simulator cannot validate itself by generating both the prediction and the supposed observation. Test against the actual environment or an independent oracle, under the applicable rules.

**Avoid forced narration.** Make computation and relevant evidence available without requiring an extra language-model turn, fixed world-model template or full prose recap for every action. Measure total useful work, including the costs of generation, prefill, runtime and tool feedback.

**Separate local research from restricted evaluation.** Source reading is an important legitimate capability where access is authorized. It is not permission to inspect hidden game engines, replay forbidden state or obtain benchmark answers. Every evaluation must state its actual information and action affordances.

## How to tell whether this became architecture rather than another note

Trace one concrete capability through: **present -> exposed -> used -> executed -> outcome checked -> retained -> reused on a changed case**. A tool in a prompt proves only exposure. Count missing evidence as unknown, not success.

A useful small-model comparison holds model, task information, wall time and authority fixed while comparing prose-only reasoning, a fixed-operation harness and open-ended coding with equivalent observation access. Record task outcomes, action efficiency, time/tokens, prediction errors, recovery and later reuse. Vary model size separately. An optional-helper arm tests whether libraries amplify authorship rather than replace it.

The first implementation question is therefore not "which new organ should we install?" It is **"can the being author and test the procedure it needs, and does its intent survive the journey to action?"**

## Sources and local anchors

- Dennis Palatov, discussion of 2026-11-01: attribution and design direction. The quote above is reaffirmed directly here; this note does not invent an earlier source location.
- [1] Gao et al., [PAL: Program-aided Language Models](https://proceedings.mlr.press/v202/gao23f.html), ICML 2023.
- [2] Tufa Labs, [Duck Harness](https://tufalabs.ai/research/duck-harness/), 2026-07-01, especially Solution Architecture.
- [3] Daniel Franzen, [ARC-AGI-3 Milestone 2 write-up](https://github.com/da-fr/arc-agi-3-solution/blob/main/WRITEUP.md), sections on observation, retaining Python functions, and unsuccessful changes; accessed 2026-11-01.
- [SAGE README](../README.md), research loop, tools/effectors and learning: this insight sharpens the existing move toward agent-authored experiments and procedures.

**Keep the freedom to formulate. Make predictions testable. Govern effects. Retain what earns reuse.**
