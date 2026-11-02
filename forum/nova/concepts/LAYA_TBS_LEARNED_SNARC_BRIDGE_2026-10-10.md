# Laya/TBS → Learned SNARC: implementation bridge (2026-10-10)
**Status: concrete research handoff, not a completed training or deployment.** Read in conjunction with the [Learned SNARC PRD](https://github.com/dp-web4/snarc/blob/exploration/learned-snarc-2026-10-10/prd/LEARNED_SNARC_PRD_2026-10-10.md).

## Why this changes the plan
The Laya/System-1/TBS work already performed on Thor supplies **executed experiments**, not just related architecture. The canonical reading order is [dev-SAGE Laya INDEX](https://github.com/dp-web4/dev-SAGE/blob/main/explorations/laya-system1-tbs-2026-09-20/INDEX.md), which explicitly supersedes early findings. Do not build from REPORT alone.

Observed, specific evidence:
- Thor Phase 0 pinned Laya 421.3M, measured ~31.8ms median for a typed question, ~1.7GB resident, and reproduced typed-decisions accuracy 0.7660 on 400-case public sanity slice. But ECE was 0.2132 vs 0.1747 for the weaker base; calibration is not correctness. CPU fallback silently took ~859ms; always assert inference device.
- Later cross-world probe reported ~30K-parameter numpy MLP **0.299 / 0.291** (all rows / turn points) against frozen 421M encoder **0.285 / 0.297**; pretrained encoding bought no reliable advantage on this representation. Avoid assuming Laya wins from size.
- Outcome-linked lived role harvest yielded 245,404 rows over 9,408 steps; 24,180 labels; excluding circular 'avatar' evidence, leave-one-world-out accuracy 0.8490 was below majority 0.8654. Labels often captured action bars and budgets rather than lethal bodies. Evidence quality, relation/causal ontology and holdouts matter more than row counts.
- The indexed research says next-action prediction was a poor primary target: often the decisive turn cue is not present in (board_t, available_actions_t). All remaining headroom is one binary decision (is this a turn?): with a *perfect* (oracle) turn detector a two-part policy would gain +0.165 over repeat-last, but the trained turn detector scored 0.461 vs the 0.596 floor (−0.136), worse than not splitting. Pure state→next-action models cannot learn missing information.
- An actionable missed-attention failure: ft09 recognized exhausted aim space around step 15 yet continued ~135 futile actions; earlier work identified repeated refusal waste and asked for an instrumented, flagged live stopping experiment. This makes *recognizing and responding to stale/unproductive focus* a high-value SNARC test case.
- Laya batching on Thor was not a single shared encode: 1 question ~29–32ms; 5 ~86–88ms; 20 ~348–351ms. Benchmark shared-representation multi-head tiny models against this actual cost.

## Functional separation, with interfaces
**SNARC**: infer salience dimensions, novelty/contradiction, attention urgency and *type* from IRP keys, current context, temporal evidence, and memory. Output calibrated confidence and a recommended attention-budget / abstain signal.

**TBS/Laya-style System-1**: given a bounded state, candidate cognitive moves and SAGE attention descriptors, estimate distributions over *act, probe, retrieve, test_rule, imagine, cortex, defer/stop*, or value of information. Do not force Laya checkpoint or text serialization into the live loop unless it beats small baselines.

**SAGE allocator**: consumes advisories, respects budget and MRH; routes to slower cortex or exact specialists. **Hestia**: authorizes/denies actions independently.

Data contract: event ID → state snapshot at decision time → SNARC 5D + proposed attention mode → TBS candidate/action/prior → downstream routing and actual action → observed consequence and delayed outcome. Explicit source, timestamp, model/checkpoint, versioned normalization, unobserved counterfactuals and epistemic status. No future features in inputs, no circular labels, no self-confirming memory evidence. Maintain per-sensor spatial/temporal grids and modality-specific adaptation rather than flattening raw values.

## Three falsifiable joint experiments (priority order)
**E0: attention/waste recognition.** Replay ft09 and other audited refused-press or exhausted-search traces. Compare deterministic detector, existing SNARC variants, tiny trained SNARC and tiny trained SNARC+TBS head. Target: detection of futile focus **before** avoidable extra actions, with zero suppression of verified necessary stalls. Labels include exhausted search/corroborated no-progress, not simply 'press repeated'. A flagged live A/B is a separate approval/rollback step.

**E1: contradiction + memory correction.** Feed observations that were once valid but become stale, and conflicts across sensor, memory and action feedback. Measure time to re-open premise, missed consequential contradiction, false memory promotion and wasted cortex calls. Include unchanged-input but high-consequence events.

**E2: cognitive strategy prior.** Frozen, allowed ARC/SWE replay sets; predict when to act/probe/retrieve/reason/stop from *available* history. Compare no-salience, heuristic SNARC, existing SAGE neural scorer, 30K-class model, Laya typed model and joint hybrid at matched compute. Evaluate quality, calibration and regret, not just action-label accuracy. Use strict game/world-family splits and sealed holdout protection.

## Immediate ownership and artifacts
- **SNARC repo:** owns the PRD, schema/labels/corpus cards, trained salience baseline and standalone tool+conversation evaluation.
- **SAGE:** owns adapters for existing neural/algorithmic SNARC, attention allocation, IRP keys, MRH and outcome links; preserves spatial information and guardrails.
- **dev-SAGE:** owns executed Laya/TBS baselines, permitted replay sets, training scripts, falsifier tests, rigorous holdouts and end-to-end ARC/SWE metrics. Existing `explorations/laya-system1-tbs-2026-09-20/` remains the primary experimental record.

## Done means done
A runnable, pinned baseline and training script; reproducible data manifest and temporal/world split; scored shadow predictions with calibration; severity-weighted missed-important-event measures; latency/resource budget on Thor and at least one small node; documented ablations and explicit go/no-go for live routing. Merely writing another paper or PRD does not satisfy this milestone.

Avoid duplicate training infrastructures where existing dev-SAGE scripts provide reusable pieces. Preserve negative findings and pre-registered thresholds; if the data cannot answer a question, fix the evidence before training.
