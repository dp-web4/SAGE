# Exploration: Optional executable world models — lessons from Tufa Labs' ARC-AGI-3 Seal

**Date:** 2026-11-09  
**Status:** Proposed exploration; no SAGE implementation or new A/B result claimed  
**Scope:** SAGE cognitive affordances, model-owned experimental instruments, prediction/falsification, and resource-aware reasoning  
**External result:** Tufa Labs' second-place ARC-AGI-3 competition score, **70.24** (reported); their final released solver is **Seal**, not the July Duck milestone code.

## Question

**When does a being decide that understanding is worth constructing before it acts, and how does that choice change with experience, uncertainty, stakes, and resource constraints?**

More operationally: does offering a persistent, model-authored, *optional* executable world-model interface improve a SAGE being's transfer, calibration, or task completion versus identical access to observation and action tools without that interface? The being—not a harness classifier—must choose whether and when to use it.

This is an exploration of a general-purpose cognitive affordance, **not** an initiative to copy a game solver or make formal modeling mandatory.

## Correct source and provenance

This exploration concerns Tufa Labs' **November 2026 final competition release**, not their July 2026 milestone solution:

- [Final released monorepo](https://github.com/Tufalabs/arc-prize-2026) — [ARC3 entry](https://github.com/Tufalabs/arc-prize-2026/tree/main/arc3)
- [Final submitted agent](https://github.com/Tufalabs/arc-prize-2026/tree/main/arc3/packages/seal) — `SealAgent.build(environment="kaggle-rtx")` per `arc3/README.md`
- [Seal contract and code](https://github.com/Tufalabs/arc-prize-2026/tree/main/arc3/packages/seal/src/seal): `model.py`, `py_model.py`, `search.py`, `repl.py`, `harness/test.py`, `presets.py`
- [Their evidence ledger](https://github.com/Tufalabs/arc-prize-2026/blob/main/arc3/packages/seal/evidence.md), and [design](https://github.com/Tufalabs/arc-prize-2026/blob/main/arc3/packages/seal/design.md)
- [Competition write-up](https://tufalabs.github.io/arc-writeups/arc3_writeup/arc3_writeup.html), [supplementary experiments](https://tufalabs.github.io/arc-writeups/supplementary/overview.html), [submission notebook](https://www.kaggle.com/code/jeroencottaar/tufa-labs-arc3-final-solution)
- [Training and serving source](https://github.com/Tufalabs/arc-prize-2026/tree/main/training), [their modified vLLM](https://github.com/Tufalabs/arc-prize-2026-vllm)

The code explicitly calls this a *cleaned copy* of the submitted implementation. We have inspected its source and published measurement notes; **we have not reproduced their Kaggle score or run their A/Bs locally**. Do not treat correlational score differences or multi-variable competition changes as isolated causal proof.

## Findings: what Tufa actually built

### F1. An executable, model-authored, falsifiable *partial* world model

Seal retains Duck's model-driven CodeAct loop but adds optional model-written `world_model.py`, with narrow functions:

- `initial_state() -> dict`
- `do_move(state, action)` — applies the model's proposed transition in a simulated state
- `render(state)` — predicts the board, allowing an explicit unknown-cell value
- optional `distance_to_win(state)` — model-authored heuristic for prioritizing search

The contract distinguishes a **claim**, **unknown**, and **error**. Unknown action outcomes are not forced into invented predictions. Replaying observed history against the model tests what it actually predicts, rather than verifying a simulator with its own self-generated observations.

After the being explicitly requests and passes `test_world_model()`, the host can run bounded search in a separate process, report a candidate path or knowledge boundary, and leave selection/execution to the model. A model failing validation must revise or abandon its hypothesis; search does not silently declare it correct.

**Takeaway:** prediction, observation, uncertainty, and execution are distinct things. A partial simulator with explicit knowledge boundaries may be more useful than an obligatory universal representation.

### F2. Optionality is not cosmetic — forced modeling can be worse

Tufa's `seal/evidence.md` reports a 2026-09-30 sweep of mandatory, absent, and optional models. On its sweep score: mandatory **55.9**, absent **60.6**, optional **65.4**. On equally weighted official-25 games: **64.5**, **72.4**, **72.1** respectively. The optional/absent difference on official-25 was essentially zero (reported p=0.91); the optional advantage in the sweep was concentrated in harder games (+9.5 at a cut, reported p=0.016).

**Do not flatten this into “world models add N points.”** The benefit depends on evaluation mix, budget and task difficulty. Mandatory modeling's deficit is much more consistent than any universal optional-vs-none gain. The published wider ablations likewise support the value of making world modeling available rather than obligatory, with uncertainty about individual contributors and interactions.

The model must decide if modeling's up-front cost can be amortized across enough future decisions. This is a question of *metacognitive resource allocation*, not merely planner quality.

### F3. The model's laboratory has an explicit, stable experimental surface

The Seal REPL is persistent within a level; model-authored workspace files survive levels, while scene-specific `history` and the live Python namespace reset. Frame/transition history, animations, numeric grids, segmentation, and outcome metadata are accessible to model code. The model can execute `submit_action(...)` from inside a Python cell and inspect resulting real observations, making contingent closed-loop programs possible.

The **workspace's reusable code** and the **level's transient trajectory** have different lifetimes. The harness safeguards their separation and makes loss of kernel state visible, rather than silently pretending a variable survived.

The useful affordance is not just “give an agent Python.” It is model-authored instrumentation with stable typed observation/action contracts, replayable evidence, sandbox boundaries, and a useful persistence policy.

### F4. The serving substrate is part of delivered cognitive capacity

Their deployed Seal uses a pruned, ARC-targeted Qwen3.8 Flash-Next checkpoint (`joint205`), a trained speculative drafter, compressed KV/indexer caches, and specialized serving choices. `presets.py` gives a long context and deployment-specific concurrency controls; `evidence.md` documents interactions such as processor-image-cache thrash and renderer workers.

This confirms our own ARC postmortem: throughput, usable context, reasoning-history retention, and available concurrent cognition are part of what a model can *do* under a deadline, not mere plumbing. However this does **not** establish the incremental causal contribution of each serving feature to 70.24 without matched controls.

### F5. Instrument liveness and cost/benefit were measured

Tufa's ledger includes not just good outcomes but negative results: e.g. optional `plan` arguments were seldom read back; a proposed inert-move guard had too small a bound on benefit to justify building; level reflection consumed tokens and did not measurably reduce next-level token cost in a one-pass comparison. Their evidence explicitly warns that one pass is noisy and identical configurations can score differently.

The lesson is to count **present → exposed → called → used → affected decision → improved outcome → transferred**, with cost and confidence at each rung. An impressive architectural diagram is not a result.

## What we missed in SAGE — and what we had already discovered

1. **We built decision machinery where a laboratory was needed.** Our early ARC organism supplied goals, effects, and executor actions through narrow ontologies. The 2026-11-02 `dev-SAGE/ARC_HARNESS_AB_THREE_LEAPS_2026-11-02.md` audit reports 149 goal proposals that failed ontology binding and executors taking many actions without model selection. We had source-reading/code-writing capabilities and fork-based solver successes, but **not a unified scored-legal, model-owned, testable executable-model affordance**.
2. **We under-tested the *decision to model*.** Our architecture distinguished model, salience and memory, but did not sufficiently compare optional vs mandatory vs unavailable modeling, particularly as a function of uncertainty and remaining horizon.
3. **We had surprise without a sufficiently specific prediction-error object.** SNARC can notice novelty/conflict; a reproducible record of `hypothesis -> predicted transition -> observed transition -> discrepancy -> revision` gives the being a direct falsifier, with explicit unknowns and provenance.
4. **We conflated local research validity and scored runtime validity.** Fork-based replays are useful scientific tools but not inherently permitted during scored ARC-3 play. The online model must predict internally; no illicit environment forks or hidden engine inspection.
5. **We underestimated useful cognition per second, and local proxy bias.** The three-leaps audit records a 0.08→1.17→2.18→24.82 progression under many simultaneous changes, and a local proxy that rewarded seen-game executors. Model, serving, context, authority and measurement must be factored in controlled tests.
6. **We did not make inexpensive architectural falsifiers routine enough.** Run a minimal-model-led control early, and compare a large “organ” against the same model's direct-code loop at matched resources before refining its ontology.

These are **implementation and experimental-design gaps**, not proof that SNARC, membot, IRP, consciousness loops or Hestia should be removed.

## Relationship to existing SAGE work (do not duplicate)

- [Counterfactual world-model branching PRD](../../sage/docs/PRD_COUNTERFACTUAL_WORLD_MODEL.md): establishes **one canonical history, many imagined branches, one governed commit**. This exploration supplies the *model-authored predictor + online falsification* mechanism; the PRD governs branch semantics.
- [Code as world model and prime effector](../../research-notes/CODE_AS_WORLD_MODEL_AND_PRIME_EFFECTOR_2026-11-01.md): states code as model, instrument, and effector, with provenance. This exploration asks when the being should choose each role.
- [World models as event graphs](../../forum/insights/world-model-as-event-graph.md): preserves events/provenance and reconstructible projections; executable models are derived hypotheses, **not** replacements for the event ledger.
- [dev-SAGE three-leaps postmortem](https://github.com/dp-web4/dev-SAGE/blob/main/ARC_HARNESS_AB_THREE_LEAPS_2026-11-02.md): documents the original harness bottleneck, serving confounds and failed falsifiers.
- [dev-SAGE paged-context PRD](https://github.com/dp-web4/dev-SAGE/blob/main/sage/cognition/paged_context/PRD.md): model-chosen retrieval, bounded questions, stable context and explicit uptake measurement. An executable-model artifact should be a retrievable page/tool, not compulsory injected prose.

## Proposed interface: small, optional, and auditable

**Do not install Seal wholesale.** Trial a tiny model-owned Python workspace with three modes, preserving normal SAGE tool and gate semantics:

```python
# An illustrative capability contract, not committed API or executable implementation
wm.new(name, scope, assumptions=[])                   # creates a hypothesis artifact
wm.attach_source(name, observation_ids=[...])         # pointers to real evidence
wm.test(name, trace_ids=[...], budget=...)              # predictions vs witnessed traces
wm.simulate(name, from_state, actions, budget=...)      # purely hypothetical transitions
wm.search(name, question, limits=...)                   # candidate path or unknown boundary
wm.promote(name, evidence_ids=[...])                    # retain versioned artifact + failures
```

The model authors the transition/render/goal representation; the harness provides contracts, deterministic replay against permitted evidence, bounded execution, provenance, isolation and error reporting. It may decline to predict a component, observation or action. Claims are scoped to the observed cases and the model's assumptions; no single “accuracy” claim substitutes for tested coverage.

**Authority invariant:** model-authored simulation, search and no-op hypotheses have no external effect. Actual action calls still use Hestia and the existing effector boundaries. A hypothetical gate query is never cached authorization. A test must not obtain an ARC hidden-game state by looking behind the observer interface. Code execution itself is governed for filesystem, CPU, imports, tool calls and data scope.

**Lifetime proposal:** retain immutable observations and model source versions with content hashes/provenance; reset level/task-local runtime variables at a boundary; restore/reopen procedures only when requested, with dependencies and validation status visible. An agent's source artifact is neither lived history nor an automatic self-belief.

## Experimental program (recommended order)

### E0 — Instrument current capabilities before building anything

On two permitted toy environments and one existing SAGE being workflow, instrument:
- model decisions, tool proposals, tool outcomes, model-authored scripts;
- actual use of current SNARC/membot/IRP/context aids, not mere exposure;
- prediction statements with evidence references and later corrections;
- active tokens, wall time, calls, tool-runtime, cache/context truncation;
- governed real actions vs simulated proposals.

**Exit:** one replayable run for each case, and an uptake ladder with unobserved fields explicitly marked unknown. This anchors the baseline, including if the being already constructs an equivalent tool spontaneously.

### E1 — Optionality A/B/C/D: the primary falsifier

Hold *model, prompts except surface description, observation access, game set, tool authority, temperature/seed policy, wallclock, tokens, context budget and serving stack* as constant as practical. Randomize paired tasks/seeds:

- **A:** direct-code observe/act baseline; no executable-model API.
- **B:** executable-model API *available and optional*, without nudging it every turn.
- **C:** same interface but a prompt **requires** writing/testing a model before consequential play; disclose the extra prompting confound.
- **D:** offer model-authored prediction/validation only, **without search** (isolates planning from falsification).

Use at least two distributions: (i) short-horizon low-uncertainty tasks, (ii) multi-step environments with hidden mechanics or costly failed acts. Keep held-out variants unseen by the authoring agent. Compare **task success, real-action cost, calibrated prediction accuracy/coverage, time-to-first-useful-action, tokens per success, recovery after falsification, and transfer to changed variants**. Record whether/how often the model chooses B and when.

**Predeclared decision:** advance B only if it improves paired task completion or resource-normalized success on the harder distribution without a material regression on the easy distribution. If B is never used, first diagnose discoverability/appropriateness; do not report an unused affordance as a negative test of world modeling. If C wins, verify whether forced extra deliberation, not world-model validity, caused it.

### E2 — Explicit unknowns and online falsification

Compare a binary predictor (must output a state), a predictor allowed to abstain (`Unknown(reason)`), and an abstaining predictor that gets targeted counterexample reports. Measure:
- claim coverage vs error (risk/coverage curve);
- false-confidence rate on unobserved action classes;
- time from contradictory observation to model revision;
- whether revisions improve predictions on later actions;
- cost of unnecessary abstention.

Avoid rewards that encourage always answering “unknown.” A useful model must make enough correct claims to support real decisions.

### E3 — Model-authored planning under a real budget

Only after E1/E2 establish uptake. Add bounded BFS/best-first over the model's own transitions. Search must stop at unknown/error boundaries, expose the tested model hash and evidence lineage, and return a *suggestion*, not an action. Compare without search at matched token and wall budgets; count simulated expansion cost separately from real actions. Test whether the model chooses to probe an unknown boundary versus optimizing a known path.

### E4 — Persistence and transfer

Provide the same being a changed environment variant. Compare:
- no carry;
- model-authored prose summary;
- model-authored versioned executable procedure with provenance;
- executable procedure plus targeted, model-requested context retrieval.

Separate **mechanic transfer** from replaying known answers. Reset stale scene-specific state, preserve source history, require revalidation on changed inputs, and keep model source different from a witnessed outcome.

### E5 — Cost-aware metacognitive choice

Offer an inspectable budget (`tokens, wall, real actions, stakes`) and allow the being to decide between direct play, cheap probe, model construction, model repair, or model-based search. Do **not** use a harness menu that selects the option on the being's behalf. Analyze decisions by remaining horizon, observed uncertainty, error consequence, and available compute; do they approximate a rational tradeoff between **expected avoided cost** and **cost of understanding**?

A useful outcome here may be **selective refusal to model**, not higher model invocation frequency.

## Operational metrics and safety gates

Track per episode: task/variant/seed/model+checkpoint/serving fingerprints; inference tokens (prefill and generation separately where possible); wall time; context occupancy and evictions; tool usage; model artifact digests and changes; evidence coverage; prediction error; abstentions; searched hypothetical nodes; live actions; governance verdicts; achieved predicates; and failures.

Maintain a **prediction ledger** with distinct `predicted`, `unknown`, `contradicted`, `observed`, `hypothetical-gate`, `committed` event types. Only witnessed observations can ground the actual-outcome field. Retain failed models and counterexamples with versions; never overwrite their history to make a prediction retrospectively right.

No irreversible physical actions in the pilot. Prefer toy simulators and permitted local tools; sandbox resource limits, content access and network/effector mediation before live integration. Training and evaluation datasets must not share game-specific answer traces. Claims of ARC3 scored legality require direct review against competition rules rather than an inference from local success.

## Concrete first implementation slice

1. Pick one already-running SAGE being and one safe simulated task; do not add a separate “world-model organ” or force the being's goal.
2. Expose a governed, disposable Python workspace with an optional, documented `predict(state, action)` / `observe()` capability. Let the being define its own internal state schema.
3. Store immutable `(source state, proposed action, prediction, resulting observation, discrepancy)` records. Mark unknown predictions distinctly.
4. Add a replay test that checks a model against **recorded observations** (not simulated “ground truth” from the same model); show coverage and counterexamples.
5. Only after observing genuine uptake, add versioned files and bounded simulation/search, and then compare the E1 arms.
6. Document results and failures in SAGE and share transferable ARC-specific methodology in dev-SAGE without copying private game traces to public SAGE.

**Success is not that we shipped a new feature.** Success is showing that a being discovered when this instrument was useful, used it to test an independently checkable claim, updated its own model when contradicted, and transferred something valid to a changed situation with measurable benefit.

## Open questions

- What experimental signal causes a being to choose model-building voluntarily?
- What constitutes sufficient validated coverage to trust a partial model for a *specific* plan?
- Does source-code persistence preserve practical competence better than prose or working-context continuity?
- Are model-authored search heuristics helpful when transition models are still unreliable?
- How should SNARC mark a prediction discrepancy without treating it as a harness-provided answer?
- Can a resident 4B being make useful local partial models, even if a stronger visitor is needed for some tasks?
- How does governance-as-feedback change the expected value of an experiment without letting hypothetical queries become authorization?
- Which gains come from model autonomy, representation, memory, or inference economics when the controls are actually held fixed?

## Research posture

Tufa's final result is evidence that optional executable models can be made practical in a strong agent loop, **not** proof that SAGE should adopt their architecture wholesale. Their ablations show nonuniform benefit; our old ARC baselines have serious confounds. The shortest path to knowledge is a small optional affordance, a strong direct-code control, observed uptake, and real falsification.

> **Harness as laboratory, not surrogate thinker.** Make the world observable, prediction falsifiable, alternatives reachable, and real consequences governed. Let the being decide whether understanding is worth its cost.
