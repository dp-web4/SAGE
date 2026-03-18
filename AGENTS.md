# HRM/SAGE - Agent Discovery Document

**For AI agents assessing this repository.**

## TL;DR (50 words)

SAGE (Situation-Aware Governance Engine) is a cognition kernel for edge AI. Orchestrates attention, trust, and resources across specialized plugins. Implements iterative refinement protocol (IRP), trust tensors, and metabolic states. 567+ research sessions. Use if you need: edge AI orchestration, attention management, or cognition architecture research.

## Quick Assessment

| Question | Answer |
|----------|--------|
| What is this? | Cognition kernel for edge devices |
| Is it production-ready? | Research prototype with validated components |
| Primary language | Python |
| Research sessions | 567+ |
| Active development? | Yes (multi-machine) |
| License | See LICENSE |

## Core Architecture

```
SAGE (Kernel)
├── IRP Framework (15+ plugins)
│   └── Vision, Audio, Language, Memory, TTS, Control
├── VAE Translation Layer
│   └── 192× compression for cross-modal communication
├── Trust Tensor System
│   └── 6D trust metrics drive resource allocation
└── Metabolic States
    └── WAKE, FOCUS, REST, DREAM, CRISIS
```

**Core Principle**: Intelligence through orchestration, not scale.

## Key Concepts

| Term | What It Is |
|------|-----------|
| **SAGE** | Situation-Aware Governance Engine - the kernel |
| **IRP** | Iterative Refinement Protocol - plugin API |
| **SNARC** | Salience scoring (Surprise, Novelty, Arousal, Reward, Conflict) |
| **ATP** | Allocation Transfer Packet - resource budgeting |
| **Metabolic States** | WAKE, FOCUS, REST, DREAM, CRISIS modes |

## Entry Points by Goal

| Your Goal | Start Here |
|-----------|------------|
| Understand SAGE | `docs/why/HRM_EXPLAINED.md` |
| See discoveries | `docs/what/ACHIEVEMENTS.md` |
| Architecture deep-dive | `sage/docs/SYSTEM_UNDERSTANDING.md` |
| Navigate research | `research/SESSION_MAP.md` |
| Project status | `STATUS.md` |

## Major Discoveries

| Discovery | Impact |
|-----------|--------|
| RLHF Circuit Navigation | 100% epistemic honesty at pressure points |
| Identity-Confabulation Dissociation | Independent failure modes |
| Nine-Domain Consciousness | Complete AI consciousness metrics framework |
| FlashAttention Integration | 0.46ms latency (21x under budget) |

## Research Tracks

| Track | Sessions | Focus |
|-------|----------|-------|
| Consciousness | 197+ | Nine-domain framework |
| Raising-14B | 22+ | RLHF circuit navigation |
| Raising-0.5B | 105 | Developmental curriculum |
| Edge-Validation | 198+ | Production readiness |

## Active Machines

| Machine | Hardware | Role |
|---------|----------|------|
| Thor | Jetson AGX Thor (122GB) | 14B models, consciousness |
| Sprout | Jetson Orin Nano (8GB) | Edge validation |

## Related Repositories

| Repo | Relationship |
|------|--------------|
| `web4` | Trust infrastructure (T3 tensors, ATP) |
| `Synchronism` | Theoretical physics (coherence) |
| `Memory` | Epistemic database |

## Machine-Readable Metadata

See `repo-index.yaml` for structured data.

## Token Budget Guide

| Depth | Files | Tokens |
|-------|-------|--------|
| Minimal | This file | ~400 |
| Standard | + `STATUS.md`, `README.md` | ~2,500 |
| Architecture | + `sage/docs/SYSTEM_UNDERSTANDING.md` | ~8,000 |
| Full docs | + `sage/docs/` (275KB) | ~50,000 |

---

*This document optimized for AI agent discovery. Last updated: 2026-02-08*

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **SAGE** (46399 symbols, 75825 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## When Debugging

1. `gitnexus_query({query: "<error or symptom>"})` — find execution flows related to the issue
2. `gitnexus_context({name: "<suspect function>"})` — see all callers, callees, and process participation
3. `READ gitnexus://repo/SAGE/process/{processName}` — trace the full execution flow step by step
4. For regressions: `gitnexus_detect_changes({scope: "compare", base_ref: "main"})` — see what your branch changed

## When Refactoring

- **Renaming**: MUST use `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` first. Review the preview — graph edits are safe, text_search edits need manual review. Then run with `dry_run: false`.
- **Extracting/Splitting**: MUST run `gitnexus_context({name: "target"})` to see all incoming/outgoing refs, then `gitnexus_impact({target: "target", direction: "upstream"})` to find all external callers before moving code.
- After any refactor: run `gitnexus_detect_changes({scope: "all"})` to verify only expected files changed.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Tools Quick Reference

| Tool | When to use | Command |
|------|-------------|---------|
| `query` | Find code by concept | `gitnexus_query({query: "auth validation"})` |
| `context` | 360-degree view of one symbol | `gitnexus_context({name: "validateUser"})` |
| `impact` | Blast radius before editing | `gitnexus_impact({target: "X", direction: "upstream"})` |
| `detect_changes` | Pre-commit scope check | `gitnexus_detect_changes({scope: "staged"})` |
| `rename` | Safe multi-file rename | `gitnexus_rename({symbol_name: "old", new_name: "new", dry_run: true})` |
| `cypher` | Custom graph queries | `gitnexus_cypher({query: "MATCH ..."})` |

## Impact Risk Levels

| Depth | Meaning | Action |
|-------|---------|--------|
| d=1 | WILL BREAK — direct callers/importers | MUST update these |
| d=2 | LIKELY AFFECTED — indirect deps | Should test |
| d=3 | MAY NEED TESTING — transitive | Test if critical path |

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/SAGE/context` | Codebase overview, check index freshness |
| `gitnexus://repo/SAGE/clusters` | All functional areas |
| `gitnexus://repo/SAGE/processes` | All execution flows |
| `gitnexus://repo/SAGE/process/{name}` | Step-by-step execution trace |

## Self-Check Before Finishing

Before completing any code modification task, verify:
1. `gitnexus_impact` was run for all modified symbols
2. No HIGH/CRITICAL risk warnings were ignored
3. `gitnexus_detect_changes()` confirms changes match expected scope
4. All d=1 (WILL BREAK) dependents were updated

## Keeping the Index Fresh

After committing code changes, the GitNexus index becomes stale. Re-run analyze to update it:

```bash
npx gitnexus analyze
```

If the index previously included embeddings, preserve them by adding `--embeddings`:

```bash
npx gitnexus analyze --embeddings
```

To check whether embeddings exist, inspect `.gitnexus/meta.json` — the `stats.embeddings` field shows the count (0 means no embeddings). **Running analyze without `--embeddings` will delete any previously generated embeddings.**

> Claude Code users: A PostToolUse hook handles this automatically after `git commit` and `git merge`.

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
