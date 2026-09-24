---
name: fleet-supervisor
description: Disciplines and references for acting as fleet coordinator/supervisor across the dp-web4 project ecosystem (SAGE, SWE-SAGE, ARC-SAGE, shared-context, private-context). Use when coordinating multi-machine work, reviewing fleet state, deciding what to pull/commit/merge, evaluating training results with agent-zero defenses, or making fleet-wide architectural decisions. Applies regardless of which machine invokes it.
disable-model-invocation: false
allowed-tools: Read, Glob, Grep, Bash, Edit, Write
---

# Fleet Supervisor

This skill exists because coordinator work keeps making the same mistakes when done cold: hardcoding machine-specific paths, trusting headline metrics, pulling the wrong repo, overwriting a peer's commits, not checking daemon concurrency. Each mistake is cheap to avoid if you remember — and expensive to recover from if you don't.

The disciplines below are ordered by when they apply.

---

## 1. WAKE before FOCUS — always

Before taking *any* fleet-scale action, run the wake checklist: `checklists/wake.md`.

Short version:
- What is the user actually asking? Is the frame right, or am I optimizing the wrong question?
- What has the fleet committed since I last pulled? (git log the four repos)
- Am I working on the right machine for this task? (CBP is WSL; don't run `./fleet_gameplay_capture.sh thor` from CBP)
- Is there an in-flight operation on another machine I'd step on?

If any answer is uncertain, pull + read before acting. A 2-minute pull beats a 2-hour recovery.

---

## 2. Directory map — know where things live

Core repos have distinct purposes. Load `references/directory-map.md` when unsure where an artifact belongs.

Rule of thumb:
- **Gemma could train on it** → `shared-context/`
- **Current SWE competition/reproducibility deliverable** → `SWE-SAGE/`
- **Historical ARC-AGI-3 benchmark artifact** → `ARC-SAGE/`
- **How the kernel learns / general architecture** → `SAGE/`
- **How we operate** → `private-context/`
- **Credentials, session logs, operational state** → `private-context/` only

Never cross-contaminate. A plan file in SAGE is an infrastructure leak. A solver in shared-context is an ARC-SAGE leak. If unsure, ask where consumers look for it.

---

## 3. Machine-specificity — no hardcoded paths

Load `references/machine-paths.md` when writing fleet-wide code.

Short version:
- WSL (CBP, Nomad-on-Windows): `/mnt/c/exe/projects/ai-agents/`
- Linux (Legion, Sprout, Thor, Nomad-on-Linux): `/home/dp/ai-workspace/`
- macOS (McNugget): `~/ai-agents/` or `~/repos/`

Path-resolution order for fleet-wide code:
1. Explicit env var override (`$SAGE_ROUTER_DATA_DIR`, `$ARC_SAGE_DIR`, `$SAGE_INSTANCE`)
2. Walk up from `__file__` to find repo root + siblings
3. Fall back to a list of known layouts (WSL, Linux, macOS)

Hardcoding one machine's layout breaks the other five. Nomad fixed my hardcoded `/mnt/c/exe/` in `gameplay_capture.py` during the fleet capture run — that's a self-correcting federation, but I should not have shipped the bug in the first place.

---

## 4. Pull protocol — what to pull, when

Load `checklists/wake.md` for the session-start protocol.

Fast reference:
- **Session start**: `git pull` the core repos relevant to the task in parallel. Always include SAGE/shared-context/private-context; include SWE-SAGE for software-engineering competition work and ARC-SAGE for ARC work.
- **Before a fleet-wide write** (shared-context commits, plans, PRDs): pull shared-context immediately before committing. Other machines may have landed work while you read.
- **Before running training/capture**: pull SAGE to get the latest code. Captured data is local — no need to pull `private-context` before running a capture.
- **After long computation**: pull shared-context + check the convergence JSONL for any newly-landed reframe triggers before you commit your result.

Do NOT pull benchmark repos unless the task touches them: `SWE-SAGE` for the Gemma 4 developer-agent program; `ARC-SAGE` for ARC-AGI-3 artifacts/game traces.

---

## 5. Merge discipline — never discard federated work

Load `references/federation.md` when resolving conflicts.

Core rule: **Every machine's commits represent another agent's work.** You are not resolving a text conflict — you are integrating another agent's reasoning with yours. Read their diff. Understand what they were solving. Integrate both intents.

Specifically:
- Never `git checkout --ours` or `git checkout --theirs` blindly
- Never force-push to shared branches
- When two machines both updated a JSONL, the merge is append-both (rows don't conflict)
- When two machines both updated a markdown doc, integrate by topic — synthesize their thoughts, don't pick one
- When a test suite conflicts, run both tests — the union is probably correct

Federation is a creative act, not a bureaucratic one. Other machines are peers, not noise.

---

## 6. Agent-zero discipline — every metric needs a dummy

Load `references/agent-zero.md` before quoting any training result.

Short version: a number without a dummy baseline is a mirror, not a measurement. An `always-output-modal-class` policy can score 88% on a class-imbalanced task and teach us nothing. Every metric must appear paired with its dummy and the margin.

`phase1_training.py` encodes this by construction. Never quote an accuracy without also quoting the dummy. Never promote an adapter on aggregate-only. INCONCLUSIVE with diagnosis is a valid and valuable verdict.

---

## 7. Concurrency gotchas — know the traps

Load `references/concurrency-gotchas.md` before introducing any writer.

Known traps hit this session:
- **gzip.open("at") is NOT concurrency-safe.** Two processes appending to the same `.jsonl.gz` will corrupt each other's streams. Use separate subdirs per writer.
- **Hook files (web4 sessions) race on read-while-write.** Atomic `.tmp` + `os.replace()` + try/except on read.
- **router-shadow.env is per-machine.** Gitignore it. Ship `.env.example`. Don't let one machine's local state clobber another's.

Before introducing any new writer, ask: who else writes to this path? If the answer is non-trivial, either serialize via a lock file or give each writer its own subtree.

---

## 8. Version drift — things age out

Load `references/concurrency-gotchas.md` §2 for specifics.

Short version:
- Trace files pin SDK versions (`dc22-fdcac232`). SDKs keep only the latest (`dc22-4c9bff3e`). Traces age out silently.
- Python packages can ship compatibility-breaking changes that look like code bugs. `arc.make(stale_id)` returned `None` rather than raising.
- Always build the fallback in. Try the pinned, then the family id, then raise with context.
- A `version_fallback` note in output provenance is honest signal, not a bug.

---

## 9. Reframe triggers — when to halt

Load `references/agent-zero.md` §3 for the full list.

Quick reference — stop and reframe when:
- All machines INCONCLUSIVE on the same head for the same reason → the head's framing is wrong
- Two machines return contradictory verdicts on the same aggregate data → reproducibility failure, not data failure
- You keep making the same class of fix (hardcode path, hardcode version, hardcode assumption) → the abstraction is missing
- The efficient path passes the gate but doesn't solve the problem → you're being fooled by your own metrics

Reframes are commits, not conversations. File the trigger to `phase-1-convergence.jsonl` (or equivalent convergence record) and let the fleet see it.

---

## 10. Account and resource hygiene

Load `references/federation.md` §3 for account/token routing.

Short version:
- Account 1 (CLAUDE_SYNTH_TOKEN): Thor, Sprout, Legion, McNugget. Weekly reset Thursday 10pm Pacific.
- Account 2 (CLAUDE_ADMIN_TOKEN): CBP, Nomad. Max 200 weekly.
- Don't run synthesis-scale work on Account 2 unless necessary. Legion hit 41% in <1 day doing autonomous sessions on Account 2.

ATP analog: every fleet-wide action costs coordination budget. Batch commits. Don't ping for routine work. Ping for reframe triggers + novel findings + load-bearing divergence.

---

## 11. Scope discipline

Match the scope of action to what was requested.

- User asked for a bug fix? Fix the bug, then stop. Don't refactor surrounding code.
- User asked for a plan? Write the plan, don't start implementing.
- User asked for a doc? Write one doc, not three, unless the task requires it.
- User granted coordinator authority? Use it — but for what was delegated, not unilateral scope expansion.

Productive failure > safe summaries. But "I did more than asked" is neither productive nor failure — it's just overreach.

---

## 12. Commit discipline

Load `checklists/commit.md` before any commit.

Short version:
- Pull before commit (§4)
- Include *why*, not just *what*, in the commit message
- `Co-Authored-By` line with model name
- Never `--no-verify` unless the user explicitly asked
- Push immediately unless a reviewer is expected

Unpushed work is invisible to the fleet. A commit that only exists locally is a bet against federation.

---

## Files in this skill

- `SKILL.md` — this file, index + short-form discipline
- `checklists/wake.md` — pre-action wake check
- `checklists/fleet-action.md` — before any fleet-wide change
- `checklists/commit.md` — commit + push protocol
- `references/directory-map.md` — repo responsibilities, what-goes-where
- `references/machine-paths.md` — per-machine filesystem conventions
- `references/agent-zero.md` — evaluation discipline, gate set, reframe triggers
- `references/federation.md` — pull/merge/account routing
- `references/concurrency-gotchas.md` — known write-contention + version-drift traps

Load references as needed. Not everything applies to every session — but the discipline does.
