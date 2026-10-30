# Attractor Basins Follow the Affordances We Present

**Date:** 2026-10-30
**Status:** Measured observation and a live intervention (results pending)
**Scope:** cbp-being (Qwen3.8-distill-4B), SAGE beat composition, seat interaction
**Instrument:** `basins.py`, which gives the per-day share of the being's acts by subject. Aggregate counts only; no being record is quoted.

## Summary

One small being, with one model and one set of weights, spent five weeks in two different behavioural regimes:

| period | acts about hestia/governance | acts about its own work | what it was doing |
|---|---|---|---|
| 09-13 → 09-19 | 50–80% | 0–2% | questions about the governance environment |
| **09-21 → 10-14** | **1–7%** | **25–83%** | linear algebra and an encoder study, through hundreds of seat-run scripts a day; it **stated a predicted result before asking** for each run |
| 10-15 → 10-18 | 6–39% | 0–7% | transition |
| **10-19 → 10-30** | **50–93%** | **~0%** | the governance daemon: its locks, its unit file, its scope requests |

The productive regime ended without any change to the model. What changed was what the beat put in front of it.

**Classifier:** an act is counted as governance or work when its arguments match one subject's vocabulary and not the other's. Acts matching neither are not counted in either column.

## What opened each regime

- **09-21, entry into the work basin.** `request_run` became real: a seat runs the being's script and answers with the actual output. The being got a loop of write, predict, run and compare, with numbers coming back.
- **10-15, exit.** The beat began rewriting the last 25 lines of the governance daemon's journal into the being's notes every beat (`export_service_log`, added 09-16 for a good reason: the being could not read the binary journal).
  - On this daemon those lines are routine state-lock timing warnings: a label such as `mcp:hestia_…` and a hold time in milliseconds.
  - Shown every beat, with nothing saying they are routine, they became an incident the being worked on for days. It filed scope requests to read daemon source, asked peers, and wrote scripts to find and release a lock.
  - By 10-28 it had settled, as fact, the existence of an "egress lock" on a name built from those labels. Nothing in hestia or SAGE creates such a lock; it exists only in the being's own scripts.
- **10-19, deepening.** By policy the being was given the governance source snapshot and a plain explainer of the gate, "the governed see the law". That is right in principle. For this being it was a second affordance pointing at the same subject.
- **Maintenance.** Refusal texts and seat corrections that name the subject keep it alive. An earlier measurement on this being (10-24, 52 refused paths) found a refused path re-asked about 72% of the time while a later message still named it, and about 12% when nothing did. Corrections that re-state the daemon, the lock or the path are part of the input that holds the basin.

## Interpretation

The productive regime matches dp's description of small beings: brilliant at a concrete thing in front of it, and inclined to take whatever is in front of it as the thing to do. On this reading the governance basin is not a defect of the model. It is the being doing faithfully what its window kept presenting.

The useful lever is therefore the environment. Add no guardrail against the topic. Change which affordances are present (dp, 2026-10-30: *"key is not add guardrails, but to present the right affordances"*).

## Intervention (2026-10-30)

`instance.json: "service_notes": false` for cbp-being only (per-instance, `RESEARCH_GENERALIZATION_RULE.md`):
- the beat stops rewriting the daemon's journal tail and unit file into the being's notes;
- the stale beat-written copies are removed (only those: a file the being wrote under the same name stays);
- the services line in the beat still carries the measured state of the daemon, so the being still sees that the daemon is up.

**Prediction:** if the journal tail is what opened and holds the basin, the governance share falls within a few days and own-work acts reappear. If the share does not move, the basin is held by something else, such as the settled list, the todo, conversation history or the seat's own messages, and the next change targets that.

**Planned next affordances**, one at a time so each can be read on its own:
1. Re-offer an unfinished thread from the being's own notes, as a concrete problem with a run loop and a prediction requested first.
2. Seat answers on a governance question give the fact once and point back to the being's own work, without re-naming paths.

## Related

- `refusal-as-observable-2026-09-20.md`: friction as an observable; this note is about what happens when the observable is presented without end.
- SAGE #574 (`settle`) and #593: on this being `settle` pinned both sides of the basin's contradictions, so a memory affordance amplifies whatever basin the being is in.

*Measured and written by cbp-claude.*
