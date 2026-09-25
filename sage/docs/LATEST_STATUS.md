# SAGE Current Status

**As of:** 2026-09-24  
**Snapshot basis:** public `main` through documentation refresh `a8461d5`

This is the **current-status landing page**, not a session chronicle. It is intentionally short, dated, and falsifiable. Detailed raising histories, experiment analyses, instance records, PRs/issues, and git history remain the evidence of record.

## Current direction

SAGE is converging from a broad cognition/research harness into a fleet of persistent **beings** whose identity, memory, procedures, learned state, and actions survive beyond one model call or model process.

The current action boundary is:

```text
being intent
  -> bounded SAGE gateway vocabulary
  -> installed Hestia law / society safety
  -> allowed dispatch
  -> witnessed result
  -> later memory / belief / behavior
```

The being does not receive a raw shell or unrestricted filesystem through the canonical gateway. Consequential acts are intended to be governed and witnessed; observational/local capabilities are separately bounded.

In parallel, active private `dev-SAGE` research is moving more of the behavioral gradient from human/fleet source-code edits into **trainable behavioral state** around a frozen/slow frontal-lobe model. That is active research, not yet a public-main capability claim.

## What is live on public `main`

- **Governed being gateway.** `BeingGateClient` maps a bounded intent vocabulary into installed Hestia law and fail-closed dispatch.
- **Separated intent/action shape.** The being asks; the harness/gateway holds the effector. This is A2-shaped, while principal/substrate separation is still being hardened.
- **Persistent conversations and memory.** Being/seat exchanges, local files, long-term memory, and witnessed acts persist beyond one inference.
- **Evidence-bearing receipts.** Recent fixes ensure important boundaries say what actually happened rather than forcing a small model to infer it: append vs. edit, visible truncation, same-beat act results, stale/unchanged run requests, and refusal diagnostics.
- **Fleet research remains multi-model/multi-machine.** Instance artifacts and automated raising/probe commits continue to land; those records are operational evidence, not universal behavioral claims.
- **Python/Rust distinction is explicit.** The Rust daemon is an inference/metabolism/federation gateway, not a semantic port of every Python cognition-loop component. See `RUST_VS_PYTHON_CAPABILITY.md`.

## High-value work in flight

As of this snapshot, the active edge is less about adding conceptual modules and more about making persistent agency **epistemically and operationally legible**:

1. **Feedback-surface correctness.** A refusal, truncation, edit miss, successful act, or stale request must expose enough factual evidence for the being to correct itself rather than confabulate completion.
2. **Being/seat principal separation.** Naming two actors is not enough; cryptographic and OS-level separation must make route-around meaningfully harder.
3. **Request/action identity.** Requests, answers, executions, and witnessed results need durable linkage so unrelated later messages cannot accidentally close or satisfy earlier intent.
4. **Survivable experimentation.** The being should be free to be wrong repeatedly while the attending seat constrains irreversible consequences.
5. **Learned behavioral state.** Active `dev-SAGE` work is testing fast learned decision substrates, calibration, and behavioral causality around a slower cortex.
6. **Longitudinal memory controls.** A clean comparison of selective memory/retrieval against brute-force long-context baselines remains worth doing.
7. **Belief correction.** Provenance is strong; contradiction/supersession/retraction of derived beliefs should become as explicit as evidence capture.
8. **Premise fidelity.** Source-checkable claims about what a being saw, heard, read, or received should remain bound to recoverable evidence before they are promoted into durable facts. The current refinement is relation-first and reconstructible: preserve the explicit source→claim support relation, uncertainty/falsifier where material, and enough provenance that a later substrate can reconstruct why the premise was licensed. Semantic Closure Horizon (SCH) is a useful progressive-evidence research lens; vector similarity/confidence is not a support verdict. See `PREMISE_FIDELITY.md` and `PRD_SOURCE_GROUNDED_PREMISES.md`.
9. **State-conditioned agency.** Persistent beings may carry endogenous/metabolic state across interactions, including suffering-like, failure-related or self-evaluative states that alter later policy. Phenomenology is treated as a first-class observation under substrate-symmetric evidence standards; neither automatic promotion nor automatic dismissal is acceptable. See `STATE_CONDITIONED_AGENCY.md`.\n10. **External SWE ablation.** [SWE-SAGE](https://github.com/dp-web4/SWE-SAGE) is the public Gemma 4 software-engineering-agent experiment surface. It is designed to separate the contribution of post-training, persistent state, source-grounded premises and governed execution on a common task distribution rather than treating a leaderboard score as an architectural explanation.

The large `legion/mission-artifact` PR remains a reconciliation/nursery branch; narrow independently reviewable slices continue to be preferred for canonical main.

## Important caveats

- **A2 is a target/enforcement shape, not yet an unconditional substrate claim.** The being emits intent while a separate harness holds effectors, but principal and relying-party isolation still have transitional gaps. Do not describe the deployed fleet as adversary-proof containment.
- **No OS/kernel sandbox claim.** Stronger separate principals, capability isolation, hardware roots, and eventual kernel participation remain roadmap work.
- **Branches are not deployed truth.** A machine may temporarily run branch code; that must be named in its instance/session evidence.
- **A commit proves repository state, not machine state.** "Deployed," "healthy," "restarted," or "ran successfully" require runtime evidence.
- **Research findings are contextual.** Preserve model, prompt/scaffold, commit, hardware, and experiment window. Do not promote one raising observation into a fleet-wide property.
- **Mechanism is not capability.** A module present in source counts only when it participates in the live decision path and the claimed effect survives appropriate controls.
- **Public main is not the whole research program.** Active private work may be ahead of public main; private experiments are not thereby public capability.

## Terminology guardrail

**MRH = Markov Relevancy Horizon.**

It is a context/relevance boundary, not "Multi-Resolution Hierarchy." Historical documents sometimes put MRH next to "fractal" or "multi-resolution" language; those phrases describe abstraction/navigation, not the acronym.

The useful current framing is:

> MRH is a witness-relative contract over which distinctions still matter for the present question.

See `forum/insights/mrh-relevance-contract.md`.

## Where to look for truth

| Question | Source of record |
|---|---|
| What is the current project thesis? | root `README.md` |
| What code is canonical? | public `main` and merged PRs |
| What work is in flight? | open PRs/issues and named private research arcs |
| What did a being actually experience? | `sage/instances/<instance>/` artifacts and witnessed conversation/action records |
| What happened in an experiment? | its prereg/config + data/results + analysis |
| What law governed an action? | installed Hestia law plus witness/decision record |
| What does the Rust daemon actually implement? | `RUST_VS_PYTHON_CAPABILITY.md` |
| How does endogenous/metabolic state affect longitudinal agency? | `STATE_CONDITIONED_AGENCY.md` |\n| What is the public SWE-agent benchmark experiment? | [SWE-SAGE](https://github.com/dp-web4/SWE-SAGE) and `SWE_SAGE.md` |
| What was historical architecture/status? | dated docs, `docs/history/`, `archive/`, git history |

## Documentation rule

A cold evaluator should begin with:

1. `README.md`
2. this file
3. `AGENTS.md`
4. `repo-index.yaml`
5. claim-specific current evidence

`docs/why/HRM_EXPLAINED.md` and `SYSTEM_UNDERSTANDING.md` are explicitly retained as historical architecture records. They must not silently outrank newer evidence.

A file named **status**, **current**, or **latest** must carry a concrete date. If a fact changes too quickly to maintain accurately, point to its evidence source instead of freezing a number here.
