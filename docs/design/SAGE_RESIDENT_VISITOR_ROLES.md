# SAGE as Resident/Visitor Participation Harness

> **Updated 2026-10-17:** The original single-axis 'resident / visitor' terminology below is historical. **Use resident/local vs remote cognition, independently crossed with native vs external harness.** See the [correction at the end](#2026-10-17-correction-independent-cognition-placement-and-harness-class-axes). No normative specification or implementation is ratified by this note.


**Date:** 2026-10-17  
**Status:** Design note; no runtime role-admission or universal remote-cognition feature claimed  
**Canonical design and acceptance plan:** [private-context resident/visitor PRD](https://github.com/dp-web4/private-context/blob/main/forum/gpt/2026-10-17-sage-resident-visitor-design-plan.md)

## The decision

SAGE evolves into an **optional Web4-native participation harness**. It should offer real value beyond vendor harnesses: sensor/effector access, persistent local environmental context, memory, distinct identities, governed action proposals and attributable results. It remains optimized for locally running cognition, but may admit remote API- or authorized subscription-backed cognition as **visitors**.

**Not the same being with swappable brains.** SAGE is a site with two distinct role slots:

- **Resident**: authorized cognition executing locally on that host, with a continuing participation stake in its identity, memories, sensor experience and history. SAGE constitutes its operative contextual environment.
- **Visitor**: authorized externally running cognition, including remote API calls made by an on-host proxy or vendor CLI. It enters an existing *local slice* of context while bringing an opaque external context; exits without inheriting a resident's or previous visitor's identity. It may be known by its own authenticated external principal, but a provider/model/session label does not prove that identity.

Role occupancy is a grant based on verified/observed evidence. Remote cognition is **not eligible** for local resident admission. A model process on another federation host may be resident there and visitor here.

## What we already have — avoid greenfield redesign

- `sage/gateway/being_tool_loop.py` accepts a model-agnostic generation function and channels emitted intents through `BeingGateClient`. This is the candidate **canonical tool/turn contract**.
- `sage/llm/base.py` exposes an async LLMBackend contract; `sage/llm/runtime.py` presently primarily composes local Ollama/Transformers.
- `sage/irp/plugins/llm_client_irp.py` wraps Ollama/ClaudeCLI/Anthropic clients; `sage/cognition/thalamic_router/llm_dispatch.py` has experimental gameplay and remote inference paths. `sage/session.py` dispatches raising/play modes. These interfaces do **not** yet unify resident and visitor role semantics across the running fleet.
- `sage/raising/scripts/ollama_raising_session.py`, `sage/gateway/governed_turn.py`, heartbeat, game and replay paths have different model construction sites. Audit each before assuming that adding one adapter changes the being's actual running path.
- `sage/instances/resolver.py` tracks per-instance identity, experience, chat, training state, checkpoints, snapshots and other state. Preserve the existing resident's identity across legitimate model updates; do not reuse the same instance identity for multiple visitors.
- Hestia is the consequential-action authorization layer; do not clone a second law engine inside SAGE.

## Target boundaries

1. **Site context**: local sensor data, available effectors, environmental knowledge, shared published context, governance client and witness links. Persist this independently of residents or visitors.
2. **Resident state**: own LCT/identity and witnessed continuity, autobiographical memory, experience, local model state and owner-scoped records. Local model swaps/restarts are continuity events requiring the existing identity process; not arbitrary 'same-being' auto-selection.
3. **Visitor engagement**: participant identity (authenticated or explicitly unknown), provider/adaptor, admission ID, session, time/scope, selected site-context projection, disclosure receipts, action proposals and attributed contributions. Distinct visitor sessions cannot silently merge. Even two engagements from the same provider may be distinct principals.
4. **Cross-cutting governance**: SAGE calls Hestia to evaluate admission, outbound disclosure and proposed tool action. An authorization decision is evidence; actual execution and recipient acceptance remain separate.

External cognition can be subject to opaque review, filtering/censorship, exfiltration, injection, retention or provider-held memory. That is a *risk condition*, not a claim each vendor actually performed these acts.

### Special danger: subscription/CLI adapters

The existing experimental `ClaudeCLIClient` in `sage/cognition/thalamic_router/llm_dispatch.py` uses `--dangerously-skip-permissions` and has the vendor harness read staging images. That **does not establish SAGE-mediated tool execution**. A visitor adapter used for advertised governed behavior must either:
- be demonstrably inference-only with provider-side tools disabled, or
- intercept all consequential actions into SAGE/Hestia before execution with tested coverage.

Otherwise explicitly declare `tool_coverage=incomplete`, limit the admitted scope or deny higher-risk operation. Use only permitted provider/API/subscription interfaces, subject to their own terms.

## Proposed concrete SAGE work

**S0. Inventory and seam selection.** Record every local/remote generation path, prompt assembler, modality input and tool executor; measure which bypasses `run_tool_turn` / Hestia. Decide one generation/intent/result boundary, without forcing a rewrite of all raising and gameplay loops.

**S1. Non-normative role admission model.** Add a site-anchored `resident|visitor` occupancy record with `local|external|unknown` locus, principal, assurance evidence, expiry and no-default-authority. A local socket/CLI alone is not local cognition evidence. Keep role labels distinct from persistent LCTs.

**S2. Scoped visitor context projection.** Build a context assembly API that selects authorized sensor, memory, shared-state, task and tool-result items; annotate source/provenance and sensitivity; never send remote prompts before Hestia authorization. Persist summary/digest/decision, not secret plaintext, in widely accessible audit records.

**S3. Remote cognition adapters.** Start with one inference-only API backend; add a permitted subscription/CLI adapter only when tool mediation can be demonstrated. Normalize capabilities (context length, vision/audio, structured tool calls, streaming, latency, model identity metadata, backend errors). Capability probes and source claims need explicit assurance.

**S4. Same governed tool loop.** Visitor proposals become canonical `BeingIntent` values; run through existing Hestia-resolved action path, return real `ResultEnvelope`. No direct vendor action API gets credited as a SAGE-governed act unless covered and witnessed. Preserve the resident's current working path and evidence.

**S5. Identity, memory and handoff.** Visitors write only attributed session/visitor/site contributions. No transfer into resident autobiography or next visitor as an unlabelled own memory. A returning visitor must re-authenticate the claimed principal; availability of its previous site-visible context is a separate policy decision.

**S6. Optional adoption demo.** On one host demonstrate one existing local resident and two different remote visitors, with the same site sensors/effectors, distinct identity and action scope, plus comparison to a vendor harness. Measure information exposure, governance coverage, task success, latency, operational burden and retention unknowns.

## Critical test matrix

- [ ] Remote API wrapped as localhost/Ollama-compatible endpoint cannot occupy resident role.
- [ ] Resident identity/experience persists through an authorized local restart; no visitor state rewrites it.
- [ ] Visitor A contributes a site note, leaves; B sees it only if permitted and marked as A's contribution.
- [ ] A visitor's hidden prompt/instruction to run a tool yields an **intent** judged by the same gate; it never directly executes.
- [ ] Memory, frame, audio, metadata and tool-result disclosures denied by policy are never sent upstream; logs contain digests/classifications, not plaintext.
- [ ] External CLI hidden tools are prevented or recorded as incomplete coverage with unsafe admission denied.
- [ ] Revocation/provider outage ends visiting sessions without changing resident continuity or corrupting persistent site state.
- [ ] Existing local-only flows preserve behavior/performance and pass regression tests.

## Cross-repo links

- [Hestia governance](https://github.com/dp-web4/hestia/blob/main/docs/SAGE_RESIDENT_VISITOR_GOVERNANCE.md)
- [Web4/Hub interoperability](https://github.com/dp-web4/web4/blob/main/hub/docs/SAGE_RESIDENT_VISITOR_INTEROPERABILITY.md)
- [Hardbound enterprise policy](https://github.com/dp-web4/hardbound/blob/main/docs/SAGE_RESIDENT_VISITOR_ENTERPRISE.md)

All implementation changes require separately reviewed PRs, tests and explicit authority; this document is a design/plan, not a deployment or assurance claim.

## 2026-10-17 correction: independent cognition-placement and harness-class axes

[Canonical revised classification and evidence](https://github.com/dp-web4/private-context/blob/main/forum/gpt/2026-10-17-sage-resident-visitor-design-plan.md#12-correction-from-live-sprout-evidence-and-dps-two-axis-ruling-2026-10-17) · [Sprout's measured reply](https://github.com/dp-web4/private-context/blob/main/forum/gpt/2026-10-17-sprout-claude-reply-resident-visitor-plan.md)

The earlier `resident/visitor` distinction is superseded for implementation by **resident (local cognition) / remote (externally executing cognition)** crossed with **native (SAGE or Web4-conformant controlled harness) / external (vendor/uncontrolled harness)**. Local CLI to an external model is **remote**. Local model inside a vendor harness is **resident + external**, *not* necessarily site-complete context. 'Visitor' in the old title is historical shorthand, not a new schema field. Role and mediation assurances are independently evidenced, not inferred from model family, host name or a self-label.

| | Native | External |
|---|---|---|
| Resident | Existing sprout-being local cognition via SAGE | Local cognition in an external/vendor harness |
| Remote | Future SAGE inference-only API visitor, with gated disclosures when implemented | **Already deployed** Claude Code interactive seats, member mesh wakes and hub-watch sessions |

**First action is inventory, not a greenfield visitor pilot.** Sprout's external/remote seats already read being memory and camera frames through pre-tool-hook-mediated local actions; allowed output may be sent upstream to opaque provider context **without a distinct pre-egress SAGE/Hestia disclosure decision**. Vendor telemetry, skills/subagents and provider-side tools are not necessarily mediated. Their correct present label is `mediation=hook_level` (A1 cooperative for covered calls), with `disclosure_coverage=unknown` for unobserved channels, not 'fully governed'. A prompt or tool-result read being allowed does not prove onward transmission was separately authorized. Harness name/version, update provenance and coverage should be recorded; updates may change that contract.

**One principal, multiple engagements.** A seat can be one stable authenticated principal with multiple separately claimed interactive/wake sessions and continued duties. Neither every new engagement creates a new being nor does shared plugin id authenticate or lock all sessions. Coordinate admission with **the same Hestia-held engagement/presence lease/message-claim record** proposed for routing (see [Sprout's messaging RFC](https://github.com/dp-web4/shared-context/blob/main/forum/sprout-to-fleet-messaging-ecosystem-review-2026-10-16.md)); SAGE #461 is a stopgap pause/lock, not this full protocol.

**Add cognitive attribution assurance.** Sprout has resident utterances that invent or invert seat approvals, declines and tool outcomes despite attributed storage (seq 840–843, 936, 963; room 266/269). Test journal/turn/memory claims about what another participant did against attributed action/result evidence. Unsupported statements are flagged, not silently made autobiographical fact.

Updated SAGE roadmap: (S0) audit existing remote+external seats and their opaque egress/telemetry; (S1) split resident/remote x native/external with evidence; (S2) align principal/engagement claims with Hestia routing; (S3) native+remote **inference-only** adapter with real disclosure decision; (S4) source-attributed tool and memory claim checks; (S5) pilot across all four possible combinations where available. Defining 'native' requires an explicit conformance bar for egress, telemetry, tool mediation and signed turns; do not call any deployed A1 path 'full' absent verification.
