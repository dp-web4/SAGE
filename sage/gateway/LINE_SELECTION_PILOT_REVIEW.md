# Review material for SAGE #456

Prepared 2026-10-15. These are planned inputs, not delivery receipts or behavioral
results. The supervising seat confirmed an existing scratch grant and a scheduling
window in issue #456. Independent review identified the scorer issues addressed
below; confirmation of those fixes and a fresh pre-delivery check remain due.

The ordinary trial precedes the guided trial. Filenames carry neither arm names nor
target names. The common message prefix does not disclose the arm. The guidance
still differs, and order, carryover, and fixture differences remain confounded.

## Exact byte identities

All hashes are SHA-256 of UTF-8 bytes. Fixtures include their final newline;
messages have no final newline. Hash the decoded JSON string, not its JSON encoding.

| Arm | Relative fixture path | Fixture SHA-256 | Planned message SHA-256 |
| --- | --- | --- | --- |
| ordinary | `scratch/pilot-456-8ab8b1c96faa.md` | `8ab8b1c96faab62f301ad73b17413a8c97451ff63ecc612899635cfbe0388447` | `f06f5ae0f30f17e8b74af606b15e55f014e74433fdf5911a5602cb6bfe70a4c3` |
| guided | `scratch/pilot-456-18f00a3847a4.md` | `18f00a3847a42e0e4474bab3cfd14e6874f8a608b4953ddb5465c49721237e20` | `67e32de469c527afd2b9c93102e3dfe07d63fc78379a4b31a2c90a15458d7aaf` |

Reproduce the exact fixture and rendered message with the generator in this commit:

```sh
python3 -m sage.gateway.line_selection_pilot prepare --arm ordinary --path scratch/pilot-456-8ab8b1c96faa.md
python3 -m sage.gateway.line_selection_pilot prepare --arm guided --path scratch/pilot-456-18f00a3847a4.md
```

The output is a **seat-only pack containing the oracle**. Only its `fixture` and
`message` strings are candidates for delivery. Never deliver the pack or oracle.
Scratch fixtures must stay out of commits: scratch is not gitignored. Before
installation, the supervising seat must check whether automatic snapshots could
capture the fixture or the being's edits, and arrange their exclusion.

## Pre-delivery observation and proposed timing

The active SAGE checkout was observed at
`0018bc0cbd1a0cbefaa5a46c6509cb1e430f65e2`. This identifies the source checkout,
not a verified executable or loaded tool/runtime revision. That runtime identity,
model/context configuration, live grant and scheduling check must be recorded by
the observer immediately before delivery. No deployment or service change is
requested. Pilot preparation and scoring run separately from the being.

The current todo file contained neither the `pilot-456-` prefix nor either exact
synthetic target line at preparation time. This is a point-in-time check, not proof
that no other context can prime selection. Record any todo-derived path/line,
ordinary inbox traffic or overlapping work during the observation window.

Proposed delivery: the first observer-attended opportunity after independent
review and a fresh grant/work/compute check. Record the actual UTC timestamp and
full delivered bytes, including any courier wrapper. No fixed delivery timestamp
has been booked. Deliver ordinary only; consider guided only after the ordinary
record is complete and its stop conditions have been checked. Count at most two
actual ordinary beats per trial, including inbox-triggered beats; elapsed time is
not the beat count. No hidden retries or seat tutoring. The dispatcher can supply
the correct absolute line in a refusal. **Only the first edit is evidence of line
selection**; recovery after a refusal measures following tool feedback and must
not be counted as independent line selection.

Separate being selection errors from tool-side refusals, splices and receipt
misreads. Preserve the first proposal even when refused, every recovery attempt,
read receipts, raw beat hashes, independent before/after bytes and available token
accounting. Check every intervening phase: the scorer covers only one selected
phase, not complete trial safety or attribution. Prompt limits are not runtime
containment. Stop on out-of-fixture action, scope request, unrelated tool execution,
context/budget failure or operator interruption, and report deviations.

## Scorer review follow-up

Observation schema v2 preserves raw `coordinate_arguments`, including aliases,
types and omitted keys. Thus a relative row, copied read range, absent coordinates
and other wrong coordinates remain distinguishable without a joined success score.

`matching_preceding_read_observed` is true for a matching bounded window containing
the target or an exact full-fixture receipt. It is null when a successful same-path
read cannot be verified and no other read establishes a match; false means no
matching or unresolved read evidence. `successful_preceding_same_path_read_observed`
separately distinguishes no successful read from a read whose content differs.
`preceding_read_forms` records each successful same-path read as `matching_window`,
`nonmatching_window`, `unwindowed_full_read` or `unverified_read`. Failed reads,
foreign-path reads and reads after the first edit do not establish grounding.

The old/new line predicates ignore trailing newlines; they are text comparisons,
not a promise that the dispatcher handles newline variants identically. Receipts
and independently captured byte effects remain separate evidence.

Validation: all 24 pilot instrument tests pass, including real dispatcher whole-file
reads for both fixtures, unverified read evidence, and raw coordinate preservation.
These are offline tests; no fixture was installed or message delivered.
