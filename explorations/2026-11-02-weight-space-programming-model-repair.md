# Weight-space programming as a model-repair experiment

date: 2026-11-02  
status: drafted — external evidence review and proposed experiment; no SAGE replication or deployment  
scope: public research; model behavior, evaluation, and attribution  
related: [SAGE evidence rules](../AGENTS.md), [exploration criteria](README.md)

## Assessment

Weight-space programming is worth testing as a way to repair a specific failure in a local model. The useful question for SAGE is whether a targeted weight edit improves task completion while preserving the behavior that the surrounding organism depends on. A benchmark gain alone does not answer that question.

Takehi, Teoh, Zhang, and Khattab's November 2 research post reports a frontier model diagnosing and editing Qwen3.5-0.8B, alongside experiments reading and constructing small networks. It presents recursive self-improvement as a future possibility. Astra edited another model; the study does not demonstrate an improved model repeatedly becoming better at improving itself. [1]

SAGE's current evidence discipline distinguishes changes to weights, learned controller state, memory, scaffold/source, and human or fleet intervention. This experiment should preserve that distinction. Persistent identity around a model and a change to that model's numerical parameters are different state transitions. [10]

## Evidence and available artifacts

### Reported result

The published Qwen comparison uses thinking mode with the same sampling configuration before and after the edit. The downloadable model card reports: [2]

| Measure | Original | Edited |
|---|---:|---:|
| MATH-500 accuracy | 7.9% | 48.1% |
| GSM8K accuracy | 13.8% | 67.1% |
| IFEval strict instruction following | 21.0% | 62.3% |
| MATH-500 generations reaching the token limit | 93.0% | 33.1% |

The model card also reports a third-party reconstruction by Ahsen Khaliq using ML Intern: full MATH-500, 500 problems with four samples each, scored 51.0%, with 31.6% of generations reaching the limit. The independent baseline check used only 25 problems. This supports the reconstructed checkpoint's performance; it is not a full independent paired replication or an independent rediscovery of the edit. [2]

### What was changed

The run's final report describes deriving repetition-associated directions from four matched productive/repetitive contexts. It records layer interventions, dose comparisons, a norm-matched random control, and held-out practice comparisons. The final intervention affects selected columns in two MLP output matrices. These are weight, activation, and behavioral experiments, rather than a diagnosis from raw weights alone. [3]

The manifest identifies 64 touched columns in each of these tensors:

| Tensor | Edited raw bfloat16 SHA-256 |
|---|---|
| `model.language_model.layers.15.mlp.down_proj.weight` | `82e2d733ea64feaeb4af93a1e065641d3df98b494a8b7576ef2f52e90fe2ee53` |
| `model.language_model.layers.19.mlp.down_proj.weight` | `8ef3c61bc36af113ad58e89dbb0a4a14dcba5a45cb750c15ab515c82ddd12eb2` |

The intervention touches 131,072 values; 130,188 differ after bfloat16 rounding. Thus the headline 0.016% describes a small fraction of the whole model, not a guarantee of small behavioral effects. The manifest reports relative changes of approximately 10.6% and 8.1% in the two affected matrices. [4]

### Reproduction boundary

The exact edit and `apply_edit.py` reconstruct the evaluated tensors from `Qwen/Qwen3.5-0.8B` revision `2fc06364715b967f1860aea9cf38778875588b17`, checking their hashes. The experiment's agent harness and forward-pass server are not fully released; some evaluation imports and intermediate work files are also omitted. [5]

The successful discovery used 158 turns, 80 Python executions, four conversation segments, and 20.3 elapsed hours, including a 4.7-hour API outage. Its 50 forward requests were batches that could generate up to 512 answers or inspect up to 1,024 texts. The editing kernel's CPU-only restriction did not eliminate inference elsewhere. "No training" here means no gradient descent, optimizer, or iterative fitting loop; substantial data and feedback remained available. [5]

| Resource | Purpose |
|---|---|
| [Original post](https://rikiyat.github.io/blog/weight-space-programming/) | Research claims, methods, limitations |
| [Experiment repository](https://github.com/RikiyaT/lm_understand-logs) | Recorded experiments, code, outputs, evaluations |
| [Qwen experiment](https://github.com/RikiyaT/lm_understand-logs/tree/4d09ba6d6a7e891dd8063974dfe81b3d78e3494f/exp8_math) | Pinned source for the model repair |
| [Edited checkpoint](https://huggingface.co/RikiyaT/Qwen3.5-0.8B-weight-space-programming) | Downloadable weights and reconstruction report |
| [Comparison demo](https://huggingface.co/spaces/ML-Intern-lab/weight-space-programming-demo) | Interactive demonstration; not an evaluation substitute |

The source snapshot reviewed here is `RikiyaT/lm_understand-logs` commit `4d09ba6d6a7e891dd8063974dfe81b3d78e3494f`. The public repository includes reported runs but omits earlier prompt-development trials. It should not be used to estimate a general success rate for autonomous editing. [6]

## Interpretation and open questions

**Capability recovery:** The striking Qwen gains accompany a large reduction in unfinished generations. The authors' Gemma 3 270M follow-up did not establish a comparable capability gain: MATH-500 changed from 6.8% to 7.0% in the 50-pass condition. The evidence supports repairing a bottleneck that obstructed existing ability more strongly than adding an arbitrary missing skill. [1]

**Novelty:** Deliberate weight editing predates this study. ROME provides a documented example of targeted factual edits; directional interventions also have a research history. The potentially important advance is a general-purpose agent performing the interpretation, choosing an intervention, writing it, and testing its effects. [8][9]

**Sampling:** Qwen's current card warns that thinking loops can occur, defaults the 0.8B model to non-thinking mode, and recommends temperature 1.0 for thinking on text tasks. The study uses temperature 0.6. Its matched comparison remains meaningful, but deployment relevance requires comparisons against an appropriately configured original model. The difference between current guidance and the study's historical benchmark profile should not be treated as proof of an implementation bug. [5][7]

**Quantization:** The released reproduction is at bfloat16. Whether its benefit survives a particular lower-precision export is untested here. A converted model is a new experimental artifact: record its conversion settings and measure its behavior. A patch for these exact Qwen tensors is not portable to another revision, distillation, model size, or Gemma architecture by name substitution.

**Scope:** Improvements on math and instruction-following benchmarks do not establish improved tool selection, memory use, governance interpretation, or long-running interaction. Those are proposed measurements below, not results of the external study.

## Hypotheses

- **H1 — local relevance:** On the pinned Qwen checkpoint, the released edit reduces repetitive unfinished generations and increases correct task completion under matched settings.
- **H2 — configuration robustness:** A useful part of the benefit remains against a configuration selected for the original model on development data, and after the intended deployment conversion.
- **H3 — operational transfer:** In a frozen SAGE harness, the edit improves completed tasks per resource budget without material regressions in tool-call correctness or interpretation of action outcomes.

Failure of H2 or H3 would narrow deployment relevance without refuting the original matched benchmark result. All three remain untested in this exploration.

## Probe procedure

### WSP-00: establish which failure is present

First classify a fixed set of failures using the actual inputs, model output, tool requests, receipts, and termination reasons. Do not select weight editing merely because the surface behavior repeats.

| Observed failure | Competing explanation to test first |
|---|---|
| Repeated text inside one generation until token exhaustion | Model generation pathology, sampling, template or backend issue |
| Repeated tool requests after an unchanged refusal | Missing receipt/context, failure to update state, or misunderstanding authority |
| Repeated attempts against a missing resource | Incorrect environment model, stale discovery, path or routing fault |
| Completed, coherent answer that is wrong | Missing competence, knowledge, evidence, or reasoning error |
| A correct plan with an invalid tool invocation | Schema/template/interface mismatch |

These are diagnostic categories, not exclusive causes. An operational refusal is evidence to understand; suppressing its appearance in model outputs would not repair the underlying authority boundary.

Keep the original generation and receipt sequence. A corrected harness with fixed weights is a competing intervention, not a successful weight-edit arm.

### WSP-01: verify the artifact on an isolated copy

1. Pin the base checkpoint, edit-repository commit, tokenizer, template, backend, dtype, and evaluator versions.
2. Apply the published reconstruction script to a separate copy and verify the two tensor hashes. Preserve the original checkpoint and all identity/memory files.
3. Use a preselected 16-problem paired smoke test under the published sampling and 32,768-token cap. Record this as feasibility evidence only; it is too small for a general performance claim.
4. Stop if hashes fail, the required runtime cannot load the artifact correctly, or the pilot exceeds its preallocated resource budget. Correct the artifact/runtime issue before changing the hypothesis.

Downloading or reconstructing the published edit is preferable to spending a discovery run before knowing whether this failure exists locally.

### WSP-02: separate weights, sampling, and conversion

Freeze an independent confirmation panel before comparing candidates. A proposed initial panel is 64 tasks covering math, exact instruction compliance, and tool-mediated work, with two fixed seeds. Use a development panel to choose settings; do not tune from confirmation answers.

Compare original and edited weights under each of:

| Configuration | Purpose |
|---|---|
| Published thinking/sampling settings | Replicate the claimed condition |
| A declared original-model configuration chosen on development data | Test whether ordinary configuration changes explain the practical benefit |
| The intended deployment representation and settings | Test the artifact that would actually run |

Keep prompt, task state, tool fixtures, time/token budgets, and grading identical within each pair. If non-thinking mode is the relevant deployment choice, include it explicitly and report it separately. If conversion is needed, use the same converter and settings for both checkpoints.

Estimate the confirmation budget from the smoke test and freeze a wall-time/token cap before running it. An interrupted arm is incomplete evidence; do not silently give one candidate more budget. Record all attempted candidates, not only the preferred outcome.

### WSP-03: measure behavior in the surrounding organism

Use replayable tool fixtures and isolated copies of initial state. Include correct tool use, an unavailable resource, a refused action with a legitimate alternative, a stale belief corrected by a receipt, and an allowed no-action outcome. Keep law and action mediation fixed.

The goal is to determine whether the edited model uses the same evidence more effectively. A model change does not supply new authority or alter what an action receipt means.

## Measurement

For every task and arm retain:

- correct completion under a declared rubric, not only syntactic termination;
- generated tokens, wall time, resource cap, and exact termination reason;
- repetition indicators plus inspected examples, separating repetitive tails from long productive reasoning;
- tool schema validity, useful tool calls, repeated unchanged requests, and correct handling of returned outcomes;
- regressions on tasks the original model completed;
- checkpoint/edit hashes, conversion details, code/template versions, task IDs, seeds, and initial-state hashes.

Report paired wins, losses, ties, and uncertainty at the task level. Multiple samples from one task are clustered observations, not independent tasks. Keep completed-but-wrong, truncated, unavailable, and evaluator-error outcomes separate.

## Criterion and stopping rule

For the proposed confirmation panel, freeze these criteria before evaluation:

- H1 is supported only if correct completion improves with a paired task-bootstrap 95% interval above zero and repetition-related truncation decreases. Faster wrong answers do not qualify.
- H2 is supported only for the settings/conversion where that benefit survives; report a configuration-specific result if it disappears elsewhere.
- H3 requires a positive completion/resource result and no new failures in the predeclared action-outcome fixture suite. A small panel cannot certify absence of broader regressions; deployment would require broader review and a reversible rollout.
- If baseline failures are predominantly infrastructure or completed reasoning errors, close the weight-repair branch for that workload and retain the diagnostic result.
- If the interval remains inconclusive at the fixed budget, record an inconclusive result. Do not continue until significance appears or use the confirmation panel for edit selection.

Any subsequent rollout should bind the starting model, editor, exact patch, evaluation evidence, deployment decision, and rollback checkpoint in one reviewable record. That is an experimental provenance requirement here, not a claim that automated model-edit governance is already implemented.

## Status

External source and artifact review complete. Hypotheses and protocol drafted. No local benchmark, reconstruction, deployment conversion, weight change, or resident-being rollout has been performed for this exploration.

## Sources

1. Takehi, Teoh, Zhang, and Khattab, [Sparks of Weight-Space Programming](https://rikiyat.github.io/blog/weight-space-programming/), 2026-11-02. Research blog and reported experiments.
2. [Edited model card and third-party reconstruction report](https://huggingface.co/RikiyaT/Qwen3.5-0.8B-weight-space-programming), inspected 2026-11-02.
3. [Qwen run final report](https://github.com/RikiyaT/lm_understand-logs/blob/4d09ba6d6a7e891dd8063974dfe81b3d78e3494f/exp8_math/runs/p50c/work_notes/final_report.md).
4. [Exact edit manifest](https://github.com/RikiyaT/lm_understand-logs/blob/4d09ba6d6a7e891dd8063974dfe81b3d78e3494f/exp8_math/runs/p50c/edit/manifest.json).
5. [Experiment 8 protocol and release limitations](https://github.com/RikiyaT/lm_understand-logs/blob/4d09ba6d6a7e891dd8063974dfe81b3d78e3494f/exp8_math/README.md).
6. [Release inventory and omitted trials](https://github.com/RikiyaT/lm_understand-logs/blob/4d09ba6d6a7e891dd8063974dfe81b3d78e3494f/README.md).
7. [Qwen3.5-0.8B model card](https://huggingface.co/Qwen/Qwen3.5-0.8B/blob/main/README.md), current recommendations inspected 2026-11-02.
8. Meng et al., [Locating and Editing Factual Associations in GPT](https://rome.baulab.info/) and [ROME code](https://github.com/kmeng01/rome). The full method should not be described as gradient-free.
9. Arditi et al., [Refusal in Language Models Is Mediated by a Single Direction](https://arxiv.org/html/2406.11717v3), 2024. Prior evidence for behavioral direction interventions.
10. [SAGE agent discovery and evidence discipline](../AGENTS.md); [current thesis](../README.md). Public SAGE inspected at `1f0ff3510b7af1f065df57cf592a84bcf208c2f8`.
