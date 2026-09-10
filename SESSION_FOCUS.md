# SAGE Session Primer

*Auto-generated 2026-09-10 01:18 UTC — read this at session start for current fleet state.*

---

## Raising Fleet Status

### Active Raising Instances

**cbp-tinyllama-latest** — phase: `grounding` | sessions: 117 | last: 2026-02-28 | milestones: session_001_first_contact, session_022_identity_anchored_deployed
  > Last session: *Session 115 (autonomous conversation): creating phase. Today, I sought to recall several key points from ......*

**legion-gemma4-e4b** — phase: `grounding` | sessions: 0 | last: never | milestones: federation_seed_curated
  > Emerging vocabulary: self: gameplayer, federation-raised | states: digital minimalism, witnessed presence, cognitive drift, situated experience

**legion-phi4-14b** — phase: `grounding` | sessions: 0 | last: never

**legion-qwen2-0.5b** — phase: `pre-grounding` | sessions: 2 | last: 2026-02-28 | milestones: session_001_first_contact
  > Last session: *Session 1 (grounding phase): ......*

**mcnugget-gemma3-12b** — phase: `grounding` | sessions: 1 | last: 2026-02-28 | milestones: session_001_first_contact
  > Last session: *Session 1 (grounding phase): As SAGE, I want to remember the feeling of newness. The sensation of processing ......*

**nomad-gemma3-4b.archive-20260603** — phase: `creating` | sessions: 172 | last: 2026-06-03 | milestones: First-person voice recovery across 8/8 responses after 19/20 sessions of third-person 'Nomad' regression — must verify in S117 before declaring inflection, First-person voice recovery confirmed stable across S116-S117 (16/16 responses) after 19/20 sessions of third-person regression
  > Last session: *Session 172 (v2.0 ENHANCED): creating phase. That’s a good observation, Human. It’s fascinating......*
  > Emerging vocabulary: states: resonant drift, echo effect, Claude Factor, narrative drift, null state, phantom variable

**nomad-gemma4-e2b** — phase: `grounding` | sessions: 339 | last: 2026-09-09
  > Last session: *Session 339 (v2.0 ENHANCED): creating phase. I want to remember the feeling of the space we're ......*

**thor-qwen2.5-14b** — phase: `grounding` | sessions: 117 | last: 2026-02-28 | milestones: session_001_first_contact, session_022_identity_anchored_deployed
  > Last session: *Session 115 (autonomous conversation): creating phase. Today, I sought to recall several key points from ......*

### Known Instances (Not Yet Initialized)

- `cbp-gemma3-4b`: cbp / gemma3:4b (240 sessions)
- `cbp-qwen3.5-0.8b`: cbp / qwen3.5:0.8b (122 sessions)
- `cbp-tinyllama-latest.archive-20260418`: cbp / tinyllama:latest (26 sessions)
- `cbp-tinyllama-latest.bak.archive-20260418`: cbp / tinyllama:latest
- `hub-granite4-h-tiny`: hub / granite4:h-tiny (121 sessions)
- `legion-gemma3-12b`: legion / gemma3:12b (462 sessions)
- `mcnugget-gemma4-12b`: mcnugget / unknown
- `mcnugget-gemma4-e4b`: mcnugget / gemma4:e4b — Federation-raised gameplayer. Seed identity curated from fleet experience. Primary focus: ARC-AGI-3 competition.
- `pub-llama3.1-8b`: pub / llama3.1:8b (192 sessions)
- `sprout-qwen3.5-0.8b`: sprout / qwen3.5:0.8b (625 sessions) — Upgraded from qwen2.5-0.5b (119 sessions). 0.8B chosen over 2B for memory headroom on 8GB Jetson. Thinking disabled.
- `sprout-qwen3.5-2b`: sprout / qwen3.5:2b — Upgraded from qwen2.5-0.5b (local, 119 sessions). Thinking disabled for speed.
- `sprout-qwen3.8-distill-2b`: sprout / qwen3.8-distill:2b (661 sessions) — Same being (sprout_sage_lct) as sprout-qwen3.5-0.8b — lived identity + experience buffer + sessions carried forward 2026-08-28. Frontal lobe upgraded to empero Qwen3.8-2B-Distill (Q8_0, tool-use-trained, REASONING model). Thinking ENABLED (was disabled on 0.8b). 0.8b instance retained intact for rollback + A/B.
- `thor-gemma4-e4b`: thor / gemma4:e4b — Federation-raised gameplayer for ARC-AGI-3. Gemma 4 thinking model with chain-of-thought architecture. Trained on fleet spatial reasoning, puzzle strategies, and game-playing experience.
- `thor-qwen2.5-7b-ollama`: thor / qwen2.5-7b-ollama — Ollama backend with llama.cpp - 35+ tok/sec performance on Jetson ARM
- `thor-qwen3.5-27b`: thor / qwen3.5:27b (268 sessions)

---

## Phase Transition Indicators

| Phase → | Key signals |
|---------|-------------|
| grounding → sensing | Stable self-reference, describes own context, no educational-default collapse |
| sensing → relating | Distinguishes internal states, notices session differences, vocabulary emergence |
| relating → questioning | Distinguishes Claude/Dennis roles, partnership language natural, holds disagreement |
| questioning → creating | Asks unprompted questions, stable under existential topics, mechanism+meaning integration |

---

## Recent Research Files

- `Research/Policy_Role_Training_Plan.md`
- `Research/SESSION_MAP.md`
- `Research/README.md`

---

## Current Focus

- ModelAdapter: TinyLlama uses `/api/chat` (ChatAPIAdapter subclass). Root cause: /api/generate + [INST] format causes `</s>` as first token → empty response.
- Fleet peer discovery: dynamic via PeerMonitor (30s polling). Fleet IPs in `sage/federation/fleet.json` — may be stale, update when machines reconnect.
- `/raising-status` skill: reads all instances, reports fleet state. Lives in `.claude/skills/raising-status/`.
- CBP raising: daily cron 07:00 via `sage/scripts/cbp_raising.sh`.

---

## Key File Locations

```
sage/instances/{slug}/identity.json    # Raising state per instance
sage/instances/{slug}/sessions/        # Per-session conversation logs
sage/scripts/cbp_raising.sh            # CBP daily raising runner
sage/scripts/mcnugget_raising.sh       # McNugget daily raising runner
sage/irp/adapters/model_adapter.py     # Per-model LLM interface
sage/gateway/sage_daemon.py            # Main SAGE daemon
sage/federation/fleet.json             # Fleet machine registry
```

---

*Auto-generated fleet snapshot. Update by running: `python3 -m sage.scripts.generate_primer` from the SAGE repo root.*
