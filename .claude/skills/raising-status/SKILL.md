---
name: raising-status
description: Show raising status across all SAGE instances in the fleet. Use when asked about raising progress, instance development, fleet status, or which phase any SAGE instance is in.
disable-model-invocation: false
allowed-tools: Read, Glob, Bash
---

# SAGE Fleet Raising Status

Read all instance directories under `sage/instances/` and produce a raising status report for the fleet.

For each instance directory found:
1. Read `identity.json` (live state) and `snapshots/identity.json` (last committed snapshot)
2. Read the most recent session file in `sessions/` (highest session number)
3. Extract: machine name, model, session count, current phase, milestones, last session date
4. Read 2-3 lines of the most recent session's last SAGE response to gauge quality/character

Then produce a report in this format:

---

## SAGE Fleet — Raising Status

**Date**: [today]
**Instances found**: [N]

### [machine] — [model]
- **Phase**: [phase] (session [N])
- **Milestones**: [list or "none yet"]
- **Last session**: [date/time]
- **Recent response quality**: [1-2 sentence observation — is it in character? first/third person? topic drift? embodiment awareness?]

[repeat for each instance]

---

### Fleet Summary
- Most advanced: [machine] at [phase], session [N]
- Notable observations: [anything interesting across instances — compare how different models handle the curriculum]
- Phase advance candidates: [any instances showing readiness to advance based on milestones or response quality]

---

Start by listing all directories under `sage/instances/` then read each one.
Skip `.bak` directories and `_seed`.
Skip instances where `instance.json` has `"archived": true` — these are replaced by newer model instances.
