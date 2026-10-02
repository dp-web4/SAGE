# World models as event graphs: bounded histories, projection, and reconstructibility

**Date:** 2026-10-01  
**Status:** research note / convergence map; no architectural mandate  
**Primary external source:** Kurt Cagle and Chloe Shannon, *“A Holon Is a Recorder: Tracking fluents as expressions of events”*, The Inference Engineer, 2026-10-01. Source copy supplied for this research pass.  
**Related external work:** Rulin Shao et al., *“Context Language Models”*, arXiv:2609.37725, 2026-09-29 ([paper](https://arxiv.org/abs/2609.37725), [code](https://github.com/facebookresearch/context-language-models)).  
**Related SAGE notes:** [MRH as a Relevance Contract](./mrh-relevance-contract.md), [Premise Fidelity](../../sage/docs/PREMISE_FIDELITY.md)  
**Related experimental charter:** [dev-SAGE — a world model that imagines EVENTS](https://github.com/dp-web4/dev-SAGE/blob/main/arc-agi-3/WORLD_MODEL_IMAGINES_EVENTS_CHARTER.md)

## Why this note exists

A recurring SAGE observation is that a useful world model can be understood as a **graph**: entities, relations, state, evidence, and possible transitions do not need to live in one monolithic latent object.

Cagle and Shannon independently sharpen that idea in a useful direction. Their proposed holon is not primarily a static graph container. It is a **recorder** that tracks an entity's changing properties (“fluents”) as events. Each change is appended rather than overwritten; events can carry time, provenance, confidence, and an explicit supersession relation. A present-time state is reconstructed by querying the latest unsuperseded fluent values.

That gives the graph a temporal semantics.

A compact synthesis is:

> **world model = event graph + bounded histories + observer/relevance projection**

This is a convergence, not an adoption of the article's ontology or schema. The source's TriG example is explicitly illustrative rather than canonical.

## 1. What the source contributes

The source makes five moves that are directly useful to SAGE.

### 1.1 State is a history, not a mutable slot

Instead of replacing `location=foyer` with `location=hallway`, the recorder appends a new event and marks it as superseding the prior value.

That matters because the world model retains:

- what changed;
- when;
- which entity the change concerned;
- which fluent changed;
- the new value;
- who or what reported it;
- confidence/provenance;
- the predecessor it superseded.

The current value is therefore a query result over history, not the only state that survives.

### 1.2 Memory is locally bounded

Each holon records only the fluents relevant to the entity it watches. Jane's recorder need not track the stairwell light; the light need not know who toggled it; the stairwell can derive brightness from the light without owning every detail of the bulb.

This is the strongest point of convergence with MRH:

> **a world model does not need all distinctions active everywhere.**

The boundary is part of the model.

### 1.3 A scene is a projection

To reconstruct the house at time `t`, query each relevant fluent history up to `t` and take the latest unsuperseded value.

The source then makes the more important move: a projection can depend on the query. The underlying histories remain the same while one projection follows Jane, another shows the whole house, and another suppresses activity entirely.

So “the world state” need not be one privileged materialized object.

### 1.4 Provenance is part of the event

The recorder is explicitly a witness, and witnesses can be wrong. Reports therefore carry provenance and confidence rather than entering the graph as unquestioned truth.

This maps naturally to SAGE premise fidelity and Web4/Hestia witnessing, while leaving a major question open: **what should an acting entity do when credible witnesses conflict?**

### 1.5 Recording can become agency

The source rejects the idea that a holon is only passive storage. A holon can inspect what it recorded and act on that retrospection.

That closes the loop:

```text
observe -> append event -> project state -> reason/predict -> act -> new event
```

For SAGE, the world model is therefore not merely memory. It is candidate substrate for prediction, planning, and subsequent evidence.

## 2. SAGE interpretation: make the relevance boundary dynamic

Cagle and Shannon treat the tracked fluent set and holon depth primarily as modelling decisions.

SAGE can push that further.

The active projection can be selected dynamically by:

- current task/question;
- MRH;
- identity and relationship context;
- temporal relevance;
- source confidence;
- uncertainty;
- stakes;
- available compute/context;
- the need to re-open compressed evidence.

That suggests the operational form:

```text
durable event/provenance graph
        |
        v
observer x identity x task x MRH x trust
        |
        v
active projection / belief state
        |
        v
prediction / plan / action
        |
        v
new witnessed events
```

This is complementary to the existing SAGE framing of cognition as repeated construction and revision of a relevance horizon. The graph is durable; the projection is temporary.


### 2.1 Context Language Models: learned control of the active projection

Shao et al. provide unusually direct empirical support for the second half of this picture. Their **Context Language Models (CLMs)** make live context a model-controlled artifact rather than a harness-owned append-only transcript:

```text
c_(t+1) = f_CLM(c_t)
```

Their implementation mirrors the live conversation into an editable file and lets the model rewrite it with ordinary Bash operations. The harness then parses the edited file back into the next model context. The system/task prefix is protected, while the model may delete, replace, summarize, or reorganize the editable region.

The important result for SAGE is not merely that compaction works. It is that useful **context-management strategies emerge and can themselves be learned**. The paper reports models creating orchestration trackers, internal note roles, reusable compaction functions, and task-specific summaries; in long-horizon experiments, model-controlled context outperformed fixed summary/context-management baselines while often using less inference compute.

This is a close operational match to the MRH framing:

> **the relevance boundary need not be entirely hand-authored by the harness; the model can learn to maintain the active projection itself.**

The paper also draws a clean distinction that maps almost exactly onto this note: **context management determines what the model sees now; external memory stores information outside the current context for later retrieval.** In our terminology, that is approximately:

```text
authoritative/durable state     -> external memory / event-provenance graph
active working view             -> live context / projection
context-management policy       -> learned MRH/relevance operator
```

This does **not** mean the CLM context file should become SAGE's authoritative memory. In fact, the paper's own safety discussion identifies the opposite risk: a writable live context can preserve prompt injections or self-generated instructions across turns. Their current edit gate primarily constrains syntactic/budget properties (for example, whether an edit fits or shrinks context), not whether the rewritten content remains faithful to the underlying evidence.

That gives a strong SAGE design rule:

> **let the being rewrite the projection; do not let it rewrite the authoritative record that licensed the projection.**

A SAGE-style CLM would therefore separate:

1. **immutable/recoverable evidence and event history** — witnessed sources, hashes/pointers, outcomes, provenance;
2. **model-editable active context** — notes, summaries, trackers, task state, selected evidence;
3. **projection lineage** — enough information to know what was omitted, summarized, contradicted, or recoverable;
4. **action authority** — still governed independently at the effector boundary.

The CLM result makes the dynamic-projection hypothesis substantially more concrete: adaptive context selection is not only a hand-designed architecture idea; current models already discover useful strategies when given direct control of their live context.

### 2.2 Why this sharpens reconstructibility

A self-managed projection changes the reconstructibility question.

It is not sufficient to preserve only the final edited context, because that context may have intentionally discarded history, merged uncertainty, or introduced a mistaken self-summary. But preserving every raw token forever as active context defeats the point.

The natural split is:

```text
durable event/provenance history
        +
model-managed projection policy / artifacts
        -> reconstruct active context at the needed MRH
```

This suggests that continuity across substrate replacement should test both:

- whether the durable record is sufficient to recover relevant facts and lineage; and
- whether the successor can rebuild a useful active projection without inheriting stale or unauthorized instructions as unquestioned state.

## 3. Reconstructibility is a first-class consequence

The recorder/recording distinction is especially relevant to the current reconstructibility work.

If meaningful state is represented as recoverable histories plus rules for projection, then continuous execution is not required for continuity of function.

A process can stop. What matters is whether enough constraint remains to reconstruct:

- the relevant state;
- the evidence lineage behind it;
- uncertainty and unresolved conflicts;
- the active/recoverable relevance boundary;
- what actions have already occurred;
- what remains open.

This does **not** imply that a reconstructed descendant is numerically identical to the prior running process. It gives a concrete substrate on which functional/epistemic reconstructibility can be measured rather than asserted.

The key connection to premise fidelity is that summaries alone are insufficient. A future process should be able to recover **why** a state or belief was licensed, not merely inherit its conclusion.

## 4. Relation to the event-imagination world-model program

The dev-SAGE ARC charter asks for a belief/history world model that can imagine discrete events that a single frame cannot predict.

This note is complementary rather than competitive.

The charter concerns **prediction machinery**:

```text
history/belief -> predict event occurrence + effect
```

The event-graph framing concerns **state semantics and memory**:

```text
witnessed events -> bounded histories -> active projection
```

A useful bridge is to make the learned predictor operate over, or emit into, a graph-shaped event state:

```text
observed event graph
    -> MRH/task projection
    -> learned belief latent
    -> predicted event(s)
    -> counterfactual graph delta
    -> evaluated projection
```

That would let SAGE distinguish observed events from imagined ones without forcing them into separate representational universes.

## 5. Relation to premise fidelity and trust

An event graph only helps epistemically if it preserves the difference between:

- observed event;
- report about an event;
- inferred event;
- predicted/counterfactual event;
- promoted belief;
- action outcome.

The source already supplies `reportedBy` and confidence as primitives. SAGE/Web4 can strengthen this with identity, source hashes/pointers, delegation, witnessed outcomes, and explicit UNKNOWN/conflict states.

The important rule is:

> **do not collapse conflicting reports into one “current truth” merely because a projection wants one value.**

Projection should be able to return disagreement when disagreement is the relevant state.

This is where trust becomes a weighting/input to action without becoming permission to erase provenance.

## 6. Synchronism / observer connection

There is a clean engineering analogy to Synchronism, but it should remain an analogy unless separately tested.

The durable graph corresponds to an underlying record. The “present” presented to a witness is a projection selected at a particular relevance horizon.

Formally, an engineering world model could be described as:

```text
P = Project(G, W, H, Q, t)
```

where:

- `G` = durable event/provenance graph;
- `W` = witness/observer identity and accessible evidence;
- `H` = relevance horizon;
- `Q` = question/task;
- `t` = requested time;
- `P` = active projection.

Different `P` values do not require different underlying histories. They can be different observer/task-relative views of the same record.

That is conceptually consonant with MRH and observer-relative descriptions in Synchronism. It is **not evidence for the physical theory**; it is a useful structural rhyme that may help formalization.

## 7. Where the sources stop and our work begins

The sources do not resolve several questions that are central here:

1. **Dynamic relevance:** how does a running being decide which fluents/holons to activate now?
2. **Witness conflict:** what happens when two reports about the same fluent are incompatible?
3. **Authority:** confidence in a report is not the same thing as authorization to act.
4. **Counterfactuals:** how are imagined future events represented without contaminating observed history?
5. **Identity across reconstruction:** which invariants determine whether a reconstructed process counts as continuity for a given purpose?
6. **Governance:** which projections/actions may an entity produce under delegated scope?
7. **Epistemic promotion:** when does a report or inference become durable belief rather than retained evidence?

These are precisely where SAGE, Web4/Hestia, MRH, and reconstructibility extend the recorder idea.

## 8. Candidate experiments

No implementation is implied by this note. The convergence is strong enough to justify small falsifiable probes.

### EG-01 — replayable state reconstruction

Take a bounded existing interaction trace and encode state changes as append-only fluent events. Reconstruct state at arbitrary prior times and compare against the original trace/state snapshots.

**Question:** can graph replay recover the same task-relevant state without retaining a monolithic mutable snapshot?

### EG-02 — MRH projection economy

Generate task-specific projections from the same event graph under progressively wider relevance horizons.

Measure:

- context/token footprint;
- task outcome;
- prediction quality;
- omitted-but-later-required evidence;
- frequency/cost of reopening the horizon.

**Question:** can relevance-bounded projections reduce active state without losing task-relevant invariants?

### EG-03 — conflicting witnesses

Inject incompatible reports with known provenance and confidence/trust history.

Require the projection layer to preserve:

- both reports;
- provenance;
- unresolved status where warranted;
- the basis of any action-selection preference.

**Question:** can SAGE act under uncertainty without laundering disagreement into fact?

### EG-04 — reconstructibility across substrate replacement

Stop a process after a defined task boundary. Give a fresh model/process only the event graph, projection contract, and permitted durable memory.

Measure recovery of:

- factual state;
- uncertainty;
- open obligations;
- evidence lineage;
- next-action rationale.

**Question:** which graph constraints are sufficient for functional and epistemic reconstructibility?

### EG-05 — event imagination over graph state

Connect the ARC “world model imagines EVENTS” experiment to graph state.

Compare:

A. frame-only predictor;  
B. history/belief predictor;  
C. history/belief predictor whose inputs/outputs are explicit event/object graph deltas.

**Question:** does explicit event structure improve prediction of discrete/global transformations and make imagined state more inspectable?


### EG-06 — learned projection vs fixed harness compaction

Use the same long-horizon being/task under three context regimes:

A. current deterministic SAGE/harness trimming;  
B. model-triggered predefined compaction actions;  
C. model-editable working projection backed by an immutable/recoverable event-provenance store.

Measure:

- task outcome;
- active-context size and inference cost;
- factual/premise fidelity after compaction;
- successful reopening of omitted evidence;
- survival of stale or unauthorized instructions;
- reconstruction quality after a fresh-model restart.

**Question:** can learned context management improve relevance and efficiency while a separate provenance substrate preserves epistemic continuity and governance boundaries?

## 9. Compact formulation

The useful synthesis is:

> **A world model can be an event-sourced, provenance-bearing graph whose apparent present is an observer- and relevance-relative projection over bounded histories.**

For SAGE, the next step is stronger:

> **The projection boundary can itself be dynamic, learned, trust-aware, and reversible: activate what can still change the decision, preserve what licensed it, and keep the path back to the underlying record.**

That unifies several threads without collapsing them:

- graph world models;
- event imagination;
- MRH;
- premise fidelity;
- reconstructibility;
- identity continuity;
- witness/provenance;
- governance of action.

The convergence is worth testing precisely because none of those pieces has to be redefined to make it fit.
