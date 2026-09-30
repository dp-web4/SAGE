# Heartbeat watchdog: intention, evidence, remaining guarantees

The intended contract already exists: events drive engagement; the idle timer is a
backstop. This audit identifies implementation gaps, not a proposal to replace that
design with periodic polling.

Baseline: `c9e203e38` (the audited gateway code is unchanged from `8c55a957d`).
Scope: Python heartbeat/arousal, their Rust conversation callers, timer examples,
and read-only inspection of one installed configuration. No fleet-wide deployment
claim follows from this sample. No service was started, stopped, or reconfigured.

## Findings

1. **The idle-health check inferred configuration it did not inspect.** A loaded,
   active timer without an elapse was treated as an inactivity timer waiting for beat
   completion. The checker did not inspect its directive, target, or target state.
   A realtime `0` sentinel also counted as a scheduled wake. Both false-positive
   shapes were reproduced by executing the committed pure interpretation function.
2. **The example and the checked installation used activation-relative timing.**
   `OnUnitActiveSec` counts from activation, while `OnUnitInactiveSec` counts from
   deactivation. Both can participate in a watchdog, but only the latter matches
   the documented post-beat quiet interval. The installation had a scheduled elapse;
   the latest three inspected beat records completed normally. This is not evidence
   of an actual stall.
3. **In-flight events can wait for the idle timer.** `arousal.decide()` records that
   an already-running beat has not received the new turn. `wake_for_late_turns()`
   optionally schedules a successor, but held wake is off by default and was off in
   the checked configuration. Even enabled, its own docstring identifies the gap
   between the tail scan and process exit, and the case where a beat never reaches
   that scan. Recorded input and a reliably scheduled successor are different facts.
4. **Wake acceptance is not beat entry.** `_start_wake()` sets `started=true` after
   successful `systemctl start --no-block`. The command verifies and queues the job;
   it does not observe heartbeat entry. Python console and Rust delivery text use
   that field. Correcting it requires a coordinated producer/consumer contract change.

Sources: [arousal](../gateway/arousal.py), [heartbeat](../gateway/heartbeat.py),
[systemd timer semantics](https://github.com/systemd/systemd/blob/main/man/systemd.timer.xml),
[nonblocking start semantics](https://github.com/systemd/systemd/blob/main/man/systemctl.xml).

## First bounded correction

- A reported scheduled elapse now requires a loaded, active timer targeting the
  intended heartbeat service. Absent-deadline sentinels do not count as schedules.
- An unscheduled timer is accepted as waiting for completion only when its positive
  inactivity interval and the target service's active/activating state are observed.
- Failed property queries cannot become evidence merely through plausible stdout.
- The example measures quiet after completion. Existing installations are unchanged.
- Missing evidence is reported as an unconfirmed idle wake, not proof that every
  possible wake source is absent.
- Existing opt-in fallback and resume behavior remain opt-in. Held-wake defaults,
  resource policy, and live configuration are unchanged.

These are scheduling observations, not execution receipts. The two property queries
are not atomic; configuration can change after inspection. A healthy timer can still
lead to a failed service. This patch does not claim exactly-once execution, crash
recovery, or a complete liveness proof.

## Verification

Run from the repository root:

```sh
python3 -m pytest -q sage/gateway/tests/test_heartbeat_wake.py \
  sage/gateway/tests/test_arousal.py \
  sage/gateway/tests/test_wake_held_and_conversing.py
git diff --check
```

Result for this correction: **52 passed**; whitespace check clean.

The focused tests fake scheduler calls and isolate conversation/witness state. They
cover both ordinary scheduled deadlines and the pending-inactivity case, wrong
targets, failed queries, deadline sentinels, multiple timer directives, custom unit
names, opt-in fallback, and unchanged event/refractory/held-wake behavior. No model
inference or live wake injection is required. A deployment acceptance test remains
separate: use an owned disposable service, observe event-triggered activation, then
verify the idle deadline is rebased after completion.

## Next slices, in dependency order

The first reader/producer correction is described in the
[wake acceptance contract](WAKE_ACCEPTANCE_CONTRACT.md). It separates acceptance
from unknown entry; correlated execution receipts and durable handoff remain below.

1. **Wake evidence contract:** distinguish request, scheduler acceptance, beat entry,
   and consumed event IDs; update Python and Rust readers together. Unknown execution
   is not failed execution. Do not use a no-block return as an entry receipt.
2. **Durable pending-work handoff:** retain event IDs until acknowledged at a defined
   consumption boundary; make the worker-exit/pending-check transition race-safe.
   Keep resource/refractory limits without discarding the obligation to run later.
3. **Failure and resource tests:** events during execution, after the final scan,
   bursts, worker crashes, unavailable scheduler, and deadline exhaustion. Check for
   both stranded obligations and redundant costly wakes.

Do not enable shorter cadences fleet-wide as a substitute for those guarantees.
For a task-scoped multi-organ runtime, the transferable requirement is preservation
and resumption of unfinished obligations inside its allowed lifetime—not an assumption
that the host permits a permanent background heartbeat.
