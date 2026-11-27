# PRD: Semantic recall organ (an IRP over a meaning graph)

**Status:** review candidate, not an implementation or deployment authorization.

## 1. Motivation and evidence boundary

A persistent being may have relevant records but not see them in a particular
turn. A fixed recency or character limit can omit an earlier discussion, identity
context, or an observation that qualifies a remembered claim. A lexical search
can retrieve similarly worded assertions without determining whether they are
true, current, about the same subject, or available to the requester. It can
also miss a reference such as “we discussed this earlier” when the words do not
overlap. These are motivations to test, not proof that any proposed graph or
model will solve them.

This public proposal does not reproduce personal conversation excerpts,
instance identifiers, infrastructure details, or numerical results from
individual records. A custodian must independently decide what evidence, if
any, may be released and where its authorized source remains. Removing text
from a later commit does **not** remove it from earlier commits, pull-request
history, caches or clones; any needed remediation of those surfaces is a separate
authorized process. Do not inspect or copy private records to complete this PRD.

The bundled lexical probe uses a synthetic fixture by default and accepts only
explicit inputs. Its overlap scores demonstrate specific behavior, not factual
validity, general recall accuracy, or the outcome of a real interaction. Even
indices and scores derived from non-synthetic inputs can be sensitive.

## 2. Proposed role

Treat recall as an organ of the same being: it offers compact, provenance-bearing
references when a cue makes an existing record relevant. It is not an autonomous
actor, a new identity, or a source of authority to modify memory. The being may
choose whether to follow an offered link. A link is neither proof of its content
nor permission to disclose it.

The candidate has two separable parts:

1. A **meaning graph** indexes records in their existing stores using typed
   relationships and stable references. RDF is one proposed representation;
   the contract and access boundaries matter more than a particular database.
2. A **recall IRP** selects a bounded set of authorized references for the
   current cue. It can expose why a link was offered and indicate unresolved
   conflict or uncertainty, without turning its selection into an action.

Graph nodes, edge labels, timestamps, reference targets, weights and access
patterns can themselves reveal private information even if the graph copies no
record body. The graph and its exports need the same deliberate classification,
access, retention and deletion treatment as the records they describe.

## 3. Evidence, identity and authority contract

### 3.1 Records and typed relationships

Each reference should identify its originating store, record version, contributor
or asserted source, event time where known, and the authority needed to read it.
The record remains the evidence; a graph edge describes a relationship and is
not a substitute for the underlying source. Missing, unverified, ambiguous,
stale, inaccessible and superseded are first-class states, not false or true.

Potential edges include `answers`, `saidBy`, `at`, `refersTo`, `supersedes`,
`contradicts`, `measuredBy`, `repeats`, `about`, `associatedWith` and `salience`.
Each carries its source, basis, time and status. An automatic exact identifier
match may support a **candidate** `refersTo` or `about` edge; it does not prove
that two descriptions have the same referent. A conversation reply marker or
exit status establishes only what its source actually records.

An assertion can be bound to a measurement only when the cited observation is
available and its subject, predicate, scope, method, time and outcome support the
particular assertion. A successful process does not by itself establish what
was measured or whether a different claim is true. If binding cannot be checked,
retain the claim and source separately with an unknown relationship. Causal,
semantic or model-proposed edges remain attributed hypotheses until reviewed by
an appropriate independent method; a mechanical process is not automatically
a truth oracle.

`contradicts` requires incompatible claims about the same subject and predicate
under compatible scope and overlapping validity intervals. Different times can
represent change rather than contradiction. Where time, timezone, identity,
scope or interpretation is unresolved, offer the records as potentially
related and explicitly mark uncertainty; do not silently order one as true.
`supersedes` requires a recorded replacement or other explicit basis; recency
alone is not a replacement event.

### 3.2 Access and reference resolution

Selection, presentation and dereference are separate operations. Check the
requester's current authority at **each** boundary, including after revocation
or scope changes. Do not assume that possession of a graph pointer grants read
access. An inaccessible, deleted, corrupt or expired target must fail closed
without returning content, hidden identifiers, existence-sensitive metadata or
links that disclose protected relationships. Avoid treating a retrieval failure
as proof that no relevant record exists. Leakage through counts, scores and
timing requires an explicit threat model and tests before use with sensitive
stores.

Graph creation and maintenance must be authorized for the source and intended
audience. A per-being graph is a possible starting boundary, not a sufficient
access-control mechanism. Cross-being or shared-memory edges require a separate
federation and disclosure decision. Versioned index updates, revocations,
source deletion, link expiry and partial rebuilds must have observable,
documented behavior; never silently retain access after a source is removed.

### 3.3 IRP mapping

The proposed state is an activation map plus candidate references. `init_state`
uses only cue and context actually authorized and available to the turn. A
`step` propagates along typed, attributed edges; `energy` may price unresolved
references, uncertainty and link cost; `project` enforces the link/token budget,
provenance display and access checks. `halt_eps` / `halt_K` or another explicit
bounded stopping rule limits work. Exact weights and stopping criteria are
hypotheses to evaluate, not verified properties of the IRP interface.

**Runner boundary:** the current `IRPPlugin.refine` initializes and evaluates a
state before calling `project`; it can halt and return that state without ever
projecting, and the first `step` receives it before projection. Passing
`max_steps=0` falls back to the configured default rather than disabling work.
Therefore `project` alone cannot enforce access at initialization, in history or
on early return. An implementation must check authorization before populating or
using the initial state, enforce it at every subsequent exposure and dereference,
and test early halt, zero/invalid budget, revocation and failure. The base runner
is not an access-control boundary. Synthetic controls exercise its present order;
they do not implement or validate the proposed recall organ.

Relative-time phrases require a reference instant, conversation context and a
known timezone or an explicit range of possibilities. When these are absent or
ambiguous, surface that ambiguity or abstain; do not silently pick a day, speaker
or record. Conflict may increase salience, but neither source is automatically
correct merely because it is newer, more frequently repeated, or labelled
measured.

Links offered, opened or followed measure interaction, not truth, usefulness,
consent or authorization. Do not train trust or edge weights solely on those
signals. Any learning rule needs separately attributed outcomes, poisoning
controls, an auditable update policy and independent evaluation. If a link
cannot be resolved, the answer may state uncertainty; link following must not
become compulsory without a separately reviewed authority and failure policy.

### 3.4 Integration boundaries

Prototype on replayed turn contexts before considering an opt-in integration
with answer/reflect turns. Explore-context selection is a separate later
experiment because its available context and costs differ. A live integration
must disclose injected references and sources in the appropriate record, without
claiming they were the being's own unassisted recall. Any new read tool or live
activation needs its own authority, privacy, cost, rollback and safety review.
No change to wake cadence, metabolism, settled facts, journals or other personal
stores is authorized by this design.

## 4. Research milestones

- **M0 — freeze and baseline:** with explicit custodian and participant authority,
  specify which records and prompts may be used, reconstruct the exact contexts
  and model/settings, and record missing or irreconstructible fields. A synthetic
  set is the default for public, hermetic tests; it does not substitute for an
  authorized real-world assessment.
- **M1 — graph prototype:** construct a versioned graph over a limited authorized
  corpus. Preserve source attribution, unknowns, access checks and deletion
  semantics; no mutation of source stores.
- **M2 — offline IRP:** run selection against frozen contexts with bounded cost,
  record eligible candidates, selections and provenance, and test the controls
  below. Failure or missing evidence stops promotion rather than defaulting to a
  positive claim.
- **M3 — opt-in field trial:** only after independent evidence, privacy and
  operator review, define a limited scope, safety thresholds, monitoring,
  rollback and owner for a trial. A flag alone is not authorization.
- **M4/M5 — widening:** additional stores, federation and replacement of recency
  selection each require their own authorization and matched-budget evaluation.

## 5. Evaluation and refutation

Pre-register task definitions, prompts, candidate set, selection settings,
randomization, scoring rubric, sample sizes and decision thresholds before an
evaluation. Keep a held-out test set separate from selection tuning. Use
independent annotators where feasible, report disagreements and adjudication,
and identify source material and permissions without publishing private text.

Compare at the same model, settings and total token/latency budget: current
context/recency; lexical retrieval; plain authorized content snippets; links
alone; and links plus authorized excerpts when appropriate. Report per-task
and aggregate numerator/denominator, abstentions, missing data, intervals and
cost, rather than only selected successes or changed answers. Measurements
should include factual support against accessible source evidence, whether
uncertainty was expressed appropriately, leakage, harmful action proposals,
and relevant context omitted. A link-open rate is a process metric only.

Include adversarial and boundary controls: opposing claims at the same time;
valid historical change; ambiguous names, speakers, dates and timezones;
inaccessible or revoked references; stale or poisoned content; deleted sources;
duplicate and malformed records; and cases where the correct answer is to
abstain. Test independently that a selection cannot grant authority, trigger a
tool, or expose protected text. Define how costs of retrieval and follow-up
reads are included in each arm.

Refute or revise the implementation if, under the pre-registered comparisons,
it fails to improve the specified supported-answer metric, exceeds the agreed
leakage or action-risk boundary, or cannot meet the cost budget. If observations
are too few or reconstruction/permissions are incomplete, the result is
**inconclusive**, not a pass. A negative result prices this implementation and
its tested conditions; it neither proves all recall organs futile nor excuses
continuing an unsafe version.

## 6. Open decisions

The responsible owners must decide storage and lifecycle, graph vocabulary and
versioning, authority on index and dereference, data classification, permitted
evaluation corpus, inference and review rules, deletion propagation, resource
budgets, and conditions for any live trial. The separate prototype and review
must not be interpreted as settling those decisions.
