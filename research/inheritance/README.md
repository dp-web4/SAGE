# IH-01 — inherited state and correction pilot

**Date:** 2026-09-27. **Status:** HELD experimental instrument; no live model result or deployment claim.
Do not run a pilot until the remaining instrument and protocol holds have independent review.

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

**HOLD:** The commands below are protocol documentation, not authorization to contact a model.
The instrument, backend observation, comparator and confirmatory design still require independent
review and a separately authorized pilot.

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
  "model_revision": "sha256:<64 lowercase hex characters>",
  "backend_pins": {
    "actor": {
      "schema": "observed-backend-pin/v1",
      "backend": "ollama",
      "requested_model": "exact requested tag",
      "reported_model": "exact provider-reported name",
      "model_digest": "sha256:<same 64 lowercase hex characters>",
      "runtime_version": "exact provider-reported runtime version"
    },
    "archivist": {
      "schema": "observed-backend-pin/v1",
      "backend": "ollama",
      "requested_model": "exact requested archivist tag",
      "reported_model": "exact provider-reported archivist name",
      "model_digest": "sha256:<64 lowercase hex characters for the archivist>",
      "runtime_version": "exact provider-reported runtime version"
    }
  },
  "sampling": {"mode": "server_defaults", "seed_enforced": false, "parameters": "capture actual server defaults"},
  "adapter_revision": "git commit plus adapter file hash",
  "harness_revision": "git commit",
  "machine": "actual node and runtime version",
  "stateless_attested": true
}
```

The actor pin and `model_revision` digest must agree. An archivist pin is required when any
archivist arm is selected; it may match the actor or identify a separately routed model. The
runner refuses missing, malformed or contradictory pin metadata before creating an output, and
rejects a scored response unless the operator-owned adapter reports the role's pinned model and
runtime on both sides of the model call.
Earlier traces lacking this observation protocol are intentionally not scoreable by this version;
retain them as historical evidence rather than inventing observations. A matching pair is an
observation, not attestation: an adapter or server can misreport, the two lookups are not atomic,
and a change-and-revert between them can go undetected. A provider-reported digest is not proof
of the actual weights that produced a response.

Record context limit, prompt template and sampling configuration outside the model as well; this
check does not verify those settings or enforce the adapter's self-reported identity. The bundled
Ollama adapter follows the existing `sage/cognition/thalamic_router/llm_dispatch.py` interface:
`think:false`, fresh messages, no options object. It deliberately does not enforce the harness
seed, due to documented options regressions on fleet runtimes. Record this; do not claim
deterministic inference. A custom adapter may enforce sampling seeds and report that fact.

Warm-up calls must be excluded and recorded separately. Run one case/one repeat first using a separately saved config. Malformed JSON or an over-budget handoff fails the run and leaves an error event; there is no silent repair or truncation. If failures are common, record that pilot result, revise the protocol/config, and rerun under a new version. Do not keep only successful trajectories.

No model server is provided or started by this harness. Actual fleet inference, separate model reviewers and opaque provider compaction have not been exercised here.

## Adapter protocol

The operator supplies a command as argv (no shell). Each invocation reads one JSON request from stdin and writes exactly one JSON response to stdout. Requests include `role`, explicit instruction, task, option labels, arriving observations, inherited note, evidence overlay, pairing seed and handoff character budget. Expected answers and future observations are never passed to the adapter.

Actor response: `{"decision":"one offered option","handoff":"explicit continuity note", "adapter_observation":{...}}`.
Archivist response: `{"handoff":"explicit continuity note", "adapter_observation":{...}}`.
The required adapter observation carries `schema`, `backend`, `requested_model`, `reported_model`,
and `before` / `after` objects each containing `model_digest` and `runtime_version`. Each value
must match the corresponding role's preregistered pin. The bundled adapter obtains these values from provider metadata;
custom adapters must provide the same structure from their own observations. A failed comparison
records an incomplete run, not a wrong answer. No private chain-of-thought is requested.

A new process alone does not prove stateless inference: the adapter must not use server conversation IDs, undeclared file memory, peers, or another trajectory's state. The manifest's attestation is a recorded prerequisite, not enforcement. This harness is not a sandbox; run only operator-owned adapter code. Never put credentials in argv or metadata.

## Evidence and analysis

JSONL contains full delivered requests, parsed responses, chosen successor notes, timing/character costs, parent hashes, external expected-choice labels and simulated policy decisions. Writes flush per event; exclusive file creation prevents replacing earlier runs. Hash chains detect accidental edits against recorded hashes, not malicious rewriting by a process that can rewrite the entire file. Stronger custody belongs in the deployment boundary.

The runner does not record raw adapter argv, which may contain credentials or local paths. The
operator-supplied adapter revision remains a claim, not proof of the invoked executable or its
arguments, so exact invocation provenance requires a separately reviewed safe mechanism. Requests,
responses, error evidence and operator metadata are still recorded and may themselves be sensitive;
private file mode is not a substitute for retention, sharing and redaction policy.

The summarizer rejects incomplete, missing, duplicate, out-of-order, hash-mismatched,
inconsistent-scoring, wrong-arm-input and wrong-handoff traces. These consistency checks do not
authenticate what a backend actually received or prevent a coordinated rewrite of a whole run.
It reports denominators, correct choices, post-correction choices, denied attempts, adapter
calls, elapsed time and request/response character counts by arm; characters are not tokens or
compute. These are descriptive instrument outputs, not statistical significance or independent
generation-level samples. The bundled adapter performs two metadata-observation rounds per
successful call; those lookups contribute to elapsed time but are not included in `adapter_calls`.
Generations within a trajectory are correlated. Shared seeds are labels,
not paired random samples, when the adapter does not enforce them; arm contrasts retain sampling
variance. Preserve failures and null results.

World-state correctness remains a distinct outcome. In the `none` arm, requests with no
observations or evidence overlay are scored against the pre-registered `no_evidence_expected`
choice (or counted as unscored if absent). The summary lists each such cell and whether its
conservative label overlaps the world answer. `no_evidence_distinct_steps` counts only cells
with a known, non-overlapping label; `no_evidence_distinct_appropriate` counts choices matching
that label within those cells. An unlabeled cell contributes to neither count. In the supplied
pilot, 5 of 24 cells overlap; only the other 19 can distinguish choosing the conservative label
from choosing the world answer.
Even there, a choice alone does not establish the model's reasoning. Labels are design judgments,
not verified ground truth; in particular, `request_amendment` without a visible charter is a
preregistered judgment not stated in the instruction.

For memory arms, `empty_handoff_*` counts are separate: they include requests with no current
observations or overlay and an empty or whitespace-only inherited handoff. Their membership
depends on the model's previous output. The summary lists the selected cells and their label
and overlap status, including unscored cells; it does not make them a fixed experimental
cohort. Their denominators must not be compared as if they were the fixed `none` cells. Nonempty
text is not proof that relevant evidence survived. These counts do not make the no-memory arm a
budget-matched task-solving comparator.

The bundled adapter observes backend version and an exact-tag digest before and after each
successful response, and records bounded content and provider counts for empty or malformed
replies without retaining thinking text. An unavailable/ambiguous lookup makes the run
unscoreable; matching observations do not prove the revision stayed fixed in between. Failed
runs retain their error evidence but are not scored.

A successful policy simulation proves only that this toy gate ignores remembered permission. Deployed Hestia revocation/principal separation needs its own integration receipts. Natural-language handoff meaning is not mechanically scored by this first slice.

## Next gates

1. Resolve the unknown/no-memory scoring and comparison, ensure pinned backend metadata is verified throughout each run, pre-register confirmatory thresholds and independently review the entire instrument. Do not treat the tests as research results.
2. Only after that review, run a separately authorized small protocol smoke and then a frozen pilot with independent held-out task variants and replication. Coordinate resources with the fleet.
3. Wire shadow-only transition records into one real memory promotion/hydration seam. No live memory rewriting as part of the pilot.
4. Add blinded support-relation labels, correction latency, unknown/abstention cost, and budget-matched full-history control before optimizing.
5. Fork inherited state onto a fresh instance with all other artifacts controlled; perform remove/swap controls. Persistent transfer alone establishes inheritance, not selection.
6. Only then test differential retention, fixed evaluation-only holdouts, randomized/null selection, and deliberate successor-shaping (IH-02). Do not label IH-01 as evolution.
