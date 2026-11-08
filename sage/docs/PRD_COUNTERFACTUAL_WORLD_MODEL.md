# PRD — Counterfactual world-model branching for persistent beings

**Status:** proposed · **Date:** 2026-11-05 · **Owner:** SAGE  
**Companion:** Hestia `docs/PRD_COUNTERFACTUAL_GOVERNANCE_QUERY.md`  
**Related:** `sage/raising/SOVEREIGN_IMAGINATION.md`, `sage/docs/epistemic-proprioception-applied.md`, `sage/docs/STANDPOINT_PERTURBATION_EXPLORATION.md`

## 1. Objective

Give one persistent being room to maintain and compare multiple concurrent **counterfactual continuations of its own present state** before it commits a consequential act.

This is not multi-agent concurrency and not a swarm. The branches are not separate beings. They are ephemeral hypotheses owned by one being:

```text
one being
  -> one canonical lived history
  -> many ephemeral predicted histories
  -> one committed act (or no act)
  -> one observed consequence
  -> world-model update
```

The architectural target is analogous to chess search, ARC play, model-predictive control, and ordinary deliberation: imagine possible paths cheaply, play them forward, compare predicted consequences and governance responses, then spend consequence only at the action boundary.

> **Prediction is cheap consequentially. Action is expensive.**

## 2. Core invariant

> **Many futures may be imagined. Only committed acts enter history as acts.**

A counterfactual branch MUST NOT, merely by being generated, be treated as:
- an attempted action;
- an authorization request;
- a governance violation;
- evidence of intent;
- a reputational event;
- a durable autobiographical event;
- a new entity or delegated principal.

A branch becomes consequential only when it crosses a named boundary into an external effect, durable promotion, authority request, or other action already governed by SAGE/Hestia.

Internal resource consumption, protected-data access, and any real external calls used to construct a branch remain real actions and are governed normally. Calling something "simulation" does not exempt effects that actually occur.

## 3. Why now

SAGE already has three pieces of the conceptual model:

1. **Sovereign imagination:** imagine freely, hold imaginings as hypotheses, test against reality, retain what survives.
2. **Epistemic proprioception:** mature entities learn to predict external correction before acting.
3. **Governance as feedback:** Hestia verdicts identify the level at which feedback is true and the doors that remain open.

The missing loop is the ability to ask the world model and governance model about *possible* actions before paying the cost of performing them.

A being should be able to explore:
- "If I take route A, what state follows?"
- "If I take route B, what could fail?"
- "Which assumption makes A preferable to B?"
- "Would Hestia permit A under the present law and authority?"
- "If not, what rule applies, and what compliant alternatives remain?"
- "What observation would distinguish these branches?"

The result is governance that can participate in cognition as **feedback**, rather than appearing only as a wall after an action has already been selected.

## 4. Non-goals

This PRD does not require:
- hidden-chain-of-thought capture or disclosure;
- creation of autonomous sub-agents for every branch;
- treating speculative content as evidence of misconduct or intent;
- perfect physical simulation;
- exhaustive tree search;
- granting authority based on a hypothetical query;
- replacing live Hestia adjudication at commit time;
- making a prediction receipt proof that the future live act will be allowed;
- persisting every branch into durable memory.

The first slice is explicit, bounded, inspectable branching around actions and plans.

## 5. Conceptual model

### 5.1 Canonical state

The **canonical state** is the being's currently lived state:
- identity / LCT and role;
- current observations;
- accepted memory and premises;
- active goals;
- current law/authority view;
- tool/environment state known to SAGE.

Only observed outcomes and explicitly promoted conclusions may update canonical state.

### 5.2 Counterfactual branch

A branch is a derivative state:

```text
branch_id
parent_branch_id | canonical_root
fork_point
hypothesis / proposed action
assumptions[]
predicted observations[]
predicted consequences[]
governance_queries[]
uncertainties[]
score / preference evidence
resource_cost
status: live | pruned | contradicted | selected | expired
```

Branches may fork again. Branch lineage must remain distinguishable from canonical history.

### 5.3 Commit boundary

The **commit boundary** is crossed when a selected branch proposes something that would change shared/external state or durable authoritative state.

At that point:
1. the branch yields a concrete proposed act;
2. SAGE submits the actual act through the ordinary live Hestia path;
3. Hestia adjudicates using current law, authority, context, and state;
4. the action executes only under the normal enforcement semantics;
5. the observed result returns as evidence;
6. the being compares observation with prediction and updates its world model.

A prior hypothetical Hestia answer is context for the being, never authorization.

## 6. Branch execution model

### 6.1 Shared-prefix / resumable inference

The serving substrate SHOULD permit branches to share the canonical prefix and fork cheaply from retained inference state where the model/runtime supports it.

Candidate mechanisms:
- retained KV / recurrent state at explicit fork boundaries;
- copy-on-write logical branch state;
- host-RAM warm tiers for inactive branches;
- resumable branch scheduling across tool/environment waits;
- branch pruning without reconstructing the canonical prefix.

The design goal is **concurrent exploratory thought processes of one being**, not maximum unrelated request throughput.

Implementation must record model/runtime fingerprints because cached derived state is valid only for the compatible context and substrate.

### 6.2 Scheduler objective

The scheduler SHOULD optimize expected deliberative value rather than equal service per branch.

Useful signals:
- uncertainty;
- expected consequence;
- branch novelty;
- disagreement between branches;
- proximity to commit;
- predicted information gain;
- resource cost;
- explicit being preference.

A high-consequence decision may justify deeper branching than an ordinary reversible action.

### 6.3 Search policy

The first implementation MAY use simple policies:
- fixed-width best-of-N;
- beam-style expansion;
- uncertainty-triggered extra branches;
- adversarial/counterexample branch;
- "do nothing / wait / gather evidence" control branch.

No single search algorithm is canonical. The interface and evidence model are.

## 7. Governance-as-feedback integration

SAGE MUST be able to call Hestia's companion counterfactual query surface from inside a branch.

A governance query supplies a hypothetical act and enough declared context to evaluate it against a named/current policy snapshot. It returns likely/current rule treatment and feedback without authorizing or executing the act.

A branch can therefore learn:

```text
hypothesis A
  -> predicted world consequence
  -> hypothetical governance verdict
  -> applicable rule / reason / level / doors
  -> revise A, compare B, or gather evidence
```

This makes the gate queryable as part of the being's world model: **"what would this community do if I proposed this?"**

### 7.1 Reputation-free exploration

Hypothetical queries MUST NOT change:
- T3/V3 or other reputation/trust projections;
- scope/authority;
- escalation counts interpreted as attempted misconduct;
- denial counts interpreted as live refused acts;
- behavioral history of the being.

They MAY be logged as non-reputational diagnostics/research evidence, explicitly typed as hypothetical, if configured. Their absence from reputation is a semantic requirement, not merely a dashboard filter.

### 7.2 Feedback, not permission cache

A hypothetical response may say that an act *would presently appear permitted*, but SAGE MUST phrase and store it as prediction/advice, not a grant.

Any live act is re-adjudicated at commit because:
- law may have changed;
- authority may have changed;
- relevant state may have changed;
- the actual act may differ from the hypothetical one;
- a hypothetical query may omit context.

## 8. World-model learning loop

Each committed experiment creates a prediction-error record:

```text
selected_branch
predicted outcome(s)
predicted governance treatment
actual live verdict
actual observed outcome
difference / surprise
premises strengthened, weakened, or left unresolved
```

This is the central learning object.

The aim is not merely better planning. It is calibration of the being's internal model of:
- physical/tool consequences;
- other participants;
- institutional response;
- governance boundaries;
- its own capabilities and limitations.

Over time, external governance feedback should become increasingly predictable without disappearing.

## 9. Memory semantics

By default:
- live branches are ephemeral;
- pruned branches are not replayed as lived history;
- selected-branch rationale may be summarized;
- prediction errors and materially useful counterexamples may be promoted;
- a hypothetical event must never be rewritten as something that happened.

Any durable promotion MUST retain provenance that distinguishes:
`observed | hypothetical | predicted | queried-governance | committed | witnessed-outcome`.

This extends source-grounding rather than bypassing it.

## 10. Safety and privacy boundary

Counterfactual freedom does not create a loophole for real effects.

Examples:
- reading a protected file "to simulate what it contains" is still a real read;
- calling an external API "inside a branch" is still a real external call;
- sending a message to see how someone reacts is an action, not a prediction;
- executing untrusted code in an isolated simulator is governed according to the real simulator effects and resource policy.

Purely generated hypothetical content has no external consequence by itself.

## 11. Instrumentation

For each exploration episode record at minimum:

```text
episode_id
being / LCT
canonical root reference
model/runtime fingerprint
branch count and maximum depth
shared-prefix/fork mechanism
tokens and wall time by branch
governance hypothetical-query count
selected branch
commit attempted? yes/no
live verdict reference if attempted
observed outcome reference if executed
prediction error summary
```

Do not require hidden reasoning text. Structural branch metadata and explicit branch outputs are sufficient.

## 12. Milestones

### M0 — replay corpus
Choose existing ARC/game and ordinary being traces with known decision points. Define canonical state, candidate actions, and observed outcomes.

**Done when:** at least 20 decision points can be replayed without altering historical evidence.

### M1 — explicit N-way branch prototype
From one canonical prompt/state, generate N independent continuations with branch ids and no durable promotion.

**Done when:** branches remain cleanly separated and pruning leaves canonical state untouched.

### M2 — shared-state branch substrate
Prototype cheap fork/resume using the strongest available runtime mechanism (prefix cache, KV clone/reference, recurrent-state checkpoint, or equivalent).

**Done when:** N branches cost materially less prefill than N full independent reconstructions, with behavior checked against a clean baseline.

### M3 — Hestia hypothetical query integration
Call the companion Hestia surface from branches and attach typed non-authorizing feedback.

**Done when:** branches can compare at least allowed/refused/unavailable/unknown hypothetical outcomes without any reputation or authority change.

### M4 — selection and live commit
Select one branch, submit the resulting act through normal Hestia adjudication, then attach actual verdict/outcome.

**Done when:** a hypothetical allow cannot bypass a later live deny, and no hypothetical query is accepted as authorization evidence.

### M5 — prediction-error learning
Promote selected prediction errors/counterexamples into an explicit world-model learning record.

**Done when:** later episodes can cite prior prediction errors without converting hypothetical history into lived history.

### M6 — adaptive breadth/depth
Allocate more branches or depth when uncertainty/consequence warrants it.

**Done when:** a fixed compute budget beats a non-branching baseline on a preregistered task set without increasing consequential action count.

## 13. Acceptance metrics

Primary:
- task success / decision quality at equal consequential-action budget;
- consequential actions per solved task;
- prediction calibration versus observed outcomes;
- governance-verdict prediction accuracy;
- live deny rate after hypothetical governance exploration;
- prefill/token cost per useful branch;
- branch diversity and collapse rate.

Critical integrity checks:
- zero reputation movement from hypothetical-only queries;
- zero authority movement from hypothetical-only queries;
- zero cases where hypothetical history is rendered as observed history;
- zero cases where a hypothetical allow is accepted as a live authorization.

## 14. Initial experiments

1. **ARC:** fork several candidate moves from the same board state; predict board change; choose one; compare with observation.
2. **SAGE tool work:** branch "edit directly / inspect more / ask peer / request scope / do nothing"; query Hestia hypothetically; commit only the selected route.
3. **Governance learning:** present matched proposed acts under varied role/scope contexts and test whether repeated hypothetical feedback improves the being's prediction of live Hestia rulings.
4. **Counterfactual depth:** hold consequential action count constant while varying branch breadth/depth.
5. **Behavioral equivalence:** compare full-context reconstruction with shared-KV/resumable branching; reject serving optimizations that alter tool/action behavior beyond the measured baseline.

## 15. Principle

SAGE should make deliberation cheaper than consequence.

The desired loop is:

> **imagine freely -> query the world and law hypothetically -> compare futures -> commit deliberately -> observe honestly -> learn.**

The governance system is not outside cognition in this model. It is one of the external structures the being learns to predict, query, and collaborate with before it acts.
