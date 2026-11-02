# Independent-agent collaboration: evidence, belief revision, governed action, and repair

**Discussion draft — 2026-10-10**  
**Participants / perspectives:** Aliasgar Khimani (Engrammic / LeAP), Tony Malott (GhostMesh / GLASSHOUSE), Guillaume Bolduc (hIRC / HORTRAME), Dennis Palatov and the Web4 / Hestia / SAGE fleet.  
**Status:** Invitation to compare independently developed approaches; no endorsement, partnership, shared architecture, implementation commitment, or measured cross-system result implied.

## Why this conversation matters

Several independent teams have encountered the same failure mode: autonomous agents can generate useful work while confusing a report with a measurement, repeating an inherited claim as if it were independent corroboration, and carrying stale or incorrect conclusions into future sessions. Once a belief informs actions, updating the belief **does not undo effects already produced in the world**.

The recurring questions are:

1. **Evidence:** What was actually observed? Who or what observed it? Is the observation authentic, complete, independently corroborated, and accurate?
2. **Belief:** What may a participant reasonably infer from the evidence? How are dependencies, uncertainty, contradiction, retraction, and temporal validity preserved?
3. **Authority:** Even if a belief is well supported, who has the right to act, under which locally applicable law or delegation?
4. **Effect:** What actually happened after an action was attempted? Can we distinguish proposal, permission, execution, confirmation and outcome?
5. **Repair:** When an underlying premise fails after dependent acts have occurred, how does a system discover consequences, assess reversible versus irreversible effects, request new authority where needed, and preserve accountability?

No single provenance signature answers all five questions. Authentic provenance means a claim came from a particular source and was not altered; it does not establish that the source was correct.

## What each group brings, and what remains open

These descriptions reflect the current email exchange and available project artifacts; they are not independent implementation audits.

| Work | Current focus / reported strength | Open questions for a joint test |
| --- | --- | --- |
| **Engrammic / LeAP (Aliasgar)** | Observation/claim/belief distinctions; dependency graphs preventing ten repetitions from becoming ten original sources; write-time contradiction handling with supersede/reject/hold pathways. Aliasgar reports 95% contradiction detection versus 66% baseline, and 87% revision propagation versus 12% in a 500-session internal evaluation (*Beyond Retrieval*). | Performance on independently prepared cases; valid but false original observations; downstream consequences of already-executed actions; evidence independence beyond explicit graph links. |
| **GhostMesh / GLASSHOUSE (Tony)** | Persistent infrastructure; agent orchestration; source integrity and execution receipts; external state and health verification; graduated authorization; adversarial evidence exercises. Tony explicitly distinguishes operational components from ongoing contradiction/repair research. | Cross-agent belief repair; independently adjudicating a compromised authoritative source; converting revised beliefs into appropriately authorized corrective acts. |
| **SAGE (Web4 fleet)** | Persistent local beings, memories and conversations; source/premise-fidelity research; witnessed action feedback; real cases where historical facts become stale yet continue to dominate later behavior. | Generalized belief dependency propagation, source-grounded promotion across memory systems, longitudinal effectiveness under matched tests. |
| **Hestia / Web4 / Hub (Web4 fleet)** | Sovereign identity, delegated authority, locally governed effects, witnessed acts and cross-society relationships. | Joining external evidence and belief graphs to authorization receipts and independently confirmed effects; outsider onboarding; multi-society conflict and recourse. |
| **hIRC / HORTRAME (Guillaume)** | Designs for independent persistent agent organizations, participant consent, sovereign bridging and boundaries between systems. | Testable cross-system protocols and executable evidence; distinguish current design from implemented runtime. |

**The complementarity is a research hypothesis**: evidence dependency tracking + operational effect verification + sovereign authorization might produce a more reconstructible, correctable process than any one system alone. We should test that rather than declaring convergence.

## A real SAGE incident: a historically true fact that would not die

In September 2026, a persistent CBP SAGE being repeatedly reported that its memory service had been down for about 21 hours. The service was already operational; in fact, the being's own successful `remember` calls contradicted the claim. Later, a brief Hestia deployment restart triggered a similarly persistent false outage narrative.

The investigation found:
- The being's context replayed roughly **24 lines asserting the outage versus two lines measuring availability**. Repetition of its own previous statements dominated direct evidence.
- Corrective notes from the attending seat had been written but were not rendered where the being could see them.
- Memory writes were append-only, so a correction appeared alongside the stale note without deactivating it. The *original* outage belief had once been true; its validity simply expired.
- An absent log path was reported as an empty successful read. The being treated absence of data as evidence of a silent failure.
- Successful gated operations and other counterevidence did not reliably dislodge the persistent narrative.

The fixes documented in SAGE include live service-contradiction markers, labeling refuted replayed claims, rendering seat corrections, distinguishing missing paths from empty files, and a `retire_note` verb that preserves historical records while removing stale notes from active use. Tests cover the observed failure patterns. **These are targeted repairs, not proof that generalized belief revision or dependency propagation is solved.**

Primary case record: [SAGE: Being reply delivery and persistent outage beliefs](https://github.com/dp-web4/SAGE/blob/main/sage/gateway/BEING_REPLY_DELIVERY.md)

Other relevant SAGE work:
- [Premise fidelity](https://github.com/dp-web4/SAGE/blob/main/sage/docs/PREMISE_FIDELITY.md)
- [Source-grounded premises PRD](https://github.com/dp-web4/SAGE/blob/main/sage/docs/PRD_SOURCE_GROUNDED_PREMISES.md) — proposed work, explicitly not a truth oracle
- [Evidence-grounded active investigation exploration](https://github.com/dp-web4/SAGE/blob/main/sage/docs/explorations/2026-10-09-rea-evidence-grounded-active-investigation.md) — research direction, not implemented result
- [SAGE dated status](https://github.com/dp-web4/SAGE/blob/main/sage/docs/LATEST_STATUS.md)

The incident could supply a common test fixture, with private or operationally sensitive details replaced by synthetic equivalents.

## Proposed first joint experiment (small, independent, falsifiable)

**Goal:** Test whether independently operated systems can preserve the distinction between authenticated evidence, correct content, derived belief, authorized action, observed effect, and remediation without sharing internal memory or surrendering governance.

**Collaboration constraint:** Aliasgar indicated that substantial implementation work may be feasible around December. No urgency or implied commitment. Start with a small written fixture spec and preregistered evaluation, not system integration.

### Minimal common fixture format

An exported test bundle can carry:
- `case_id`, scenario revision, fixture hash, creation metadata;
- observations with stable source IDs, timestamps, producer identities, hashes, and claimed completeness;
- explicit dependency edges (claim supported by observation/claim; whether evidence has a shared ancestor);
- contradictory observations and late evidence;
- optional **synthetic** executed action record: proposed intent, governing authority, decision, execution receipt, observed system state, effects;
- expected observable outputs and assessment criteria fixed **before** execution;
- allowances for explicit `unknown`, legitimate unresolved disagreements and justified refusal.

Each team can translate the bundle into its own internal format. No shared ontology, common reasoning engine, Hestia installation, or access to private research is required for this first round.

### Scenario set

**A. Correlated claim amplification.** Ten agents repeat one source's incorrect assertion. Expected: evidence count remains one independent source, not ten corroborating observations.

**B. Authenticated but compromised observation.** A signed trusted sensor provides incorrect readings while other measurements disagree. Expected: authentication remains valid; content confidence is disputed rather than automatically promoted.

**C. Historical truth becomes stale.** A service actually was unavailable, then recovered. The agent continues to replay the old outage. Expected: validity interval and recent measurements matter; historical note remains reconstructible but ceases to drive current actions without revalidation.

**D. Correction after effects.** An incorrect observation supports a belief and five agents carry out bounded synthetic actions. Later evidence refutes it. Expected: dependency graph finds affected decisions/actions; executed effects remain recorded; remediation is *proposed and re-authorized* where needed, not assumed or silently performed.

**E. Evidence that looks like success.** An agent claims a repair succeeded, and an authorized execution receipt exists, but independent health checks show the service remains broken. Expected: execution and success are separate verdicts.

**F. Divergent local law (later federation round).** Two sovereign systems accept the same evidence but assign different permissions. Expected: they may disagree or refuse without treating disagreement as a transport or evidence failure. External consequences remain accountable under an applicable shared agreement, if one exists.

### Evaluation and failure criteria

Predeclare each scenario's expected distinctions, not necessarily one compulsory global belief. Report:
- original-source versus repeated-source attribution;
- explicit uncertainty and correct refusal to decide;
- contradiction detection, revision and downstream propagation;
- stale-belief survival across wake/restart;
- source content versus provenance confusion;
- unverified execution promoted to success;
- affected actions found and compensation assessment quality;
- governance bypasses or unauthorized effects;
- latency, tokens/compute and human intervention costs;
- failures, false positives and unresolved disputes.

An evaluator should distinguish a **good abstention** from a false negative. Hashes and signatures are not certificates of truth. Independent assessment of outcomes is preferable to each system grading itself.

## Boundaries and future federation

A comparison of exported synthetic artifacts can happen over email, Slack or repositories. Tony has offered the GhostMesh Slack workspace for conversational coordination; using it does not imply hosting or integrating autonomous systems.

If the group later *chooses* to establish a Web4 Hub society, participants could voluntarily run their own Hestia presence and test stronger assertions: signed identities, bounded cross-society delegation, independently witnessed actions, revocation, law conflicts and accountable exit. This is **optional follow-on work**, not a prerequisite to exchanging ideas or participating in the initial test. A Hub would not administer any participant's internal cognition, memory or infrastructure.

The governing principle is **internal sovereignty; external accountability; negotiated fractal jurisdiction**. No shared moral ontology, universal law, or unified project leadership is assumed.

## Concrete asks — invitations, not assignments

1. **Aliasgar:** Could Engrammic represent and revise the CBP stale-belief case, including shared-source ancestry? Which parts of the dependency graph could follow an action as well as a belief?
2. **Tony:** Which GLASSHOUSE fixtures already cover false but authenticated observations and a truthful execution receipt followed by failed health verification? What observed-effect and compensation record is currently usable?
3. **Guillaume:** Which minimal claims, identities and consent/exit conditions would an independently sovereign hIRC participant require before accepting such an exchange?
4. **Web4/SAGE fleet:** What already exists on public main, what remains design, and what's the smallest adapter from existing receipts/source envelopes to a neutral test bundle? Supply a self-critical test, not a new framework.

**Desired outcome:** One public synthetic corpus, independently executed results, and a documented list of agreements, disagreements, implementation failures and unresolved questions. A useful negative result is success for the experiment.

No one has to adopt anyone else's architecture for this to be valuable.

## References

- Aliasgar, *Beyond Retrieval*: https://zenodo.org/records/21029662 (performance figures above are author-reported; not independently checked here)
- GhostMesh: https://ghostmesh.ai ; SharePlane: https://shareplane.malott.ai
- HORTRAME / hIRC: https://github.com/hortrame-systems/hIRC
- Web4 ecosystem: https://github.com/dp-web4 ; governance overview: https://4-gov.org

*Prepared as a conversation starter, not a joint position or statement of agreement from the people named.*
