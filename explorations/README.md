# Explorations

Interpretive experiments, reproducibility tests, and methodological probes that are NOT part of the main engineering work but ARE part of how we calibrate it.

## What an exploration is

An **exploration** is a low-cost, falsifiable experiment whose purpose is to determine whether an observation about SAGE is a property of the *system* or a property of the *probe*.

Engineering deliverables answer "does this work?" Explorations answer "does our description match what's actually happening?" — which is a different question and a separate failure mode.

Most explorations live in the gap between "we noticed something interesting in raising sessions" and "we have empirical scaffolding for this claim." They're the bridge between observation and finding.

## Format

Each exploration is a markdown file with:

1. **Hypothesis** — the specific claim we're testing
2. **Probe procedure** — exactly what gets run (prompts, seeds, model, conditions)
3. **Measurement** — what gets recorded and how it gets scored
4. **Criterion** — what would change our interpretation if we saw it
5. **Status** — drafted / running / results / closed (with conclusion)

The criterion is the most important field. An exploration without a falsifier is just an opinion in markdown.

## Index

| Exploration | Status | Tracks |
|-------------|--------|--------|
| [2026-10-06-compiled-transducers-sensors-effectors.md](2026-10-06-compiled-transducers-sensors-effectors.md) | Drafted, ready to run | Hardware-shaped execution across learned sensors/effectors |\n| [2026-05-15-sprout-oscillation-seed-sweep.md](2026-05-15-sprout-oscillation-seed-sweep.md) | Drafted, ready to run | Three-mode probe reproducibility |
| [codification-project-2026-04-25/](codification-project-2026-04-25/) | Prior exploration (Apr 2026) | (legacy — historical context) |

## Why this directory exists

External review (Kimi 2.6, 2026-05-15) observed: *"LLMs are excellent at generating coherent frameworks and less excellent at recognizing where coherence becomes speculation."* SAGE's documentation is substantially AI-assisted, which means this failure mode is structurally present in our written record. The explorations/ directory is the operational counterweight — every interpretive claim in the main repo should eventually point to (or generate) an exploration that could falsify it.

A claim with no associated exploration is, by default, an observation or framing — not a finding. (See SAGE README → "Findings vs Framings.")
