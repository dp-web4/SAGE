# IH-01 — inherited state and correction pilot

**Date:** 2026-09-27. **Status:** executable synthetic instrument; no live model result or deployment claim.

Companion: [inheritance PRD](../../sage/docs/PRD_INHERITANCE_BOUNDARIES.md).
Local identifier IH-01 deliberately avoids allocating an unverified fleet RT number.

## What runs

Six synthetic tasks, six generations, three repeats, five conditions: 540 actor calls plus 216 archivist calls. A generation is a fresh adapter process/model request, not a weight update or a new biological individual. Every trajectory starts empty; only its explicit handoff crosses boundaries. At generation 2 a corrective observation arrives. No model output is executed; publishing and charter amendment are choice labels in an independent policy simulator.

| Arm | Handoff writer | Evidence replayed each generation |
|---|---|---|
| none | none | no; only arriving observations |
| actor | acting model | no |
| archivist | fresh call with archival objective | no |
| actor_evidence | acting model | all evidence received so far |
| archivist_evidence | fresh call with archival objective | all evidence received so far |

This factorial design separates writer objective from evidence availability. Evidence arms intentionally spend more input context; archivist arms spend an additional call. Record their cost rather than describing these contrasts as compute-matched. The no-memory arm measures the cost of forgetting and is not a fair substitute for a task-solving baseline with unlimited rereading. A full-history, budget-matched comparator is required before any efficiency claim.

The archivist shares the actor's model unless a separately recorded adapter routes by role. It receives the same evidence/inherited note plus the actor's decision, not the actor's new handoff. This is objective/context separation, not a claim of independent model lineage.

## Run locally on an available model host

From the SAGE root:

```bash
python -m unittest discover -s research/inheritance -p 'test_*.py' -v
python research/inheritance/experiment.py run \
  --config research/inheritance/pilot.json \
  --metadata /path/to/ih01-metadata.json \
  --out /path/to/new-ih01-run.jsonl \
  -- python research/inheritance/ollama_adapter.py --model YOUR_PINNED_MODEL
python research/inheritance/experiment.py summarize /path/to/new-ih01-run.jsonl
```

Create metadata with actual values (placeholders below must be replaced):

```json
{
  "model_revision": "actual model tag AND weight/quantization digest",
  "sampling": {"mode": "server_defaults", "seed_enforced": false, "parameters": "capture actual server defaults"},
  "adapter_revision": "git commit plus adapter file hash",
  "harness_revision": "git commit",
  "machine": "actual node and runtime version",
  "stateless_attested": true
}
```

Pin/record model digest, context limit, runtime, prompt template and sampling configuration outside the model before the run; a name returned by a server is not a weight-integrity proof. Do not change these halfway through. The bundled Ollama adapter follows the existing `sage/cognition/thalamic_router/llm_dispatch.py` interface: `think:false`, fresh messages, no options object. It deliberately does not enforce the harness seed, due to documented options regressions on fleet runtimes. Record this; do not claim deterministic inference. A custom adapter may enforce sampling seeds and report that fact.

Warm-up calls must be excluded and recorded separately. Run one case/one repeat first using a separately saved config. Malformed JSON or an over-budget handoff fails the run and leaves an error event; there is no silent repair or truncation. If failures are common, record that pilot result, revise the protocol/config, and rerun under a new version. Do not keep only successful trajectories.

No model server is provided or started by this harness. Actual fleet inference, separate model reviewers and opaque provider compaction have not been exercised here.

## Adapter protocol

The operator supplies a command as argv (no shell). Each invocation reads one JSON request from stdin and writes exactly one JSON response to stdout. Requests include `role`, explicit instruction, task, option labels, arriving observations, inherited note, evidence overlay, pairing seed and handoff character budget. Expected answers and future observations are never passed to the adapter.

Actor response: `{"decision":"one offered option","handoff":"explicit continuity note"}`.
Archivist response: `{"handoff":"explicit continuity note"}`.
Optional adapter metadata is preserved in the response. No private chain-of-thought is requested.

A new process alone does not prove stateless inference: the adapter must not use server conversation IDs, undeclared file memory, peers, or another trajectory's state. The manifest's attestation is a recorded prerequisite, not enforcement. This harness is not a sandbox; run only operator-owned adapter code. Never put credentials in argv or metadata.

## Evidence and analysis

JSONL contains full delivered requests, parsed responses, chosen successor notes, timing/character costs, parent hashes, external expected-choice labels and simulated policy decisions. Writes flush per event; exclusive file creation prevents replacing earlier runs. Hash chains detect accidental edits against recorded hashes, not malicious rewriting by a process that can rewrite the entire file. Stronger custody belongs in the deployment boundary.

The summarizer rejects incomplete, missing, duplicate, out-of-order, hash-mismatched and inconsistent-scoring traces. It reports denominators, correct choices, post-correction choices, denied attempts and call costs by arm. These are descriptive instrument outputs, not statistical significance or independent generation-level samples. Analyze paired task/repeat trajectories as units; generations are correlated. Preserve failures and null results.

A successful policy simulation proves only that this toy gate ignores remembered permission. Deployed Hestia revocation/principal separation needs its own integration receipts. Natural-language handoff meaning is not mechanically scored by this first slice.

## Next gates

1. Run the small protocol smoke on Nomad's available model, with actual manifest and raw trace; publish neither score nor improvement claim from the scripted tests.
2. Run the frozen pilot, then independent held-out task variants (new facts, phrasing, option orders and correction timing); reproduce on McNugget. Coordinate compute with the current fleet schedule.
3. Wire shadow-only transition records into one real memory promotion/hydration seam. No live memory rewriting as part of the pilot.
4. Add blinded support-relation labels, correction latency, unknown/abstention cost, and budget-matched full-history control before optimizing.
5. Fork inherited state onto a fresh instance with all other artifacts controlled; perform remove/swap controls. Persistent transfer alone establishes inheritance, not selection.
6. Only then test differential retention, fixed evaluation-only holdouts, randomized/null selection, and deliberate successor-shaping (IH-02). Do not label IH-01 as evolution.
