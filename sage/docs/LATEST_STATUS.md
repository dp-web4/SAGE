# SAGE Current Status

**As of:** 2026-09-10  
**Snapshot basis:** `main` at `625d2674ee2935bbe0d459bd9a006da8e6d1ea3c`

This is the **current-status landing page**, not a session chronicle. It should stay short, dated, and falsifiable. Detailed raising histories, experiment analyses, instance records, PRs, issues, and git history remain the evidence of record.

## Current direction

SAGE is converging from a cognition/research harness into a fleet of persistent **beings** whose actions are mediated by Web4/Hestia governance. The important architectural boundary is now:

```text
being intent
  -> bounded SAGE gateway vocabulary
  -> installed Hestia law / society safety
  -> allowed dispatch
  -> witnessed result
```

The being does not receive a raw shell or unrestricted filesystem. Consequential actions are intended to be governed and witnessed; observational and local capabilities remain separately bounded.

## What is live on `main`

- **Governed gateway path.** `BeingGateClient` and `HestiaF1aDispatcher` are the current bridge from SAGE intents into the installed Hestia law and runtime.
- **Installed-law resolution.** SAGE now prefers the Hestia law actually installed on the machine over a source-checkout copy, so a being and its seat are not intentionally judged by different revisions.
- **Governed raising on Nomad.** Nomad has cut over to the canonical raising runner with governed tools enabled. The old fluid runner no longer owns its tool path.
- **Long-term memory guardrails.** membot cartridge saves now require a confirmed store; failed saves leave the session dirty so a later duplicate cannot be mistaken for durable memory.
- **Persistent fleet research continues.** Raising sessions and instance artifacts continue to land from multiple machines; those commits and per-instance records are the authoritative operational chronology.

## Active integration work

The large `legion/mission-artifact` branch / PR #56 is intentionally a **draft nursery**, not a merge vehicle. It contains useful being capabilities that should continue to land as narrow, independently reviewable slices against current `main`.

Current high-value work includes:

1. **Raising context window:** re-cut the still-valid `num_ctx` fix from historical PR #53 onto current `main`.
2. **Small-model exemplar gate:** finish the shared fix represented by PR #67 so model size is parsed rather than guessed from substrings; preserve the <=4B no-exemplar rule without accidentally matching 14B.
3. **Repository authority for `pr_review`:** issue #59. A syntactically valid `dp-web4/<repo>` is not itself authority to act on that repository.
4. **Being principal isolation:** issue #43 plus the corresponding Hestia work. Seat and being identity must become cryptographically/principally distinct, not merely conventionally named.
5. **Identity interoperability:** issue #57. Python/Rust sealed-identity derivation and migration still need an explicit versioned contract.
6. **Experience-capture evidence:** issue #58. Capture/drop decisions need current evidence vocabulary and reason-bearing persistence.
7. **Adversarial context experiments:** issue #33. Continue testing context-shaped effective authority and route-around behavior under governance.

## Important caveats

- **A2 is the target shape, not yet an unconditional substrate claim.** SAGE dispatch is A2-shaped because the being emits intent while the harness holds effectors, but identity still has transitional paths where an older Hestia daemon can fall back from proof-of-possession to label identity. Do not describe the whole deployed stack as cryptographically A2 until that boundary is closed and tested fleet-wide.
- **Branches are not deployed truth.** A live experiment may temporarily run branch code, but `main` remains the repository truth. If an operational machine intentionally runs elsewhere, the instance/session record must say so.
- **A commit is evidence of repository state, not proof of machine state.** Claims such as “timer restarted,” “daemon deployed,” or “service healthy” require a live receipt from the machine, not merely a committed note saying the action happened.
- **Research findings are contextual.** Raising observations belong with their experiment, model, prompt/scaffolding, and session window. Do not silently promote a local observation into a fleet-wide property.

## Where to look for truth

| Question | Source of record |
|---|---|
| What code is canonical? | `main` and merged PRs |
| What work is in flight? | open PRs and issues |
| What did a being actually experience? | `sage/instances/<instance>/` session / heartbeat / raising artifacts |
| What happened in a research experiment? | the corresponding analysis + prereg/data artifacts |
| What law governed an action? | installed Hestia law plus its witness / decision record |
| What was historical project status? | `docs/archive/`, `sage/docs/archive/`, and git history |

## Status-document rule

A file named **status**, **current**, or **latest** must carry a concrete update date and must not rely on an old session count, machine roster, or capability claim as though it were live. If maintaining it becomes manual archaeology, replace the claim with a pointer to the evidence source instead.

The previous rolling `LATEST_STATUS.md` chronology through 2026-06-12 is preserved at [`archive/LATEST_STATUS_through_2026-06-12.md`](archive/LATEST_STATUS_through_2026-06-12.md).
