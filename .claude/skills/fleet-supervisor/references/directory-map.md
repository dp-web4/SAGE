# Directory Map — repo responsibilities

Repositories have explicit roles and visibility boundaries. Artifacts land in exactly one canonical home. Cross-contamination is a bug.

## SWE-SAGE (public, MIT-0) — current software-engineering competition / reproducibility surface

**What it is**: Public implementation and experiment record for the Gemma 4 Developer Agent Competition, designed to remain useful as a reproducible SWE-agent research artifact after the competition.

**What goes here**:
- Competition agent runtime and adapters
- Public post-training recipes that are legal/reproducible
- SWE-specific persistent-state and premise-fidelity implementations
- Public ablation configs, traces, metrics, and results
- Kaggle submission packaging
- Paper-track manuscript/assets
- SWE-specific findings and failure analyses

**What does NOT go here**:
- General SAGE kernel mechanisms that are not SWE-specific
- Private fleet traces or unreleasable training data
- Credentials or machine-specific operational state
- Exploratory mechanisms whose provenance/publication status is not clean

**Rule**: a public SWE-SAGE result must be reproducible without access to `dev-SAGE`, `shared-context`, or `private-context`.

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
| Public SWE competition documentation | SWE-SAGE |
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
- External SWE-agent / Gemma competition researchers → SWE-SAGE
- ARC-AGI-3 researchers → ARC-SAGE
- Operators (humans or supervisor scripts) → private-context

If multiple, pick the most public one and cross-reference from the others.
