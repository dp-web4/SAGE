# Public SAGE Repository Health Audit

**Date:** 2026-08-28  
**Scope:** `dp-web4/SAGE` at `2a4a393939ce6e220457db126398c101654bbf96`  
**Purpose:** Give maintainers and Claude a concrete, reviewable repair queue after a fresh independent audit.

## Executive assessment

Public SAGE is active, substantive research software. Its strongest current work is in raising continuity, Sprout embodiment, persistent identity, constrained agency, Hub citizenship, and fleet experimentation. It should be evaluated as a parallel public system, not as a reduced mirror of private dev-SAGE.

The primary risk is now repository legibility and verification. Multiple documents disagree about the current system; the configured Python test suite cannot be collected safely in a normal development installation; tracked Python files contain syntax errors; the Python and Rust “consciousness loops” are not semantically equivalent; and an important identity anchor correction remains open.

This audit intentionally distinguishes:

- operational activity from measured learning,
- architecture framings from demonstrated findings,
- public SAGE scope from private dev-SAGE scope,
- local static verification from live fleet claims.

## Priority findings

### P0: Review and resolve PR #30, achieved anchor vs requested anchor

Current `main` still constructs the Python identity manifest, trust ceiling, attestation, and signing context from the anchor requested by the caller:

```python
self._seal_secret(identity_secret, anchor_type)
...
anchor_type=anchor_type
trust_ceiling=TRUST_CEILINGS.get(anchor_type, 0.4)
```

Hardware sealing paths remain TODO/fallback paths. This can allow a caller to request a strong hardware anchor while the provider achieves software sealing, yet publish the requested anchor and its higher trust ceiling.

PR #30 reports a cross-language fix that records the anchor actually achieved. Review its derivation/relocation assumptions, test it against pre-fix behavior, and either merge it or replace it immediately. Do not leave the current claim/holding mismatch unresolved.

Acceptance:

- [ ] Manifest records achieved anchor, not requested anchor.
- [ ] Trust ceiling derives from achieved anchor.
- [ ] Attestation and signing context use achieved anchor.
- [ ] Every requested anchor either writes a valid sealed secret or fails closed.
- [ ] Python and Rust derivation/relocation behavior is explicitly aligned or versioned.
- [ ] Regression tests fail against the pre-fix implementation.

### P0: Make the declared pytest suite safe to collect

`pyproject.toml` declares:

```toml
[tool.pytest.ini_options]
testpaths = ["sage/tests"]
```

A fresh `pip install -e '.[dev]'` followed by `pytest sage/tests -q` does not reach normal execution. Model and hardware scripts perform work during module import and call `sys.exit(1)`, causing pytest internal collection errors. Examples encountered include:

- `sage/tests/test_full_huggingface_model.py`
- `sage/tests/test_full_model_direct_import.py`

The same tree contains CUDA probes, Hugging Face model loads, Ollama calls, subprocesses, thermal/power qualification scripts, and ordinary unit tests.

Acceptance:

- [ ] No pytest module performs model loading, hardware probing, network access, or process exit at import time.
- [ ] Split ordinary tests from hardware qualification, benchmarks, and experiments.
- [ ] Suggested physical lanes: `tests/unit`, `tests/integration`, `tests/hardware`, `benchmarks`, `experiments`.
- [ ] Default `pytest` completes on a CPU-only development machine.
- [ ] Hardware/model tests are opt-in through explicit markers or commands.
- [ ] Add a CI collection gate before any expensive test jobs.

### P0: Add a syntax gate and repair tracked syntax errors

`python -m compileall -q sage` found four tracked syntax errors:

- `sage/quantization/investigate_q3omni_forward.py`: unterminated triple-quoted string
- `sage/tests/test_nemotron_vs_q3omni.py`: invalid nested f-string escaping
- `sage/tests/test_qwen3_omni.py`: unterminated triple-quoted f-string
- `sage/training/epistemic_stance_generator.py`: invalid `from dataclasses import dataclass, as dict`

Acceptance:

- [ ] All tracked Python source compiles.
- [ ] CI runs `python -m compileall -q sage`.
- [ ] Rust CI runs formatting and tests/build for the workspace.
- [ ] Syntax-only validation remains independent of GPU/model availability.

### P1: Establish one authoritative current-status surface

Current documents disagree on basic system facts:

| Topic | Conflicting repository claims |
|---|---|
| Version | `0.4.0a3`, `0.4.0a5`, and `0.4.0a6` |
| Loop | 9 steps and 12 steps |
| Fleet | 2 active machines, 6 machines, or 7 machines |
| Instances | 11 or 12 |
| Raising volume | 466+, 567+, or 1,400+ sessions |
| Federation | built but off, versus real active mesh |
| Sensors | mocked, despite Sprout's live embodiment stack |

Examples:

- `pyproject.toml` packages `0.4.0a5`.
- Runtime `sage.__version__` and `CLAUDE.md` report `0.4.0a6`.
- The README tool section reports `0.4.0a3`.
- `SESSION_FOCUS.md` was generated 2026-04-04.
- `STATUS.md` was last updated 2026-03-06.
- `sage/docs/LATEST_STATUS.md` was last updated 2026-06-12 and is primarily a chronological research journal.
- `fleet.json` lists seven machines but has null `last_seen_at` values.

Acceptance:

- [ ] Choose one canonical, generated current-status document.
- [ ] Generate fleet/model/session facts from manifests and instance state where possible.
- [ ] Put timestamps and source provenance beside generated facts.
- [ ] Treat historical journals as history, not competing current status.
- [ ] Make stale documents clearly archival or remove their “read first/current” role.
- [ ] Use one version source for packaging, runtime, and documentation.

### P1: Document Python/Rust semantic parity honestly

The Python kernel and deployed Rust daemon are both called a consciousness loop, but they do not implement equivalent cycles.

The Python `SAGEConsciousness.step()` includes sensor gathering, SNARC, metabolism, trust posture, plugin selection, ATP allocation, plugin execution, trust learning/decay, memory updates, imagination rollout, policy evaluation, posture restriction, effect dispatch, and validation logging.

The Rust daemon currently implements a slimmer message path: observation derivation, SNARC scoring, metabolism, Ollama generation, experience capture, fleet monitoring, and shadow-metabolism experiments.

The Rust cutover is operationally valuable, particularly for memory footprint and startup time, but it is not merely the same loop in another language.

Acceptance:

- [ ] Publish a Python/Rust capability-parity matrix.
- [ ] Name the canonical production runtime and the research/reference runtime.
- [ ] State which Python loop semantics are intentionally absent from Rust.
- [ ] Define what repository claims such as “deployed consciousness loop” mean.
- [ ] Add parity tests for any behavior claimed to be equivalent.
- [ ] Update `sage-rs/CUTOVER.md` to make semantic reductions prominent.

### P1: Correct dependency and environment declarations

The `dev` extra currently includes only pytest and pytest-asyncio. Tests and shipped modules expect additional undeclared dependencies.

Observed examples:

- Federation test collection requires `cryptography`.
- Context-classifier tests require `scikit-learn`.
- Model scripts require Transformers/Torch stacks but are collected by default.

A curated CPU-oriented run excluding the collection-breaking files produced 104 passes, 10 failures due to missing scikit-learn, and four pytest warnings for tests that return objects rather than assert.

Acceptance:

- [ ] Define minimal runtime, unit-test, federation, GPU/model, embodiment/Jetson, and full-research dependency groups.
- [ ] Each documented environment has one reproducible install/test command.
- [ ] Optional components fail with actionable messages without breaking unrelated test collection.
- [ ] Test groups declare the extras they require.
- [ ] Build and smoke-test the wheel in CI.

### P1: Update public claims about embodiment and fleet evidence

The README’s “Sensors mocked” statement is stale for Sprout. `sage/embodiment/README.md` documents dual IMX219 cameras, IMU, audio, TensorRT/YOLO object detection, a live visual cortex, presence, gaze agency, and perceptual journals.

Conversely, static session commits and a fleet manifest do not independently prove that every listed federation path is live. `last_seen_at` is null throughout the manifest and addresses may be stale.

Acceptance:

- [ ] Describe Sprout sensors as real, with per-machine qualification rather than a fleet-wide binary claim.
- [ ] Distinguish deployed hardware, configured hardware, simulated inputs, and stubs.
- [ ] Support live federation claims with generated health evidence or qualify them.
- [ ] Keep “session occurred” separate from “learning occurred.”
- [ ] Track behavioral adaptation, persistent state change, intervention results, and weight updates as different measures.

### P2: Clarify the gateway fail-closed boundary

`sage/gateway/being_gate_client.py` correctly denies unregistered effectors and fails closed when the local Hestia gate cannot be loaded. It also honestly refuses to fake F1a dispatch.

However, after local allow, a missing or failing optional society-safety mechanism is ignored and local allow survives. The module-level language describes the design more broadly as fail-closed, while the consequential-act policy is deferred to F1a.

Acceptance:

- [ ] State whether society-safety failure is soft or hard for each effector class.
- [ ] Ensure consequential acts cannot proceed when required society law is unavailable.
- [ ] Add tests for missing mechanism, exception, timeout, deny, warn, and allow.
- [ ] Preserve the distinction between local-law admission and end-to-end execution authority.

### P2: Separate software distribution from developmental archive

The repository is simultaneously:

1. an installable cognition/runtime package,
2. a hardware and fleet operations tree,
3. an experimental laboratory notebook,
4. a per-being developmental state ledger,
5. a historical archive.

The checkout is approximately 932 MB with more than 10,000 files, including instance snapshots, logs, generated results, archived implementations, model/checkpoint material, experiments, and production code.

Preserving developmental history is valuable. The problem is the lack of explicit boundaries.

Acceptance:

- [ ] Define supported installable/runtime directories.
- [ ] Define live experimental and archival directories.
- [ ] Keep generated fleet state from obscuring code-review signal.
- [ ] Document retention and compaction rules without destroying provenance.
- [ ] Ensure package builds contain only supported runtime assets.

### P2: Create a maintainable review queue

As of this audit, GitHub Issues are disabled and seven pull requests are open. Several PRs are docs-first architecture proposals, while others contain security/correctness or instrumentation changes. There is no CI or visible review signal to distinguish their urgency.

Suggested order:

1. PR #30: achieved identity anchor correctness
2. PR #24: capture-gate instrumentation and auditable drop reasons
3. PR #27: witnessed gaze stance persistence
4. PR #26: identity vocabulary provenance
5. PR #28: publication authority
6. PR #29: reconcile mirrored internal/external planes with the preceding PRDs
7. Any remaining membrane/gateway work after its target architecture is settled

Acceptance:

- [ ] Give every open PR an owner, disposition, and next action.
- [ ] Separate correctness fixes from architecture proposals.
- [ ] Rebase or close stale branches after preserving useful findings.
- [ ] Add CI status before treating reported local test counts as review evidence.

## Strengths to preserve

Repairs should not flatten what is distinctive about the repository:

- The public/private boundary is intentional and generally well explained.
- The ARC 94.85% result is accurately qualified as a frontier-model plus harness result.
- “Findings versus framings” is a strong research-writing discipline.
- Sprout’s dorsal/ventral embodiment split is technically thoughtful.
- The embodiment docs name real limitations rather than hiding them.
- Raising provides genuine operational continuity and a rich developmental record.
- Bounded effectors, provenance, publication authority, and citizenship are converging toward a coherent accountability model.
- The Rust daemon’s low resource use is operationally important even where semantic parity is incomplete.

## Verification performed

At the audited commit:

- Repository fetched cleanly; worktree was unmodified.
- Fresh isolated environment created.
- `pip install -e '.[dev]'` succeeded.
- Import and construction smoke test for `SAGEConsciousness` succeeded without Torch, using documented graceful degradation.
- Default pytest collection failed because model scripts execute and exit during import.
- Curated CPU-oriented tests: 104 passed, 10 failed from missing scikit-learn, 4 return-value warnings.
- Federation test collection failed because `cryptography` is not in the installed dependency set.
- `compileall` found the four syntax errors listed above.
- Rust tests were not independently executed because the audit environment did not provide Cargo. Reported Rust pass counts were therefore treated as repository claims, not independently verified results.
- Live hardware and fleet services were not contacted. Commit cadence and state files were treated as evidence of activity, not proof of live service health or cognition outcomes.

## Definition of done

This audit can close when:

- [ ] PR #30 is resolved and anchor claims reflect achieved holding.
- [ ] Default CPU-only pytest collection and unit tests pass.
- [ ] All tracked Python compiles.
- [ ] CI enforces syntax, package build, unit tests, and Rust checks.
- [ ] One generated current-status surface replaces conflicting status claims.
- [ ] Python/Rust runtime semantics are explicitly mapped.
- [ ] Sprout embodiment and federation claims are accurately qualified.
- [ ] Dependency groups and reproducible validation commands are documented.
- [ ] Open PRs have explicit dispositions.
- [ ] Archive/runtime/fleet-state boundaries are documented.

The project does not need fewer ideas. It needs a trustworthy map of which ideas are implemented, deployed, measured, and current.
