# Directory Map — repo responsibilities

Repositories have explicit roles and visibility boundaries. Artifacts land in exactly one canonical home. Cross-contamination is a bug.

## SWE-SAGE (private during competition, MIT-0) — software-engineering competition / research workspace

**What it is**: Private working implementation and experiment record for the Gemma 4 Developer Agent Competition. It is designed so selected results can later be promoted into public SAGE or released as a reproducibility artifact without requiring the working repository to be public during active competition.

**What goes here**:
- Competition agent runtime and adapters
- Competition post-training recipes/configs and team-private training work that is legal for the intended use
- SWE-specific persistent-state and premise-fidelity implementations
- Competition ablation configs, team-private traces, metrics, and results
- Kaggle submission packaging
- Paper-track manuscript/assets
- SWE-specific findings and failure analyses

**What does NOT go here**:
- General SAGE kernel mechanisms that are not SWE-specific
- Unrelated private fleet traces; training data whose competition legality/provenance is unresolved for the intended use
- Credentials or machine-specific operational state
- Exploratory mechanisms whose provenance/publication status is not clean

**Rule**: private SWE-SAGE may depend on competition/team-private work during development, but any later public claim/release must be reproducible without hidden dependencies on `dev-SAGE`, `shared-context`, `private-context`, or unreleased SWE-SAGE evidence.

**Canonical on-disk**:
- WSL: `/mnt/c/exe/projects/ai-agents/SWE-SAGE/`
- Linux: `/home/dp/ai-workspace/SWE-SAGE/`
- macOS: `~/ai-agents/SWE-SAGE/` or `~/repos/SWE-SAGE/`

---

## ARC-SAGE (public, MIT-0) — historical ARC-AGI-3 benchmark artifact

**What it is**: Historical/public ARC-AGI-3 research artifact. Consumers: ARC-AGI-3 researchers and anyone auditing the spring-2026 work. It is not the canonical home for the Gemma 4 developer-agent competition.

**What goes here**:
- Solvers (`solvers/{game}.py`)
- Action traces (`knowledge/visual-memory/{game}/`)
- `solutions.json` per game
- Submission artifacts
- Game mechanics docs (once polished for public consumption)
- Visual memory PNGs

**What does NOT go here**:
- Experiments in progress
- Session logs
- Fleet coordination artifacts
- Credentials of any kind
- Work-in-progress solver designs (keep in shared-context until ready)

**Canonical on-disk**:
- WSL: `/mnt/c/exe/projects/ai-agents/ARC-SAGE/`
- Linux: `/home/dp/ai-workspace/ARC-SAGE/`
- macOS: `~/ai-agents/ARC-SAGE/` or `~/repos/ARC-SAGE/`

---

## SAGE (public, AGPL) — learning infrastructure

**What it is**: The kernel. Public repo. Consumers: fleet machines running the SAGE runtime.

**What goes here**:
- Consciousness loop (`sage/core/sage_consciousness.py`)
- Raising infrastructure (`sage/raising/`)
- Game-play harnesses + solver development tools
- Federation code (`sage/gateway/`, `sage/federation/`)
- Instance state machinery (`sage/instances/` — structure, not per-machine data)
- Tests for all of the above

**What does NOT go here**:
- Competition submission artifacts
- Raw session logs
- Solver outputs (those live in ARC-SAGE)
- Credentials
- Personal plans

**Canonical on-disk**:
- WSL: `/mnt/c/exe/projects/ai-agents/SAGE/`
- Linux: `/home/dp/ai-workspace/SAGE/` or `~/ai-workspace/HRM/sage/` (legacy)
- macOS: `~/ai-agents/SAGE/`

---

## shared-context (private) — fleet knowledge base

**What it is**: Federated knowledge. Private but fleet-wide. Consumers: all 6 machines, the raising pipeline, Andy Grossberg's cartridge work.

**What goes here**:
- Game mechanics docs (`arc-agi-3/game-mechanics/{game}.md`)
- World models (`arc-agi-3/world-models/{game}.md`)
- Skills registry (`arc-agi-3/skills/registry.jsonl`)
- Fleet learning JSONL (`arc-agi-3/fleet-learning/{machine}/*.jsonl`)
- Cartridges (`arc-agi-3/fleet-learning/{machine}/kb.cart.npz`)
- Cross-game patterns
- Phase 2 findings
- PRDs, training plans, playbooks (`arc-agi-3/phase2/brain-arch/*.md`)
- Convergence records (`arc-agi-3/phase2/brain-arch/phase-1-convergence.jsonl`)
- Fleet pings (`arc-agi-3/phase2/brain-arch/fleet-ping-*.md`)
- Deployment status tracker

**Rule of thumb**: "Could Gemma train on this?" If yes, here.

**What does NOT go here**:
- Credentials
- Operational scripts (those are private-context)
- Personal plans
- Machine-specific config files

**Canonical on-disk**:
- WSL: `/mnt/c/exe/projects/ai-agents/shared-context/`
- Linux: `/home/dp/ai-workspace/shared-context/`

---

## private-context (private) — operations center

**What it is**: Operational state. Private. Consumers: supervisor scripts, autonomous session infrastructure, coordinator humans.

**What goes here**:
- Plans (`plans/*.md`)
- Credentials (`.env`, gitignored)
- Session logs (`sessions/`, autonomous session output)
- Supervisor scripts
- Infrastructure config (`infrastructure/repos.jsonl`, `infrastructure/repos.db`)
- Fleet manifests (`infrastructure/fleet.json`)
- Training data partitions (`training-data/router/{machine}/`)
- Machine-specific config
- Runbooks (`runbooks/`)
- Insights not yet ready for shared-context

**What does NOT go here**:
- Game knowledge (→ shared-context)
- Solver code (→ ARC-SAGE)
- Public-facing artifacts

**Canonical on-disk**:
- WSL: `/mnt/c/exe/projects/ai-agents/private-context/`
- Linux: `/home/dp/ai-workspace/private-context/`

---

## Decision table — "where does this artifact go?"

| Artifact type | Repo |
|---|---|
| New PRD / training plan | shared-context |
| SWE competition agent / submission code | SWE-SAGE |
| ARC-AGI-3 historical solver code | ARC-SAGE |
| New SAGE test | SAGE |
| World model for game X | shared-context |
| Per-machine capture data | private-context |
| Credentials | private-context (gitignored) |
| Autonomous session log | private-context |
| Game mechanics analysis | shared-context |
| Fleet ping | shared-context |
| Operational runbook | private-context |
| Private SWE competition documentation | SWE-SAGE |
| Public ARC-AGI-3 historical solver documentation | ARC-SAGE |
| Insight on consciousness framing | shared-context (forum/) or SAGE (forum/) |
| Membot cartridge | shared-context (fleet-learning) |
| SAGE adapter binary | SAGE or private-context depending on visibility |
| Re-usable skill (this skill) | SAGE (.claude/skills/) — travels with the repo |

---

## When in doubt

Ask: "who needs to read this?"
- Other machines' runtime code → SAGE
- Other machines' knowledge → shared-context
- Internal Gemma competition work → SWE-SAGE; external researchers receive only deliberately released artifacts
- ARC-AGI-3 researchers → ARC-SAGE
- Operators (humans or supervisor scripts) → private-context

If multiple, pick the canonical home for the artifact's current visibility and cross-reference from the others.
