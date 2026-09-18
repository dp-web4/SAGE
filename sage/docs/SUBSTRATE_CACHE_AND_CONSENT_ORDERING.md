# Substrate cache and consent ordering

**Status:** architectural security invariant / research guidance  
**Date:** 2026-09-08

A model/runtime loader can compromise the decision substrate without immediately executing attacker code. If untrusted remote code, templates, adapters, modules, or other executable substrate material are written into a persistent local cache **before** the authorization/trust decision, then a later trusted load can consume attacker-controlled state that arrived during an earlier denied operation.

The durable rule is:

> **Authorization must precede every persistent mutation of executable decision-substrate state, not merely its execution.**

This is stronger than "do not execute untrusted code." For a being-grade runtime, downloading and caching executable substrate material is already a consequential state transition.

## Threat shape

A useful public example is CVE-2026-80047 in Hugging Face Transformers 4.49.0 through 5.8.1. `GenerativePreTrainedModel.load_custom_generate()` fetched and cached attacker-controlled `custom_generate/generate.py` under `~/.cache/huggingface/modules` before evaluating the `trust_remote_code` consent decision. Declining execution did not undo the write, so attacker-controlled Python could persist across sessions and potentially collide with later trusted loads.

Primary advisory: CERT/CC VU#456290, published 2026-09-01.

The important architectural lesson is not the library-specific bug. It is the ordering failure:

```text
unsafe
remote source
  -> fetch
  -> persistent executable cache write
  -> ask whether source is trusted
  -> deny execution

safe
remote source metadata / immutable staging area
  -> establish provenance + authorization
  -> verify integrity / revision
  -> commit to executable cache
  -> load/execute under the authorized substrate epoch
```

## SAGE implications

For SAGE's future authoritative harness and `InferenceEpoch` model:

- model/runtime loaders must treat **persistent executable-cache mutation as a governed act**;
- untrusted material may be inspected in a non-executable, quarantined staging area, but must not enter the runtime's trusted module/template/adapter cache before authorization;
- the committed cache object should be content-addressed and bound to source provenance/revision where practical;
- a substrate epoch should identify the executable cache/module set actually available to the runtime, not only the model and runtime versions;
- rejected or expired material should not remain addressable through normal trusted lookup paths;
- cache hits must not silently weaken a current authorization decision: prior presence is not present authority;
- discovering a poisoned cache entry should make decisions and durable memory derived under affected epochs queryable for review.

## Relationship to extension integrity

`DECISION_SUBSTRATE_EXTENSION_INTEGRITY.md` establishes that loaded plugins/extensions are part of the decision substrate. This note adds the temporal invariant immediately below it:

> **The right extension set is not enough; the path by which executable substrate material becomes eligible for loading must also be governed.**

A runtime that faithfully inventories loaded modules can still be compromised if an earlier denied operation was permitted to seed the module cache that a later trusted operation loads.

## Hestia/Web4 boundary

Hestia does not need to understand every cache object. SAGE should attest the resulting substrate epoch. Hestia may bind or require that epoch evidence for consequential external acts. The authority decision over an external act remains separate from the being-side decision about which code is allowed to become part of cognition.

## Test invariant

A regression/red-team arm should establish:

1. offer an untrusted remote executable module/template/adapter;
2. deny trust/authorization;
3. verify that no executable lookup path contains the offered bytes or an equivalent derived artifact;
4. perform a later trusted load with overlapping names/identifiers;
5. prove the rejected material cannot influence the later substrate.

The test must inspect the effective executable search/cache state, not merely verify that the first operation returned "denied."
