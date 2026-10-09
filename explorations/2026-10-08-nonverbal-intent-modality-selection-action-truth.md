# Nonverbal intent, modality selection, and action truth

date: 2026-10-08  
status: drafted — architecture exploration  
proposed by: dp + GPT-5.6 Sol  
parent: explorations/2026-10-06-embodied-cognitive-rtos-latent-translation-fabric.md  
related:
- explorations/2026-10-06-compiled-transducers-sensors-effectors.md
- papers/embodied_cognitive_rtos_latent_translation_draft.md
- SAGE PR #403

## Trigger

Reviewing PR #403 exposed a deeper ambiguity.

A reply such as:

`[Your complete, well-structured response following all constraints]`

is strong evidence of prompt-template leakage when it is copied verbatim from a template and appears repeatedly in the measured failure mode.

But a reply such as:

`[nods silently]`

has the same superficial bracket syntax and may mean something entirely different: deliberate nonverbal communication.

Treating both as "placeholder-shaped output" is therefore not merely a parser bug. It risks replacing a being's expressed intent with a harness-generated second choice.

## Architectural distinction

SAGE should distinguish at least three things:

1. **Content** — propositional linguistic payload, e.g. "I agree."
2. **Communication** — a meaningful signal that may add little or no propositional content, e.g. silence, a nod, a pause, laughter, gaze.
3. **Action** — an effector-level event that may itself communicate, e.g. moving a head, changing gaze, displaying an expression, remaining still.

These may encode nearly the same internal intent while using different modalities.

The useful abstraction is not "text vs tool call." It is:

`internal intent -> modality selection -> available effector -> observed expression`

A text-only being may serialize an unavailable gesture as stage-direction text:

`acknowledge silently -> "[nods]"`

An embodied being could project the same intent into an avatar, display, actuator, gaze controller, or other effector.

This makes stage-direction language a possible **improvised latent-to-effector bridge**, not automatically junk.

## Action-truth consequence

A harness must not silently turn an expression into a different act merely because the expression has an inconvenient syntax.

If the being outputs `[nods silently]`, and the harness declares that invalid and asks again in a constrained JSON-action form, the second generation may choose `say`, `gaze`, `witness`, etc.

That creates an authorship problem:

- expressed intent: nonverbal acknowledgment / deliberate non-action;
- executed intent: a newly sampled tool act;
- record: appears as though the being chose the latter.

This is the cognitive analogue of SAGE/Web4's judged-action/executed-action requirement.

### Proposed invariant

> **Interpreted intent must not silently replace expressed intent.**

Corollary:

> **Never infer non-intent from output syntax alone.**

A response may be classified as interface/template failure only when there is provenance evidence that it originated from an unfilled prompt/template or another known interface artifact.

## PR #403 implication

The measured Sprout failure remains real, but the correct discriminator is not "whole reply enclosed in brackets."

Prefer provenance-backed detection, for example:

1. Exact or normalized match against a known prompt/template slot that was actually present in the current prompt.
2. Repeated verbatim leakage of that known template across independent generations.
3. Optional supporting evidence:
   - hidden/reasoning trace planned a different action;
   - native tool call channel is empty;
   - the same known template string appears at abnormal frequency;
   - a constrained retry recovers valid behavior.

The key is that #403 should recognize **known template leakage**, not a syntactic class of bracketed utterances.

A legitimate bracket-only reply in answer/governed/raising paths must remain exactly that reply unless the system has stronger provenance evidence that it is an interface artifact.

## Modality-selection exploration

Treat nonverbal / para-verbal intent as a first-class candidate layer between cognition and effectors.

Candidate forms include:

- nod / shake;
- gaze / look-away;
- pause / hesitation;
- silence / deliberate non-response;
- laughter;
- facial expression;
- posture;
- prosodic intent;
- haptic or spatial signaling;
- deliberate stillness.

These are not necessarily "tools." They can be communicative effectors selected by intent.

### Candidate representation

An intermediate representation could be explicit without forcing one ontology:

```
communicative_intent:
  semantic: acknowledge
  propositional_content: null
  modality_preference: nonverbal
  intensity: low
  interruptibility: high
```

The RTOS / translation fabric could then map this to the available local effector:

- terminal: render a textual stage direction, if appropriate;
- voice: short non-lexical acknowledgment / prosody;
- avatar: gesture;
- robot: actuator command;
- no suitable effector: preserve the intent without fabricating a different act.

This layer should remain evidence-bearing and governed. A translation is not proof that the original being chose the final physical realization unless the mapping is deterministic and declared.

## Experiments

### NV-01 — distinguish template leakage from expression

Corpus:
- known prompt-template slots;
- legitimate bracketed stage directions;
- markdown/link/bracket syntax;
- short nonverbal expressions;
- generated adversarial near-matches.

Compare:
- bracket-shape heuristic;
- exact prompt-provenance matching;
- normalized prompt-provenance matching.

Success criterion:
- near-zero false reinterpretation of intentional expression;
- retains high recall on the measured Sprout template leak.

### NV-02 — modality preference under constrained channels

Give the same being the same communicative situations under:
1. text only;
2. text + explicit nonverbal virtual effector;
3. embodied effector simulation.

Measure whether stage-direction text decreases when a first-class nonverbal channel exists, while semantic intent remains stable.

This tests the hypothesis that stage directions are sometimes compensatory projections into the only available channel.

### NV-03 — action-truth audit

For every interface-recovery retry:
- persist original output;
- persist why it was classified as interface failure;
- persist retry policy;
- persist resulting act;
- mark the resulting act as retry-derived, not identical to the original expression.

Measure how often recovery changes modality or semantic intent.

### NV-04 — silence as an act

Test cases where the correct behavior is intentionally no outward act.

Verify that:
- the harness can distinguish deliberate silence from generation failure;
- silence can satisfy a communicative intent without being forced into a tool act;
- governance/accounting does not mistake absence of an effector call for absence of agency.

## Relationship to latent translation fabric

The parent exploration proposes specialized modality-native representations projected into local shared spaces.

This exploration adds a complementary output-side question:

**Can a shared intent representation select among available communicative effectors without collapsing every intent into text or a tool call?**

A closed-loop target becomes:

`sensor -> cognition -> communicative/action intent -> modality selection -> effector -> sensor`

This is a concrete candidate for the parent's requirement that at least one effector participate in a closed sensor-cognition-action-sensor loop.

## Design posture

Do not immediately build a universal gesture ontology.

First:
- stop destroying ambiguous expressions;
- retain provenance;
- distinguish interface artifacts from intentional output;
- instrument modality changes caused by retries;
- gather examples from actual beings.

Only then decide whether the intermediate representation should be symbolic, learned/latent, or hybrid.

The important architectural commitment is smaller:

**Non-propositional expression is not necessarily malformed text, and lack of a tool call is not necessarily lack of intent.**
