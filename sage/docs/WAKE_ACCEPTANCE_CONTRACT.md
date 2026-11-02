# Wake acceptance is not heartbeat entry

This follows the [watchdog audit](HEARTBEAT_WATCHDOG_AUDIT_2026-09-29.md).
The scope is the immediate arousal request and its Python console, sensory feeder
and Rust daemon consumers. Reconciled with event-driven waking (#296) on 2026-10-04:
pending events, claims, successor scheduling and `stay_awake` remain in place;
the removed salience/refractory gates are not restored. No installed service changes.

## Evidence boundary

`systemctl start --no-block` verifies and enqueues a start request. Successful
return does not establish that a new heartbeat entered, that it saw a particular
event, or that an action completed. Requests can coalesce with an existing job;
execution can fail after acceptance. See [systemctl semantics](https://github.com/systemd/systemd/blob/main/man/systemctl.xml).

The immediate-start response now has this contract:

| Field | Meaning |
| --- | --- |
| `engage` | Policy wants engagement; not an execution observation. |
| `wake_evidence_version: 2` | The immediate-start evidence contract described here. |
| `start_accepted: true` | The nonblocking scheduler command returned success. |
| `start_accepted: false` | The command was unavailable, so this request could not be submitted. |
| `start_accepted: null` | Acceptance is unknown, including nonzero exit, timeout, signal termination, or an unclassified exception. |
| `started: null` | No heartbeat-entry receipt was observed by this caller. Always null on this path. |
| `wake_error` | Diagnostic evidence when the request did not return success. |

The legacy `started` field remains present, but is no longer populated with a
boolean that confuses request acceptance with execution. Rejection of this request
does not prove that no heartbeat entered through some other wake source.
Even a positive command exit can follow submission and a lost reply; stderr is
diagnostic text, not a structured rejection receipt.

`respond()` delegates to `request_beat()`, which records pending work before attempting
the immediate start. On rejection or uncertainty it retains a passive fallback
description. It does not retry an uncertain request or manufacture a successor.
This deliberately removes #296's fallback arm after an unsuccessful immediate-start
command: a client error may follow a successful submission. The event stays pending
(unless the pending write itself failed, reported separately as `pending_error`).
A later event, a running beat's end check, or the watchdog can revisit retained work.
This trades immediate retry for avoiding a duplicate scheduling request without evidence.

Events observed during a running beat still arm the successor normally. Their
`next.armed` record is unchanged; it is not immediate-start acceptance or a beat-entry
receipt. The version field describes only the immediate-start result. Correctly
correlated successor acceptance/entry evidence remains follow-up work.

## Readers and mixed versions

Python's `arousal.delivery_text()` is used by the console. The Rust daemon has a
corresponding renderer, with the same JSON examples executed as tests in both
languages: [wake_delivery.json](../gateway/tests/fixtures/wake_delivery.json).
The sensory feeder uses that same Python renderer, and preserves nullable acceptance
in both sense and heard-event logs instead of coercing it into a `started` boolean.

- Explicit `start_accepted` takes precedence, including null, false, and malformed
  values. Readers do not coerce strings or numbers to booleans.
- With no new field, legacy `started=true` means only reported acceptance, never
  observed entry. Legacy false or missing evidence remains unknown.
- Neither renderer says a beat has started, nor promises that stored input will
  inevitably be consumed. Console rendering still escapes diagnostic text as HTML.

Deploy updated readers before or together with the producer. The new readers can
read old producers conservatively. An old reader paired with the new producer may
mislabel `started=null` as a failed start; retaining the field is not full semantic
backward compatibility. No automatic live rollout is part of this change.

### Merge prerequisite: reader rollout

Where the daemon invokes Python from the working tree, updating that tree changes
the producer immediately; it does not replace the already-running Rust reader.
A source update alone therefore does not satisfy the rollout requirement.

Before merging, arrange a release rebuild and restart for every deployment using
the Rust daemon. Build the updated reader with
`cargo build --release --manifest-path sage-rs/Cargo.toml -p sage-daemon`, install
the resulting binary at the service's configured executable path, and run
`systemctl --user restart sage-daemon`. Verify that the service is running the
updated binary before activating the new Python producer. The new reader can run
against the old producer while that update is pending. If updating the source tree
would activate the producer first, prepare the reader from a separate checkout.

Keep the merge on hold until this sequence has an operator and a deployment plan.
Include the long-running sensory feeder in that plan: restart it with the updated
reader before or together with producer activation. An old feeder would otherwise
coerce `started: null` to false and omit the new acceptance evidence from its logs.
Passing contract tests establishes reader agreement, not completion of rollout;
a successful restart likewise does not establish heartbeat entry or event
consumption.

## Tests and limits

The focused Python suite covers producer success/rejection/timeout/signal results,
JSON serialization, one-request/no-retry behavior (including a submitted request
whose reply is lost), shared wire examples, actual console POST/rendering, sensory
log/rendering, and the current pending-event/watchdog/successor behavior. Scheduler
calls are faked behind the shared systemd door, markers/pending sets/conversations
live in temporary directories. It does not wake a live being or invoke a model.

```sh
python3 -m pytest -q sage/gateway/tests/test_arousal.py \
  sage/gateway/tests/test_wake_acceptance.py \
  sage/gateway/tests/test_wake_delivery.py sage/gateway/tests/test_dp_console.py \
  sage/gateway/tests/test_heartbeat_wake.py \
  sage/gateway/tests/test_late_turns_are_queued.py \
  sage/gateway/tests/test_wake_continues_while_there_is_work.py \
  sage/embodiment/tests/test_every_sense_event_wakes_the_being.py \
  sage/embodiment/tests/test_hearing_words.py
cargo test --manifest-path sage-rs/Cargo.toml -p sage-daemon speaker_route_tests
```

A genuine entry receipt remains a separate slice. It needs a durable beat ID and
explicit correlation to pending event IDs; merely observing that a service is active
would not prove this request was consumed. #296 now provides pending claims and a
successor handoff, but claiming/releasing an event is not evidence it was included in
model context or answered. Correlation and interruption testing must distinguish
those stages. This contract leaves execution and consumption unknown until observed.
