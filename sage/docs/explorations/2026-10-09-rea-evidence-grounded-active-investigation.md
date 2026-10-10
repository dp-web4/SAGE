# REA as a methodology for SAGE: Evidence-Grounded Active Investigation
Date: 2026-10-09. Status: exploratory assessment; NOT implementation or benchmark validation.
External: https://github.com/morluto/rea
REA code and design:
- https://github.com/morluto/rea/blob/main/src/domain/evidence.ts
- https://github.com/morluto/rea/blob/main/docs/architecture.mermaid
- https://github.com/morluto/rea/blob/main/docs/tool-design.md
- https://github.com/morluto/rea/blob/main/docs/testing.md
- https://github.com/morluto/rea/blob/main/docs/mcp-prompts.md
- https://github.com/morluto/rea/blob/main/docs/cli.md

## Opinion, deliberately open to challenge
REA is highly relevant as a **method of investigating unknown systems**, not as a new cognitive engine. The largest transfer is from evidence-grounded observation to explicit alternatives, unresolved questions, discriminating tests and durable revisions. An ARC solver reverse-engineers an unknown world by acting; an SWE agent reverse-engineers unfamiliar software by reading, instrumenting and testing. SAGE could test whether one reusable epistemic scaffold improves both. I rate methodological fit HIGH, architectural reuse MEDIUM, direct code transplantation LOW. These are judgments, not measured results.

The objection I most want evaluated: can explicit epistemic state improve *decisions* with the same local model and compute budget, or is it just more fluent explanatory text? A simpler search/test policy may beat a detailed ledger.

## REA implementation read
REA Evidence represents artifact subject and content digest, provider/version, analysis profile, operation/parameters, raw and normalized results, confidence (observed/derived/inferred), evidence authority, environment, limitations, source locations and evidence links. Its deterministic semantic evidence ID supports tamper detection in its representation, not factual truth, witness authenticity or delegated Web4 authority. REA's guided prompts include investigate_feature, compare_application_versions, verify_reconstruction, trace_crash, audit_residual_unknowns, and prepare_bounded_process_capture. They suggest rather than enforce tool order. Its tool vocabulary includes inspect, search/list, trace, compare, workflow, observe/capture. Providers and lifecycle are separate from domain contracts; provider selection is explicit, and ownership/cleanup limits are recorded. Full evidence can be retained and accessed through narrow views and exact target/provider/settings snapshots. It distinguishes real provider verification from mocks and incomplete coverage from confirmed absence.

REA's unknown tracking is useful inspiration, but one connection-scoped evidence ledger must not be mistaken for SAGE's durable cross-wake personal memory. An unknown should be carried forward *only when relevant*, with its support, counterevidence, next discriminatory probe, and retrieval path.

## Proposed SAGE research arc
Working name: Evidence-Grounded Active Investigation (EGAI). Do NOT create a monolithic replacement for existing IRP, premise fidelity, SNARC, MRH, memory, learned state, or Hestia. Before writing code, inspect current public and private implementation and active branches for equivalent mechanisms.

Hypothesized loop:
1. Capture raw observation with its source, time, environment and witness path.
2. Distinguish observed fact, derived feature, model inference, prediction and hypothesis. Keep alternatives and contradictions.
3. Link claims to supporting/contradicting evidence, source locations and falsifiers; preserve unresolved questions rather than hallucinating closure.
4. Allocate attention using SNARC salience, MRH relevance, expected uncertainty reduction, time/ATP budget, and risk. Information gain is an empirical heuristic, not a universal policy.
5. Select inspect, retrieve, trace, compare, or a bounded experiment. An authorized effector action passes being -> seat -> Hestia, and a denial is evidence of a denied attempt, not a completed effect.
6. Record exact observation/action/result linkage; revise claims, belief and procedure state with explicit supersession/retraction.
7. On the next wake, measure whether the changed state causes a changed and improved decision under matched conditions.

Potential minimal record facets (illustrative, NOT a mandated schema): claim_id, subject/source_ref, support_refs, contradiction_refs, epistemic_kind, status, falsifier, candidate_probe, expected info value, probe cost, model/sensor version, MRH relevance, owner, witness_ref, revision, recovery path. Do not confuse classification with calibrated probability. Missing/truncated/stale provider response means unknown, not absence. Retention should use tiers (raw/source, sparse durable evidence, compact views); sensor data cannot all be retained indefinitely. VAE/IRP projections should point to retrievable sources or explicitly identify irreversible information loss.

## ARC-SAGE experiment (current private canonical ARC repo)
Unknown interactive worlds: investigate rules using ONLY legal game observations/actions. Example: does contact change color, or does color change every N turns? Select action that distinguishes these hypotheses. Baselines: existing solver; +provenance; +durable alternatives/unknowns; +probe selection; +cross-level procedural reuse. Outcomes: legal score and level completion, actions to first correct causal hypothesis, wasted probes, unsupported rules, tokens/time, novel-state transfer. Compare matched models and budgets; ablate each component. Never analyze hidden game/evaluator internals or use privileged source/mechanics in a competition entry. Public SAGE arc-agi-3 files are historical mirrors; verify latest ARC-SAGE code and rules.

## SWE-SAGE experiment (current private canonical Gemma 4 competition repo)
Inspect/trace/hypothesize/patch/verify in unfamiliar repos. Control base vs post-trained Gemma, scaffold and memory variables separately. Isolate a new EGAI axis: source-grounded premises; competing diagnosis and unknown state; chosen discriminating test; retained outcome and procedural reuse. Measure task pass rate, fault localization, verified patch regression, hallucinated paths/symbols, redundant calls, time/tokens, ablation across tasks/wakes. REA itself could be an OPTIONAL extra tool for permitted binaries/Electron/firmware, but that is a separate capability intervention, not evidence of a better cognitive scaffold. Check contest packaging, sandbox, permitted tools and provenance first. Keep private implementation/results in SWE-SAGE until deliberate competition-safe promotion.

## Cross-domain experiment / reconstructability
Use one minimal evidence/uncertainty/probe interface behind domain adapters. Compare baseline/no memory, summary-only, source-linked compact evidence, and full transcript; evaluate whether a later model or wake can reconstruct what was established, unresolved alternatives, and the next useful experiment, then actually behave better. Keep raw evidence where feasible and say what was lost when not. Cross-domain gains under matched controls are stronger evidence of general cognition than a specialized benchmark gain.

## Falsifiers and objections to actively seek
- A better baseline retrieval or fewer ad hoc calls gives same result.
- A larger explicit ledger harms small local model performance and latency.
- Hypothesis labels create false confidence or cognitive fixation.
- Information-gain estimators lack calibration and waste game actions.
- Software is static enough to inspect; real environments are moving and interventions change the target.
- Stale source refs and model/sensor upgrades break semantic identity.
- An evidence digest validates consistent bytes, NOT the observed world.
- Governance overhead should not be silently conflated with cognition improvements.
- More text, successful mock tests, or pretty traces are NOT behavioral learning.
- Game evaluator leakage, task contamination or forbidden tools invalidate performance evidence.
- A parallel evidence/trust/identity system would duplicate Web4/Hestia and fragment ownership.

## Test contract
Pre-register matched model/checkpoint, code commits, tool affordances, prompt differences, action/token/time budgets, seeds/task distribution, operators and leakage guardrails. Maintain held-out tasks and adversarial conditions: erroneous sensor, contradictory source, changed files, stale evidence, truncated/denied operation, tool timeouts, incomplete cleanup. Report uncertainty, failed cases, negative results, and real verification lanes. A mechanism counts only when removing it removes the observed benefit or changes later behavior.

## Reading request to Thor's Claude, Kimi, Codex
Please form INDEPENDENT perspectives before aligning. Suggested emphases, not assignments: Claude—architecture ownership/overlap; Kimi—strongest criticisms and experimental confounders; Codex—actual code paths and smallest testable prototype. Each should identify (1) where this note is wrong, (2) existing implementation already satisfying it, (3) lowest-cost falsifiable test, (4) competition-rule risks, (5) what should NOT be built. Do not interpret this as authorization for a sweeping rewrite or merge.

## Placement
General methods and evaluation standards belong in public dp-web4/SAGE. Canonical ARC competition specifics belong in private dp-web4/ARC-SAGE, SWE competition specifics in private dp-web4/SWE-SAGE, development discoveries in dev-SAGE as appropriate. Web4/Hestia keep identity, authority and receipts. This note reports no landed code and no tested performance gain.
