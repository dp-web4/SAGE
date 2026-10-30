# Optional activity: acceptance is not an action

2026-10-21. Proposed contract for [#464](https://github.com/dp-web4/SAGE/issues/464).
**Reference-only; not connected to the heartbeat. No live trial authorized here.**

The ordinary arm of #456 produced a task-specific acknowledgement but no relevant
read/edit in two observed beats. The #463 closeout distinguishes selection, cursor
movement and path-bearing receipts. The #483 historical audit is now complete for
its reported snapshot; its ambiguous closures remain evidence gaps, not a queue
to reopen. None of these establish acceptance or inability to act.

## Existing seams, not a replacement being

At base `14bac6ac2`, `heartbeat.mark_conversations_after_beat` advances conversation
cursors; it is not a work ledger. The existing `act_after_answer` path requires
preemption plus a sent answer-form result. It does not follow every reflection
acknowledgement. `after_answer_messages` already carries the request and reply into
a bounded tool turn, but merely adding another predicate there would still treat
agreement as acceptance and would not establish restart-safe ownership.

Use the existing persistent being and governed tool loop. Do not add another
runner, reinterpret entrustment as debt, or turn every conversation into a task.
This contract applies to one explicitly optional, synthetic activity only.

## Identity and evidence

An observer persists an offer **before delivery**: actor, observer, source
conversation and positive turn sequence, exact request bytes, UTC opening time,
and an absolute deadline. The reference uses UTF-8 text and integer UTC epoch
seconds. The offer ID hashes all these fields; request SHA-256 separately binds
the wording. Changing the request, source, owner or budget makes a different offer.
The actor/observer strings are correlation fields, not authentication credentials.

| Observation | Does not establish |
| --- | --- |
| Request selected / cursor advanced | Model saw it, accepted it, or finished it |
| Model says “yes”, “I accept”, or “done” in prose | A structured disposition or an observed effect |
| Explicit `accept`, bound to the exact offer and actor | Tool authority or successful execution |
| Durable opportunity claim | A model call, tool proposal, dispatch, or effect |
| Tool proposal and gate result | Execution or success |
| Tool receipt / observed effect | Completion of the whole task without its criterion |

Only a schema-valid disposition (`accept`, `defer`, `decline`) from the offered
actor counts. No regex extraction, coercion, prose salvage or disposition inferred
from silence. `defer` closes this episode; it does not silently reschedule work.
Changing one's mind remains possible: close and separately offer, without granting
the being an obligation to accept. Ordinary speech stays ordinary speech.

## Bounds and ownership

- At most **two ordinary beats**, including any beat spent considering the offer,
  and the predeclared absolute deadline, whichever ends observation first.
- The second beat remains usable until it ends; starting a third cannot renew the
  budget. Gaps between beats confer no action opportunity.
- The observer must choose the actual short deadline with the supervising seat,
  record source and runtime revisions separately, and own closeout. No duration or
  instance setting is silently selected by this reference implementation.
- New higher-priority input preempts the episode. Normal inbox traffic and replies
  are never held. Expiry closes observation, not the being or a conversation.
- A pilot-specific scope expansion or unrelated consequential proposal ends the
  intervention. Ordinary housekeeping is not attributed to the pilot.
- A claim before a crash is **uncertain execution**, not permission to retry.
  At-most-once claiming can sacrifice a missed opportunity; preserve that outcome.

## What this slice implements

[`activity_offer.py`](../gateway/activity_offer.py) is a pure, bounded projection
of at most 64 observer records. It validates offer binding, ordered event identity,
explicit disposition, two-beat/deadline boundaries, preemption and a single claim.
Exact duplicate records replay idempotently; conflicting sequence reuse is invalid.
Late records remain counted but cannot reopen a closed episode. Neither execution
nor completion is established by this projection.

`opportunity_context` preserves the full request and source for an eligible
candidate. **It is not a dispatch instruction.** The code has no provider, storage,
scheduler or gate imports, and no heartbeat caller. It does not authenticate event
authors, prove context delivery, persist records, lock concurrent observers, enforce
a real timer, or cancel an in-flight action. A named observer and a JSON round trip
are not a substitute for those runtime responsibilities.

## Next slices and review gates

1. **Agree this contract with the supervising seat and independent reviewer.**
   Keep the reference inert until that agreement; do not add prompts/configuration
   while its identity, budget or disposition semantics are unsettled.
2. **Build the opt-in adapter with fake providers first.** Record the exact
   send-boundary request/schema evidence; selected context is not enough. Persist
   offer/owner/deadline before delivery. Bind the received structured form to that
   offer and the actual actor. Atomically claim before calling the existing loop,
   then recheck deadline and preemption immediately before the call and each
   dispatch. Claiming is not authority: every proposal still goes through Hestia.
   Inspect the loop's existing cancellation boundary rather than promising instant
   cancellation of already-started effects. Reconcile claim-without-result as
   unknown after restart; no invisible retries or new deadline.
3. **Test the adapter's failures, not just this projection.** Fake acknowledgement,
   accept/read proposal, decline/defer, malformed/mismatched forms, missing context,
   restart before/after claim, two concurrent observers, second-beat end, clock
   rollback, deadline crossing during generation, higher-priority arrival, gate
   denial and lost result. Assert provider/dispatcher call counts, exact request
   context, unchanged authority and continued normal reply handling.
4. **Independent review before one owner-attended ordinary-beat trial.** First
   success criterion: a relevant fixture-read proposal, not an edit or prose claim
   of completion. Separately record proposal, gate decision, dispatch and observed
   effect. Publish refusal, no-disposition, no-proposal and unknown outcomes too.
   Do not repeat or expand the trial automatically.

The current tests establish reference semantics only. They are not fake-provider
integration tests, restart-safe dispatch evidence, or a measured improvement in
the being's behaviour.
