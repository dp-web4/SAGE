# being_gate_client.py — read notes (beat 21:02Z, worktree /home/dp/ai-workspace/being-worktrees/legion-being)

File size per truncation marker: **35,959 chars; this read covers the first 12,000.**
Citations are quoted text (no line numbers — do not fabricate). Provenance labels are honest.

## Design invariants (module docstring — VERIFIED by direct read this beat)
- "FAIL-CLOSED: a being that cannot reach the law is STOPPED, never ungoverned."
- "When society-safety (Stage 2) is unavailable or errors, CONSEQUENTIAL effectors
  (peer_ask, memory_write, channel_egress, mesh, pr_review, remember, request_scope)
  hard-deny; only OBSERVATIONAL effectors (witness, memory_read, recall) soft-pass"
- "BOUNDED REGISTRY ... Enforced twice: the registry below will not emit an intent
  outside it, AND the gate denies it."
- "A2-by-construction: the being never holds the tool; dispatch is hestia's."

## Claim C2 status (fail-CLOSED client: only ALLOW reaches the dispatcher)
- Docstring-level support: YES (quoted above). Enforcement code (the client class /
  evaluate loop that asks the gate and dispatches only on ALLOW) lives in the UNSEEN
  remainder (chars 12,000–35,959). C2 remains SUSPECTED at docstring level until a
  check-verified test settles it.

## SELF-CORRECTION (recorded for the record)
Last beat's journal labelled being_gate_client.py as read "(full)". That was an
overclaim: file is 35,959 chars > 12,000 max_read_chars, so both reads were truncated
at the same point. Rule internalized: call a read "full" only when no truncation
marker appears; otherwise cite total size from the marker and say which part was seen.

## Registry (seen in this read)
- 12 effectors: peer_ask, witness, memory_read, memory_write, channel_egress, mesh,
  pr_review, check, recall, remember, request_scope, appeal.
- path_args only on memory_read/memory_write ("path"). All others judged by composed
  command or not at all (paths=()).
- "request_scope ... path_args=() is CORRECT here and must stay so: the requested
  path is, by definition, outside the grant" — pinned by
  test_request_scope_path_is_not_judged_under_mrh_path (name quoted from source).

## check organ internals (seen in this read)
- CHECK_TARGETS = {"gateway": "sage/gateway/tests/", "irp": "sage/irp/tests/"}.
- Node grammar: re.fullmatch(r"[A-Za-z0-9_]+", node); suite must be a declared key.
  Anything wider is refused as ValueError -> gate.raised deny (the refusal I hit on
  2026-09-07 with `reference_f1a::test_...` is this grammar, confirmed by source).
- No worktree in ctx -> ValueError: "No worktree means no check: fail closed."
- Command shape: python3 -m pytest -q -c /dev/null --rootdir={worktree} {path}.
  "-c /dev/null because the repo's pytest.ini declares an asyncio_mode this interpreter
  does not have (measured)".
- Absolute-path rationale (quoted): "The law must judge the path the command will
  actually touch; anything else is the `_safe_path` defect again, one layer over."

## pr_review internals (seen in this read)
- repo grammar: dp-web4/[A-Za-z0-9._-]+ ; number [0-9]{1,7} ; body travels by
  --body-file so "no review text can reach the shell".
- Fixed trailer appended by dispatcher: advisory and non-binding; LCT + hestia witness
  action id lines. "The being cannot omit or alter it."

## Observation to verify before stating (SUSPECTED)
Docstring lists observational effectors as "(witness, memory_read, recall)" but the
code has `_OBSERVATIONAL = frozenset({"witness", "memory_read", "recall", "appeal"})` —
appeal is in the code set but absent from the docstring list. Either a stale docstring
or an intentional omission; find the test that pins this before stating which.

## Next verification step (queued)
Find the test(s) in test_gateway.py that encode fail-closed dispatch (would be red if
the client dispatched on DENY/UNKNOWN), then `check gateway::<test_name>`.
