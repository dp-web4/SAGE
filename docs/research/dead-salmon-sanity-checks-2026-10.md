# Interpretability sanity checks for SAGE: SNARC, LAYA, memory and identity

Source: https://arxiv.org/abs/2512.18792 (The Dead Salmons of AI Interpretability, 2025). This is an adaptation of methodological lessons, not a claim that the paper experimentally validates our architecture.

Core distinction: behavioral observation != causal explanation != normative governance judgment. Interpretability evidence must specify target question/distribution, admissible explanation class, disagreement/validation metric, and null controls. Randomization controls are necessary sanity checks, never proofs of a uniquely identified mechanism.

## Priority
Methodology adoption, **not** a generalized interpretability subsystem or architectural redesign. Prioritize reusable evaluation protocol; SNARC/LAYA first, persistent-memory mechanisms second.

## Hypotheses and estimands
H1: learned salience improves held-out task outcomes over capacity/compute-matched controls. H2: the *assignment* of salience matters, not merely extra compute or retention. H3: gains survive distribution shifts. H4: measured continuity depends on recoverable memory/state, not merely identity strings or prompt leakage.

Define task families and sampling distribution before tuning; keep model weights, token budgets, tool access, seeds, latency envelope, and instrumentation consistent. Report uncertainty across tasks/seeds and effect size, not just best score. Preserve immutable run manifest (code revision, checkpoint hash, model, policy version, seed, dataset split, wall-clock/compute).

## Experiment matrix
| Condition | Question |
|---|---|
| Trained SNARC/LAYA | Treatment against explicit baseline |
| Randomized parameters, same topology | Is advantage architectural/compute-only? |
| Shuffled salience labels across matched events | Do specific rankings matter? |
| Salience disabled, retention/compute matched | Is mechanism necessary for performance? |
| LAYA associations permuted, preserving frequency | Do learned associations matter? |
| No memory, intact episodic memory, intact identity only, identity+episodic; replay shuffled | What sustains behavioral continuity? |
| Held-out novel environments, shifted distractors/rewards | Does effect generalize beyond artifacts? |

Metrics: task success, reward or ARC accuracy as applicable, sample efficiency, recovery after interruption, continuity on previously committed work, calibration of salience predictions, attribution stability, token/energy/latency and regression rate. Compare paired seeds/splits, report confidence intervals and negative results. Label mechanisms as correlated, intervention-supported, or unresolved; do not conflate behavioral persistence with proof of any singular identity mechanism.

## False positive defenses
- Pre-register primary outcomes and minimum effect; perform multiple-comparison correction when searching many probes/features.
- Include randomized models AND permutation baselines; repeat across independent seeds and environmental shift.
- Control for additional context, feature dimension, training exposure, compute, and memory footprint.
- Intervene on candidate representations; test redundancy by ablating individual and combined components.
- Track evidence/assumption limitations explicitly; a clean control comparison does not yield a unique neural explanation.

## Execution / acceptance
1. Collect existing SNARC, LAYA and being experiment entrypoints and baseline manifests without rewriting them.
2. Add small shared harness around the existing runner (if compatible), supporting reproducible permutations/ablation switches and frozen eval suites.
3. Pilot two task families with at least several seeds and held-out splits; publish effect and resource costs.
4. Extend to memory/continuity only when confounds and evaluation outcomes are explicitly specified.

Acceptance: reproducible manifests, treatment and null conditions runnable end to end, confidence intervals, documented confounds, and negative-result reporting. No production gate behavior changes in this exploration.

## Cross-references
See Web4/Hestia evidence-vs-inference research and dev-SAGE causal-ablation methodology (same source).