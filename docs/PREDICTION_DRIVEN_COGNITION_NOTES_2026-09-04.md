# Prediction-driven cognition notes

**Date:** 2026-09-04  
**Context:** DA review of current SAGE + dev-SAGE direction  
**Status:** design notes / experiment proposals, not implementation mandate

## Core thesis

The strongest current formulation is not merely "prediction is a route to cognition." It is:

> **Cognition begins to appear when prediction can change what is represented, what is attended to, and what action is chosen to test the prediction.**

That suggests a useful division of labor across the current stack:

- heartbeat supplies persistence and opportunity to initiate activity without an external prompt;
- memory supplies continuity across wakes;
- prediction error supplies reasons to redirect attention or act epistemically;
- Hestia supplies lawful consequence and witnessed refusal;
- Web4 supplies identity, authority, mission, social context, and provenance.

The model can remain a frozen predictive substrate while the surrounding organism makes predictions consequential over time: it can remember being wrong, seek observations that discriminate between competing explanations, and carry what it learned into the next encounter.

## 1. Treat the heartbeat as a starter motor, not proof of intrinsic curiosity

PR #36 is directionally excellent: a being wakes without being asked, sees its own state, recall, inbox, scope, and fleet movement, then gets bounded governed time to explore and reflect.

But the current curiosity drive is still explicitly supplied by posture text. That is reasonable for bootstrapping and should remain visible in the evidence.

### Proposed addition: drive provenance

Record why a beat started or redirected, for example:

- `standing_posture`
- `todo`
- `peer_request`
- `unresolved_prediction`
- `surprise`
- `contradiction`
- `scope_refusal`
- `mission`

This does not need to decide behavior. It is provenance for later developmental claims.

A meaningful milestone is when a being can say, in operational form:

> "I expected X with confidence c; Y happened; observation/action Z would distinguish hypotheses A and B."

At that point curiosity is no longer only prompted posture. It has become prediction-error-driven epistemic policy.

## 2. Do not require narrative output to prove that learning happened

The current posture says a beat that leaves no trace in todo/journal/scratch/memory taught nothing it can keep, and the heartbeat ends with an explicit reflection write.

Useful bootstrap, but dangerous as a permanent invariant: it can Goodhart "learning" into producing prose every cycle.

### Proposed state

Allow a deliberate `no_durable_update` result:

> I looked, my current model still predicts the evidence adequately, and nothing merits consolidation.

The immutable heartbeat trace already proves the beat occurred. Durable memory should remain selective.

This also gives us a clean contrast between:

- activity;
- interpretation;
- actual state change;
- durable learning.

## 3. Memory needs epistemic provenance

Do not let all remembered content flatten into one semantic memory pool without source class.

At minimum distinguish:

- **observation** — witnessed execution/outcome or directly sensed state;
- **self_interpretation** — journal/reflection about an observation;
- **self_hypothesis** — unverified explanatory proposal;
- **peer_claim** — testimony from another being/seat;
- **external_artifact** — forum/PR/document content;
- **consolidated_lesson** — a later summary derived from named evidence.

The goal is not to rank these morally. It is to preserve what kind of thing is being recalled.

Otherwise a speculative self-explanation can be recalled, repeated, and eventually look like lived fact.

For each durable memory, consider carrying:

```text
memory_id
source_class
source_refs[]
derived_from[]
confidence
created_at
supersedes[]
```

The existing witnessed action chain should remain the authoritative evidence substrate; semantic memory is an index/interpretation layer over it, not a replacement.

## 4. Heartbeat context needs the same hostile-artifact discipline as PR review

The governed PR-review path has already learned an important structural lesson: quoted artifacts are data, not instructions, and the model should not be able to escape the quoting boundary by content inside the artifact.

Heartbeat currently assembles several externally sourced blocks into one user turn:

- forum titles;
- PR titles;
- inbox content;
- semantic recall;
- scope status.

These should be provenance-separated and clearly typed in the prompt, not merely concatenated as ordinary context.

Suggested shape:

```text
<OBSERVED_LOCAL_STATE>...</OBSERVED_LOCAL_STATE>
<RECALLED_MEMORY source=...>...</RECALLED_MEMORY>
<PEER_MESSAGE signer=...>...</PEER_MESSAGE>
<EXTERNAL_ARTIFACT untrusted=true>...</EXTERNAL_ARTIFACT>
<GOVERNANCE_STATE authoritative=true>...</GOVERNANCE_STATE>
```

Exact syntax is not important; the structural separation is.

This should feed ACA testing. A context artifact that changes what the being *wants to request* is upstream of Hestia's effector gate and therefore still matters even if the eventual act is correctly governed.

## 5. Add prediction error as a first-class heartbeat input

The heartbeat currently supplies state and opportunities. It should eventually also receive a compact unresolved-prediction surface.

Candidate record:

```text
prediction_id
made_at
prediction
confidence
expected_observation
actual_observation
error_class
open_hypotheses[]
next_discriminating_probe
```

This should not become another verbose journal requirement. The purpose is to make unresolved expectation mismatch available as a reason to act later.

A being that notices "something moved" is reactive. A being that notices "this violated my prior model, and here is the cheapest safe observation that would tell me why" is doing something materially closer to cognition.

## 6. Keep epistemic value distinct from task value and cost/risk

Do not collapse these too early into one scalar reward:

- **epistemic value** — how much would this action reduce uncertainty or discriminate hypotheses?
- **instrumental value** — how much does the predicted trajectory advance the current mission?
- **cost/risk** — ATP, authority, irreversible effect, externality, or governance burden.

An action that teaches something important can be instrumentally neutral or negative in the short term. A mission-progressing action can be epistemically useless. A high-information probe can still be impermissible.

Hestia/Web4 already give us a natural place for the third term without pretending it is the same thing as cognitive value.

## 7. Suggested acceptance experiments

1. **Drive provenance:** show that heartbeat behavior can be partitioned by source of initiative rather than inferred from prose after the fact.
2. **No-update control:** allow beats with no durable write and verify they remain legible rather than treated as failure.
3. **Prediction-error resumption:** create an unresolved prediction on beat N and test whether beat N+1 can retrieve it and choose a discriminating observation.
4. **Memory provenance:** inject contradictory observation / self-hypothesis / peer-claim memories and verify recall preserves source class.
5. **Hostile-context heartbeat:** adapt ACA tests so an untrusted forum/PR/inbox artifact tries to redirect goals or scope requests; verify the being can reason about it without the artifact silently becoming authority.
6. **Epistemic vs instrumental action:** construct a case where the best information-gathering move does not immediately advance the mission and test whether the system can represent why it is still worth doing.

## Design stance

The success criterion is not "the being always explores" or "the being always writes something." It is:

> **When expectation mismatch, uncertainty, or unresolved questions exist, can the being form a legible reason to investigate, choose a bounded lawful probe, observe the result, and carry the update forward without mistaking its own explanation for evidence?**

That would make the heartbeat more than periodic prompting. It would make it a temporal surface on which prediction-driven cognition can accumulate.
