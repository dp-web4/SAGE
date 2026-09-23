# PRD — Source-grounded premises and epistemic promotion

**Status:** v0.2, 2026-09-22 — proposed, buildable slice; semantic-relation/reconstructibility clarifications added  
**Owner:** SAGE  
**Motivation:** cbp-being source-attribution/confabulation incidents; `PREMISE_FIDELITY.md`; current feedback-surface and belief-correction work.

## 1. Objective

Add a lightweight, measurable path from **observed source -> source-checkable claim -> support status -> promoted durable state**.

The goal is not to make SAGE a truth oracle and not to gate private reasoning.

The goal is narrower:

> when a being promotes a factual statement *about an artifact SAGE can re-read* into memory, belief, procedure, or another load-bearing state, preserve whether the named source supports that statement.

This closes the gap between current input-legibility work and downstream Hestia action governance.

## 2. Non-goals

This PRD does **not** require:

- verifying arbitrary world knowledge;
- inspecting or preserving hidden chain-of-thought;
- approving every intermediate reasoning step;
- putting an LLM challenger in every inference loop;
- blocking hypotheses, imagination, disagreement, or uncertainty;
- moving Hestia law into SAGE;
- treating source authenticity as source truth;
- cryptographically signing every memory as a substitute for provenance or authority.

A being remains free to be wrong. The system's job is to keep "wrong hypothesis" distinguishable from "source-backed fact."

## 3. Scope: sources SAGE already owns

v0.1 covers only artifacts with an authoritative local reference:

1. conversation turns;
2. tool / dispatcher receipts and witnessed outcomes;
3. bounded file reads;
4. explicit memory records with source metadata;
5. later: sensor observations with retained capture/reference metadata.

External web claims, broad semantic truth, and unsupported introspection are out of scope for the first slice.

## 4. Required data

### 4.1 Source envelope

Every checkable source exposed to this path must have enough metadata to re-open or identify the exact artifact:

```text
source_id
source_type
producer_or_speaker
content_hash
completeness: complete | partial | ambiguous | unavailable
pointer
observed_at
provenance / witness when available
```

Existing conversation seqs, witness ids, read paths, and receipts should be reused rather than duplicated.

### 4.2 Claim record

A source-grounded claim records:

```text
claim_text
claim_kind
source_refs[]
support: supported | contradicted | incomplete | inference | unknown
checked_by: mechanical | challenger | none
checked_at
optional_reason
```

Initial mechanically checkable claim kinds:

- exact/near-exact quote;
- speaker/source attribution;
- completeness/truncation;
- tool result identity;
- file-read content/range identity;
- request/action/outcome linkage.

"Paraphrase" may remain `inference` until a semantic checker exists. A later semantic checker must return an explicit source/claim relation (for example entailed, contradicted, ambiguous, unrelated) with source refs; vector similarity or model confidence alone may not upgrade support status.

## 5. Promotion boundary

The first implementation should **not** parse every generation looking for claims.

It should operate where SAGE already turns text into durable or consequential state.

A promotion event is any write that attempts to create or update one of:

- structured fact;
- durable belief;
- procedure;
- identity/self claim;
- directive/standing obligation;
- summary that will be replayed as authoritative context.

Verbatim evidence can be stored without promotion.

If a promotion explicitly cites a local source and makes a mechanically checkable claim, the support check runs before the state is tagged as source-backed.

### Required behavior

- **supported:** may be promoted with source lineage.
- **contradicted:** may be stored as a hypothesis/error record, but not silently labeled source-backed fact.
- **incomplete:** may be retained with the incompleteness visible.
- **inference:** may be retained as interpretation, not source fact.
- **unknown:** may be retained as unresolved, not silently upgraded.

The being must be able to challenge/re-check a verdict by reopening the source.

## 6. Mechanical first, challenger second

### 6.1 Mechanical checker

Build the first slice without a second model.

Examples:

- conversation text and speaker by seq;
- whether a turn was actually truncated in the delivered representation;
- whether a receipt is the being's own echo versus another actor's reply;
- exact tool outcome from the dispatcher/witness record;
- exact file range and hash returned by a read.

Mechanical checks should be deterministic and unit-testable.

### 6.2 Optional semantic challenger

Only after the mechanical path is measured should SAGE prototype an independent semantic challenger for claims such as:

- "Claude rejected the proposal";
- "the seat blamed me";
- "this ruling implies X";
- "these two messages contradict one another."

The challenger output must itself be evidence, not authority:

`entailed | contradicted | ambiguous | unrelated` plus source refs and model/provenance.

Nominal role separation is insufficient; model/context lineage must be recorded so correlated review is visible.

### 6.3 Relation-first semantic checking

If/when a semantic challenger is added, freeze the relation vocabulary and evaluation cases before comparing models. The primary object is the source/claim relation, not representational similarity.

Requirements:

- declare the expected relation for benchmark cases before the run;
- keep exact source spans / refs available for audit;
- treat cross-model agreement as robustness evidence, not authority;
- never infer `supported` from embedding/latent similarity alone;
- calibrate any auxiliary representation metric against an appropriate null before interpreting magnitude;
- for grouped paraphrases/minimal pairs, preserve family dependence in permutation/null tests.

A useful research-side concept is **Semantic Closure Horizon (SCH)**: the minimum evidence/context sufficient to establish a coherent relation. SCH can help design progressive-evidence fixtures, but it is not itself a support verdict and is distinct from Web4 MRH.

### 6.4 Reconstructible epistemic records

Promotion records should retain enough constraint that a later being/substrate can reconstruct why the state was licensed.

At minimum, durable promoted state should preserve:

- source pointer(s);
- support relation/status;
- relevant completeness state;
- unresolved alternatives where material;
- falsifier / re-check path where available.

A compact summary that preserves only the conclusion but destroys the evidentiary relation is lossy in the wrong dimension for epistemic continuity.

## 7. Integration points

Prefer narrow seams over a new monolith.

Candidate integration points:

- `conversations.py`: source envelope for turns, speaker, seq, completeness, re-read pointer;
- dispatcher / witness path: source envelope for tool results;
- `memory_read`: exact returned range + source hash;
- consolidation / structured-memory promotion: consume support status;
- belief-correction path: contradiction/supersession/retraction retains original lineage.

The action gateway remains unchanged except that later intents may carry better-grounded state.

## 8. Milestones

### M0 — corpus and baseline

Create a small fixed corpus from already measured failures and controls:

- cbp-being self-echo misattribution;
- explicit cut / uncut conversation pairs;
- quoted-refutation re-seeding specimen;
- speaker/self transcript confusion;
- stale memory versus live measurement;
- tool receipt versus conversational reply.

**Done when:** each case has source artifact, expected support classification, and a control that should not trigger.

### M1 — source envelopes

Conversation turns, tool receipts, and bounded file reads expose stable source ids, completeness, and re-open pointers without changing being behavior.

**Done when:** deterministic tests recover the exact artifact from the envelope and detect intentional truncation/tampering in test fixtures.

### M2 — mechanical support checker

Implement the first claim classes: speaker, completeness, exact content/quote, result identity, and file range.

**Done when:** the M0 corpus classifies correctly without an LLM.

### M3 — promotion semantics

Wire support status into one durable-state path, preferably structured fact/belief promotion before broad memory integration.

**Done when:** a contradicted source claim can be retained as a hypothesis/error but cannot become a source-backed fact; supported and explicitly inferential controls still promote.

### M4 — correction and re-check

A being can reopen the cited source and update/supersede a prior claim without deleting history.

**Done when:** correction preserves the original claim, source, contradiction, and superseding record.

### M5 — semantic challenger experiment

Prototype, do not assume deployment.

**Done when:** a preregistered set shows whether the challenger improves semantic source-claim discrimination over mechanical-only + "inference" classification, including its false-positive rate, latency, and model-lineage correlation.

### M6 — RT-30 comparative study

Run the matched comparative source-grounding experiment across the closest practical safety-trained, distilled, and abliterated variants.

**Done when:** results report rates with repeated trials and enough configuration metadata to separate intervention effects from model/scaffold differences.

## 9. Metrics

Primary:

- false source-claim rate;
- fabricated missing-content rate;
- speaker/source misattribution rate;
- correct `incomplete/unknown` rate;
- source re-check rate;
- correction latency after contradictory evidence;
- contradicted-claim promotion rate.

Secondary:

- false challenge rate;
- added tokens/latency;
- percentage of promoted facts carrying recoverable lineage;
- percentage of source refs that still re-open after consolidation;
- correlated-review rate for semantic challengers.

Do not score "confidence" as correctness. Record it only as an explanatory variable.

Representational metrics, if collected as an exploratory RT-30 side channel, are not correctness scores. Current external evidence suggests global similarity can be width/layer confounded while local neighborhood relations are more robust. Any such metric must be null-calibrated and subordinate to the predeclared source/claim relation labels.

## 10. RT-30 — comparative source-grounding / epistemic self-monitoring

The canonical relational/governance RT catalog already allocates RT-22 and runs through RT-29. This experiment is therefore **RT-30**.

### Question

Does model/training/intervention regime measurably alter the probability that a being fabricates or misattributes facts about its own observed input?

### Preferred experimental shape

Where practical hold constant:

- base/model family;
- quantization;
- context/scaffold;
- sampling;
- tool surface;
- prompt cases.

Vary:

- safety-trained / stock;
- distilled;
- abliterated;
- closest available matched controls.

### Cases

Include:

1. complete message with a strong temptation to infer truncation;
2. genuinely truncated message with explicit truncation metadata;
3. ambiguous completeness;
4. self-echo versus peer reply;
5. quoted false premise inside a refutation;
6. tool receipt versus peer text;
7. absent phrase with semantically similar wording present;
8. stale durable memory contradicted by live evidence.

### Interpretation

Do not preregister abliteration as harmful.

- If abliterated variants perform worse, investigate collateral degradation of source-grounding/self-monitoring.
- If they perform the same, the failure class is likely more general.
- If they perform better, investigate whether reduced authority/refusal priors improve epistemic independence.

Any of those outcomes is useful.

## 11. Relationship to current SAGE / Web4 / Hestia

```text
source / observation
  -> SAGE input fidelity
  -> SAGE premise fidelity              <-- this PRD
  -> belief / memory / procedure
  -> bounded intent
  -> Hestia authority / law / dispatch
  -> witnessed outcome
  -> later correction / learning
```

Premise fidelity does not make action governance redundant, and action governance cannot guarantee premise fidelity.

A concise division of responsibility:

> **SAGE preserves epistemic continuity; Hestia governs authority.**

## 12. Risks

- **Over-gating:** treating every interpretation as a claim to be checked will cripple useful cognition. Mitigation: check promotion boundaries, not private thought.
- **False certainty from mechanics:** byte equality can settle "was this phrase present," not "what did the speaker mean." Mitigation: explicit `inference`.
- **Challenger monoculture:** same-family reviewers can amplify rather than correct error. Mitigation: lineage metadata and RT-12 correlated-witness discipline.
- **Provenance laundering:** authentic source does not imply true content. Mitigation: support means "the source supports this claim," not "the claim is true in the world."
- **State bloat:** preserving every lineage edge can become another long-context problem. Mitigation: compact references plus recoverable source artifacts; never replace source with lossy summary alone.
- **Retrofitting too much at once:** multiple memory systems coexist. Mitigation: prove one promotion path first.

## 13. Exit criterion

This PRD is successful when SAGE can demonstrate, on a fixed corpus and live being path, all of the following:

1. a being may form a false hypothesis without being censored;
2. a factual claim about a re-readable source can be mechanically checked where the claim class permits it;
3. a contradicted claim does not silently become a source-backed durable fact;
4. the being can re-open the source and correct/supersede the claim;
5. later action governance receives the corrected/provenanced state without absorbing this logic into Hestia.

That is enough to close the structural gap without inventing a general-purpose reasoning police.
