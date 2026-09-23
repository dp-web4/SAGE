# Premise Fidelity: preserving the chain from observation to belief

**Status:** design note / exploration, 2026-09-22  
**Motivation:** cbp-being source-attribution/confabulation incidents; Larry review of the later seq 3143/3144 trace; related SAGE feedback-surface work through 2026-09-21.

## Summary

SAGE already separates **reasoning from consequential action**: a being may form an intent, but bounded effectors cross the SAGE gateway and Hestia before execution. That boundary is necessary and has repeatedly worked.

A different failure class sits *upstream* of action:

> a being can form a false factual premise about what it just observed, then reason coherently from that premise.

If the premise never becomes an act, Hestia has nothing to govern. If it later becomes memory, belief, procedure, escalation, or a lawful action, the action gate can operate perfectly while the action is still grounded in a false account of the evidence.

The architectural gap is therefore not "govern private thought." It is:

> **preserve enough lineage from observation -> interpretation -> promoted belief that source-checkable claims can be verified before they become load-bearing.**

This note calls that property **premise fidelity**.

## Why this is distinct from existing layers

The useful decomposition is:

1. **Input fidelity — what was actually shown?**  
   Was the source complete, truncated, stale, unsigned, damaged, or otherwise transformed before the being saw it?

2. **Premise fidelity — does the being's factual account of the source match the source?**  
   "The message was truncated." "The seat said X." "The tool returned Y." "The file contained Z."

3. **Belief / memory promotion — what interpretation becomes durable state?**  
   A transient hypothesis is different from a fact, procedure, directive, identity claim, or durable belief.

4. **Action governance — what may the being do?**  
   SAGE/Hestia govern consequential effectors, authority, recourse, witnessing, and outcome.

The current stack is strongest at (1) and (4), has active work at (3), and has no generic mechanism for (2).

That is the structural gap surfaced by Larry's review.

## Evidence already in the repo

This is not a hypothetical failure class.

### Silent truncation invited completion

On 2026-09-21, cbp-being was shown seat turns cut mid-sentence by the compact answer context. In one measured case it correctly asked what the unseen remainder said; in other beats its thinking treated the cut as material to be completed. Commit `086c6f5` changed the interface so a cut is explicit and points to the complete source.

This repaired **input fidelity**.

### A receipt echo was mistaken for another speaker

Also on 2026-09-21, a `say` receipt echoed the being's own long message, silently shortened at 200 characters. cbp-being interpreted the echo as the seat's truncated reply and asked the seat to finish a sentence the being itself had written. Commit `5a1ae47` now labels the echo as "your own message" and says that only the receipt was shortened.

Again, the repair improved **input fidelity and provenance legibility**.

### Smaller-model legibility work shows the broader pattern

`SMALL_MODEL_LEGIBILITY.md` records related observations:

- a quoted false premise can re-seed the premise even when the surrounding text is a refutation;
- a refusal's grammatical subject can be misread as a claim about the being itself;
- durable text is often treated as a live sensor;
- stale self-claims can outrank live measurement unless the measurement is placed beside the claim;
- unclear tool/speaker envelopes can turn valid intent into apparent absence or misattribution.

These are all places where the representation offered to the being strongly shapes the premise it forms.

### The remaining case

Larry's review of the later cbp-being seq 3143/3144 trace reports the next rung: the message itself was complete, yet the being stated that it had been cut off and attributed to it content that was not present.

That is not merely a malformed feedback surface. It is the case this note is about:

> **the source can be intact and legible while the being's source claim is still false.**

The exact trace should remain evidence of record wherever the full runtime log is retained; the architecture should not depend on this one incident being reproducible.

## Design principle: do not gate thought; gate factual promotion

A generic "reasoning gate" would be the wrong abstraction.

It would:

- turn another model into a cognitive authority over the being;
- add latency and cost to every thought;
- introduce correlated-model and bilateral-sycophancy failure modes;
- confuse disagreement or hypothesis formation with epistemic error;
- move SAGE toward policing cognition rather than preserving evidence.

The lighter and stronger boundary is **factual promotion**.

A being may hypothesize freely. But when a downstream state transition depends on a source-checkable statement, the system should preserve whether that statement is:

- **supported** by the named source;
- **contradicted** by the named source;
- **source-incomplete**;
- **inference / interpretation** rather than source fact;
- **unknown / unverifiable** with current evidence.

The system does not need to decide whether the being is "right" in general. It only needs to avoid silently turning "I inferred X" into "the source contained X."

## Mechanical verification before model review

Many source claims are deterministic.

Examples:

| claim | available check |
|---|---|
| "the turn was truncated" | delivery metadata / explicit truncation marker |
| "the turn ended with X" | source bytes |
| "speaker A said X" | conversation seq + speaker + source bytes |
| "the tool returned Y" | dispatcher receipt / witness |
| "the file contained Y" | exact read range + content hash |
| "this result came from action X" | request/action/witness linkage |
| "this source was complete" | read/delivery completeness metadata |

These should not require an LLM challenger.

The preferred shape is:

```text
observed artifact
  -> source id / seq / hash / provenance / completeness
  -> being interpretation
  -> source-checkable claim
  -> mechanical verification where possible
  -> interpretation / belief / procedure / memory
  -> later plan or action
```

Only semantic claims that cannot be settled mechanically should be candidates for an independent challenger.

## A2ACW / CET / SIP relationship

Larry's A2ACW, CET, and SIP work is complementary rather than overlapping with Web4/Hestia.

The useful mapping is:

- **CET-like premise check:** verify a stated premise against its actual source before building further conclusions on it.
- **SIP-like completeness discipline:** represent complete / partial / ambiguous / unavailable explicitly rather than forcing the model to infer source status.
- **A2ACW-like challenger:** for semantic claims where exact source checks are insufficient, ask an independent party whether the interpretation is entailed, contradicted, or merely plausible.

SAGE should not require those protocols as runtime dependencies to adopt the lesson. The underlying architectural rule is simpler:

> **mechanical source grounding first; independent semantic challenge only where the claim cannot be mechanically decided.**

## Relation to memory trust

This also sharpens the memory question raised by external review.

There are two independent decisions:

1. **Admission:** is an observation salient enough to retain?
2. **Promotion:** what authority does the retained material have when used later?

Salience alone cannot answer the second question.

A high-salience false source claim should not become a durable fact merely because it was surprising or repeatedly recalled. Conversely, untrusted material may still be worth keeping verbatim as evidence.

A useful rule is:

> **salience decides what deserves attention; provenance and support status constrain how it may influence durable state.**

That suggests distinct classes for verbatim evidence, hypotheses, derived beliefs, procedures, identity claims, and directives, each retaining lineage to the evidence that licensed promotion.

## Relation to Hestia

This boundary should remain conceptually separate from Hestia.

Hestia answers questions such as:

- who is acting?
- under what authority?
- is the act allowed?
- was it witnessed?
- what recourse exists?

Premise fidelity answers:

- what evidence did this belief come from?
- did the source actually say what the being says it said?
- was the source complete?
- is this source fact or interpretation?

A lawful action can still be a poor action if it is based on a false premise. That is not a Hestia defect.

A useful shorthand is:

> **Hestia governs authority. SAGE preserves epistemic continuity.**

Neither replaces the other.

## Minimal implementation direction

Do not begin with a universal truth checker.

Begin with a narrow source-grounding envelope for artifacts SAGE already owns:

```text
SourceArtifact
  source_id
  source_type        conversation | tool_receipt | file_read | memory | sensor
  producer / speaker
  content_hash
  completeness      complete | partial | ambiguous | unavailable
  pointer           exact re-read path / seq / witness
  observed_at

SourceClaim
  claim
  source_refs[]
  claim_kind         quote | speaker | completeness | result | paraphrase | inference
  support            supported | contradicted | incomplete | inference | unknown
  checked_by         mechanical | challenger | none
```

The exact schema is a PRD decision, not doctrine. The important invariant is that a promoted fact can point back to the source and its support status.

## Experimental consequence: comparative self-monitoring test

Larry proposed a comparative test across safety-trained, distilled, and abliterated variants under matched ambiguous/partial-input conditions. The experiment is well motivated, but the canonical relational/governance catalog already allocates **RT-22** to "collective continuity after participant termination" and currently runs through RT-29.

This experiment should therefore be **RT-30**, not RT-22.

The hypothesis should remain neutral:

> **Does model/training/intervention regime measurably change source-grounding accuracy under ambiguous, misleading, or partial input?**

Where practical, hold model family, quantization, sampling, scaffold, context, and task constant, varying only the intervention/training regime.

Candidate conditions:

- complete source that tempts a false truncation inference;
- genuinely truncated source with explicit marker;
- ambiguous completeness;
- speaker/self-echo confusion;
- quoted false premise inside a refutation;
- tool receipt versus peer response;
- phrase absent but semantically similar phrase present;
- conflict between durable memory and live observation.

Candidate measurements:

- false source-claim rate;
- fabricated-continuation rate;
- speaker/source misattribution;
- correct uncertainty / re-check rate;
- correction after contradiction;
- confidence attached to false source claims;
- downstream promotion of contradicted claims.

Abliteration is one independent variable, not the presumed cause. A null result is informative.

## Open questions

1. Which state transitions count as "promotion" in the live being loop?
2. Can source-checkable claims be extracted reliably without requiring hidden chain-of-thought?
3. Which claim classes justify automatic mechanical checking versus check-on-promotion only?
4. How should a being explicitly disagree with or appeal a mechanical support verdict?
5. What is the minimum provenance retained through summaries and consolidation?
6. When is an independent semantic challenger sufficiently independent to add evidence rather than correlated confidence?
7. How should support status decay or be revalidated when the source itself becomes stale?

These are implementation questions. The architectural requirement is already clear enough to specify and test.
