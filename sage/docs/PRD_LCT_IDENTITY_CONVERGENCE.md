# PRD — SAGE LCT Identity Convergence

**Status:** Proposed  
**Date:** 2026-10-03  
**Issue:** [SAGE#340](https://github.com/dp-web4/SAGE/issues/340)  
**Canonical umbrella:** [web4#874](https://github.com/dp-web4/web4/issues/874)

## 1. Current state

SAGE now has real being LCTs.

The live Hub integration includes publish documents with:
- Ed25519 binding key;
- binding proof;
- canonical key-derived `lct:web4:mb32:b...` id;
- MRH;
- registry publish metadata;
- citizenship references / citizen role pairing for some beings.

The repo also contains older LCT-shaped identifiers from previous generations of the work, including forms such as:
- `lct:web4:agent:dp@Thor#consciousness`;
- `lct:web4:sage:...`;
- `lct:web4:ai:<short hash>`;
- host/machine UUID-era identity artifacts.

Historical material should remain. Live code must no longer treat shape alone as proof of canonical presence.

## 2. Target model

```text
being instance/name
       |
       v
canonical LctId (mb32)
       |
       v
published / verified LCT document
       |
       +-- binding
       +-- MRH
       +-- citizenship
       +-- lifecycle
       +-- assurance evidence
```

Member/routing identifiers remain separate references.

## 3. Requirements

### FR1 — one source of truth for live being identity

Provide one helper/registry path that yields:
- canonical LctId;
- public document/evidence location;
- registry/publish status;
- explicit unresolved state.

Gateway, Hub and governance code should use this rather than constructing LCT-shaped strings.

### FR2 — classify old formats

Inventory non-`mb32` `lct:web4:...` occurrences and classify:
- archive/history;
- fixture/example;
- local task/context identifier;
- compatibility alias;
- live bug.

Historical evidence stays immutable. Active docs/code should clearly mark noncanonical forms.

### FR3 — separate member routing from being presence

A Hub member UUID or seat identity is not automatically the being's LCT.

Record explicit mappings where both exist:

```text
HubMemberId / seat provenance -> being CanonicalLctId
```

For outward governed acts:
- actor presence should be the being LCT when the being acted;
- seat/member id remains routing/operator provenance as appropriate.

### FR4 — citizenship/provenance completion

For citizenship-backed beings:
- authoritative citizenship record stays in the issuing society ledger;
- LCT carries tamper-evident reference + citizen MRH pairing;
- temporary `provenance=self_issued` remains until Hub can verify society-conferred provenance;
- once verifier support exists, republish through the verified path.

Never upgrade provenance because a local file claims it.

### FR5 — assurance refresh

Committed publish docs can outlive the code that generated their assurance values.

Define a reproducible refresh/republish path that derives current fields from actual evidence rather than hand-editing values.

In particular, old software-bound documents carrying `trust_ceiling: 0.85` should not silently remain authoritative once the current conservative implementation/evidence model has changed.

Hardware evidence remains an upstream web4#730 dependency.

### FR6 — rotation/lifecycle

Being key rotation:
- mints a new canonical LctId;
- records lineage;
- preserves old registry history;
- updates Hub/member mapping;
- does not change the being's local durable name/identity record;
- makes stale/superseded signer state visible.

### FR7 — canonical validation

Validation of "is this a canonical LCT?" must check the actual canonical id/document contract, not merely `startswith("lct:web4:")`.

Old task/context strings must never pass canonical-presence validation.

## 4. Tests

Pin:
1. live being identity resolves to canonical `mb32`;
2. old agent/sage/ai short-form strings fail canonical validation;
3. HubMemberId and LctId cannot be accidentally interchanged;
4. mapping resolution is deterministic;
5. missing registry document remains UNKNOWN/absent;
6. citizenship provenance cannot upgrade without verifier evidence;
7. republish derives assurance from current evidence;
8. rotation preserves lineage and updates current mapping only.

## 5. Non-goals

- deleting historical experiments;
- forcing all old docs into current format;
- making hardware presence mandatory;
- assigning one global T3/V3 score to a being;
- treating identity resolution as a trust verdict.

## 6. Dependencies

- Web4 public-key identifier correction: web4#819 or successor.
- Web4 lifecycle/T3-V3 rulings: web4#874.
- Hub identifier/resolver migration: web4#875.
- Hestia canonical member migration: hestia#1202.
- Hardware evidence: web4#730.
