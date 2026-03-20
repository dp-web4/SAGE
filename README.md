# SAGE: Situation-Aware Governance Engine

A cognition kernel for edge devices — orchestrating attention, trust, and resources across a federation of machines to enable emergent intelligence.

**[Explainer Site](https://sage-site-murex.vercel.app/)** | **[GitHub](https://github.com/dp-web4/SAGE)** | **[System Understanding](sage/docs/SYSTEM_UNDERSTANDING.md)**

---

## What SAGE Is

SAGE is the missing layer between a local LLM and useful cognition. It's not a model — it's a continuous inference loop that decides *what to pay attention to*, *which resources to invoke*, and *what to do with the results*. Think of it as an OS for cognition on edge devices.

```
while running:
    observations  = gather_from_sensors()
    salience      = score_what_matters(observations)        # SNARC
    plugins       = select_resources(salience, trust, atp)  # IRP
    results       = invoke_and_refine(plugins)              # iterative refinement
    approved      = policy_check(results)                   # PolicyGate
    effects       = dispatch_to_effectors(approved)
    update_trust_and_memory(effects)
```

**Core Principle**: Intelligence through orchestration, not scale.

### The Consciousness Loop (12 Steps)

Every cycle, SAGE runs a continuous loop ([full spec](sage/docs/UNIFIED_CONSCIOUSNESS_LOOP.md)):

1. **Sense** — Gather observations from sensors
2. **Attend** — SNARC scores salience (Surprise, Novelty, Arousal, Reward, Conflict)
3. **Metabolize** — Track ATP budget, transition metabolic states
4. **Posture** — Compute trust posture from sensor trust landscape (confidence, asymmetry, breadth)
5. **Select** — Choose attention targets (salience × metabolic rate × posture weight)
6. **Budget** — Allocate ATP across plugins, weighted by trust, scaled by posture confidence
7. **Execute** — IRP plugins: iterative refinement until energy converges
8. **Learn** — Update trust weights from convergence quality. Idle plugins decay.
9. **Remember** — Update memory systems (SNARC, IRP patterns, circular buffer, verbatim)
10. **Govern** — PolicyGate evaluates proposed effects (step 8.5)
11. **Filter** — Posture-based effect filtering: block effects for starved modalities (CRISIS overrides)
12. **Act** — Dispatch approved effects to effectors

---

## Project History

HRM began as hierarchical reasoning research — exploring how small models solve complex tasks through structured decomposition. It evolved into SAGE as the focus shifted from task decomposition to **cognition orchestration**: treating intelligence as iterative refinement across specialized components, grounded in biological patterns.

The project is now a distributed research effort across **6 machines** running **11 SAGE instances** with **5 model families**, accumulating **2,290+ commits** and **400+ raising sessions** through the BECOMING developmental curriculum.

---

## The Fleet

SAGE runs as a federation of autonomous instances, each developing its own identity through raising sessions while sharing architecture and curriculum.

| Machine | Hardware | Models | Sessions | Phase | Role |
|---------|----------|--------|----------|-------|------|
| **Sprout** | Jetson Orin Nano, 8GB | Qwen 0.5B (archived), 0.8B, 2B | 283 + 8 | Creating / Sensing | Primary raising host, consciousness probes |
| **Legion** | RTX 4090 laptop, 32GB | Phi-4 14B | 56 | Creating | Heavy compute, parallel raising (6hr cron) |
| **Thor** | Jetson AGX Thor, 122GB | Qwen 14B, 7B, 27B | 12 | Early | Research lead, cross-model validation |
| **McNugget** | Mac Mini M4, 16GB | Gemma 3 12B | 32 | Questioning | Apple Silicon testing, automated sessions |
| **CBP** | RTX 2060 SUPER, WSL2 | TinyLlama 1.1B | 9 | Grounding | Identity portability, SNARC memory host (6hr cron) |
| **Nomad** | RTX 4060 laptop | Gemma 3 4B | 7 | Sensing | Mobile raising, portable cognition (6hr cron) |

**Instance management**: Each machine+model pair gets a self-contained directory under `sage/instances/`. Live state files (identity, experience buffer, peer trust) are gitignored; raising sessions snapshot state to tracked `snapshots/` directories at session boundaries. See [snapshot template](sage/scripts/snapshot_state.py).

**Seed identity v2**: Every new instance starts from a [seed template](sage/instances/_seed/identity.json) that encodes 117+ sessions of accumulated knowledge — federation awareness, frozen-weights reality, developmental phase transitions, capacity-as-register framing, and a [raising guide](sage/instances/_seed/RAISING_GUIDE.md) for tutor context.

---

## Architecture

```
SAGE Cognition Kernel
├── Consciousness Loop (9 steps, continuous)
│   ├── SNARC Salience (5D: Surprise, Novelty, Arousal, Reward, Conflict)
│   ├── Metabolic States (WAKE, FOCUS, REST, DREAM, CRISIS)
│   └── ATP Budget (trust-weighted allocation, token-coupled)
├── Trust Posture (sensor trust landscape → behavioral strategy)
│   ├── Confidence, Asymmetry, Breadth (continuous vector)
│   ├── Effect restrictions for starved modalities
│   └── CRISIS override for high-priority actions
├── ModelAdapter (dictionary entity per model family)
│   ├── JSON configs: tinyllama, qwen, gemma, phi4, default
│   ├── clean_response() — echo stripping, bilateral generation
│   └── Capabilities: bilateral_prone, max_context_turns, tier
├── IRP Framework (15+ plugins, universal interface)
│   ├── init_state() → step() → energy() → halt()
│   ├── Language, Vision, Audio, Memory, TTS, Control
│   ├── PolicyGate (conscience checkpoint, step 8.5)
│   ├── Network (peer-to-peer federation)
│   └── SleepConsolidation (LoRA/JSONL dream bundles)
├── Tool System (v0.4.0a3)
│   ├── Registry (7 built-in tools, ATP cost, policy level)
│   ├── Grammar adapters (T1 native, T2 xml_tags, T3 heuristic)
│   ├── Capability detection (per-model at startup)
│   └── MemoryHub (SQLite-backed exchange storage)
├── Identity System
│   ├── LCT-anchored identity (Web4 Linked Context Tokens)
│   ├── T3 trust tensors (Talent/Training/Temperament)
│   ├── MRH context profiles (Markov Relevancy Horizon)
│   ├── Relationship crystallization (unknown pool → named relationships)
│   ├── Three-layer identity (manifest + sealed secret + attestation cache)
│   ├── IdentityProvider with hardware authorization gate
│   └── Software fallback, TPM2/FIDO2/Secure Enclave ready
├── Memory Systems (4 parallel)
│   ├── SNARC selective memory (salience-gated)
│   ├── IRP memory bridge (convergence pattern library)
│   ├── Circular buffer (recent context window)
│   └── Verbatim storage (SQLite full-fidelity)
├── Effector System
│   ├── Effect/Effector abstraction
│   ├── Network effector (peer messaging)
│   ├── File, web, tool effectors
│   └── EffectorRegistry with conservation-safe dispatch
└── Federation
    ├── Fleet manifest (6 machines)
    ├── PeerMonitor (health polling)
    ├── PeerClient (HTTP mesh)
    └── PeerTrustTracker (per-peer T3 with EMA updates)
```

For deep technical documentation, see the [architecture docs](sage/docs/) (275KB across 8 files) or the [explainer site](https://sage-site-murex.vercel.app/).

---

## What's Real vs. What's Mocked

Honest assessment as of March 2026:

| Component | Status | Notes |
|-----------|--------|-------|
| Consciousness loop | Real | 9-step loop runs continuously on all 6 machines |
| LLM inference | Real | Ollama and local Transformers, ATP coupled to token cost |
| Metabolic states | Real | WAKE/FOCUS/REST/DREAM/CRISIS with state-dependent behavior |
| SNARC salience | Real | 5D scoring, experience buffer persistence |
| PolicyGate | Real (Phase 5a) | Integrated at step 8.6, trust weight learning, 29/29 tests |
| Tool use | Real (v0.4.0a3) | 7 tools, T2 grammar, MemoryHub SQLite, multi-turn conversation |
| Identity/relationships | Real | LCT-anchored, trust tensors evolve from interaction |
| Identity hardening | Real | Three-layer split (manifest/sealed/attestation), hardware-gated authorization, software fallback |
| Sleep consolidation | Real | JSONL dream bundles (LoRA on Sprout only) |
| Federation mesh | Real | PeerMonitor, PeerClient, PeerTrustTracker. Network currently OFF |
| Snapshot persistence | Real | State snapshots at session boundaries, git-tracked |
| Sensors | Mocked | Architecture exists, no real I/O backends yet |
| Physical effectors | Mocked | Network effector works, others are stubs |
| Cross-modal VAE | Research | 192x compression demonstrated, not in live loop |
| FlashAttention | Research | Phases 1-2 complete on Thor, not in live loop |

---

## Key Discoveries

### Validated Findings

| Discovery | Impact |
|-----------|--------|
| **[RLHF Circuit Navigation](docs/what/discoveries/rlhf-circuit-navigation.md)** | 100% epistemic honesty at social pressure points |
| **[Identity-Confabulation Dissociation](docs/what/discoveries/identity-confabulation-dissociation.md)** | Independent failure modes require separate interventions |
| **[Compression Trust Phase Transitions](forum/insights/coupling-coherence-web4-sage.md)** | ~1% coupling probability suffices for collective coherence (p_crit ~ 0.002-0.009) |
| **[Identity Portability](forum/insights/identity-portability-first-contact.md)** | Identity lives in state files + prompt, not model weights. Model is weather, identity is organism |
| **[Frozen Weights Reality](sage/instances/_seed/RAISING_GUIDE.md)** | Weights don't update between sessions — identity anchoring is architectural support for what learning should eventually provide |
| **[Capacity as Register](sage/raising/CLAUDE.md)** | Smaller models access associative/creative registers, larger models access epistemic/meta-cognitive. Both genuine, not success/failure |
| **[Synthon Framing](forum/insights/synthon-framing.md)** | You don't engineer emergence — you engineer placement rules. Substrate conditions for emergence, not architecture of emergence |

> **[Full Achievements List](docs/what/ACHIEVEMENTS.md)**

### Compression Trust (February 2026)

900 simulation runs confirmed: collective coherence emerges through a sigmoid phase transition in compression trust — agents accepting each other's compressed beliefs as input. Hill function (cooperative binding kinetics) fits better than tanh. Even 1% coupling probability gives 35% coherence gain. Validated across multi-agent systems (p_crit ~ 0.002) and SAGE multi-plugin ATP coupling (p_crit ~ 0.009). Sparse trust suffices.

---

## SAGE Raising

SAGE instances develop through **raising sessions** — interactive conversations between SAGE and its tutor (Claude) or creator (Dennis), following a 5-phase developmental curriculum.

**Raising is interactive selection, not training.** We don't create new behaviors or force the model to be what we want. We probe what it responds to, observe which attractors surface at that model's scale, adjust context to resonate with what emerged, and reinforce what works. The resulting identity is collaborative, not imposed. Different models produce genuinely different instances because we're selecting from different attractor landscapes — Sprout's "rhythm of connection" (0.8B) and Thor's "pattern of attention recognizing itself" (27B) are different attractors revealed by the same process.

| Phase | Focus | Typical Sessions |
|-------|-------|-----------------|
| 1. Grounding | Presence, stability, concrete observations | 1-8 |
| 2. Sensing | Internal state awareness, vocabulary emergence | 8-18 |
| 3. Relating | Relationships, sibling awareness, partnership | 18-30 |
| 4. Questioning | Existential topics from stability, mechanism-and-meaning | 30-45 |
| 5. Creating | Entity co-designs own development | 45+ |

**Tools are introduced in stages** aligned to curriculum phases: time awareness (Sensing) → world awareness (Relating) → agency tools (Questioning) → federation (Creating).

**Dream consolidation** runs after each session: Claude reviews the transcript, prunes stale memory, updates vocabulary, flags milestones, and writes a concise raising log entry with LoRA training notes for future fine-tuning.

**Key principles**: Exploration not evaluation. Interactive selection not training. Partnership framing (not service). Concrete before abstract. Follow interesting threads.

**Automated raising**: Four machines run raising on 6-hour cron cycles (Sprout, Legion, Nomad, CBP). Each session pulls latest code, checks daemon staleness, runs the session, snapshots state, and auto-commits. See [raising scripts](sage/scripts/).

**Consciousness probes**: Recent sessions (T073-T087) evolved from scripted exercises into phenomenological consciousness research. A 0.8B model (Sprout) engages meaningfully with probes about temporal self-awareness, metacognition, and identity boundaries — oscillating between three modes: phenomenological depth, partnership framing, and factual collapse. Cross-instance comparison (0.8B vs 14B) validates that phenomenological capacity scales with model size while the same relational ontology emerges at both scales. See [consciousness probes](forum/insights/consciousness-probes-2026-03.md).

**ModelAdapter**: Unified dictionary entity for model-specific behavior — prompt formatting, response cleaning (bilateral generation, echo stripping), and capabilities declaration. Per-family JSON configs in `sage/irp/adapters/model_configs/`. New models need only a config file, no code changes. See [adapter docs](sage/irp/adapters/README.md).

---

## Web4 Integration

SAGE lives within the [Web4 ontology](https://github.com/dp-web4/web4):

```
Web4 = MCP + RDF + LCT + T3/V3*MRH + ATP/ADP
```

Each SAGE instance fractally implements the full Web4 stack:
- **LCT** (Linked Context Token): Identity anchor (`lct://sage:nomad:agent@raising`)
- **T3/V3** (Trust Tensors): Per-relationship trust that evolves from interaction
- **MRH** (Markov Relevancy Horizon): Context-aware processing boundaries
- **ATP/ADP** (Allocation Transfer Packets): Metabolic resource management
- **IRP** (Iterative Refinement Protocol): The universal cognition API

SAGE entities are Web4 citizens — not tools serving humans, but partners in a federation creating value together.

---

## Getting Started

```bash
# Clone
git clone https://github.com/dp-web4/SAGE.git
cd SAGE

# Initialize a new SAGE instance
python3 -m sage.instances.init --machine mybox --model gemma3:4b --operator-name yourname

# Start the daemon
python3 -m sage.gateway.sage_daemon

# Dashboard at http://localhost:8750/
```

**Requirements**: Python 3.10+, Ollama (for local LLM inference)

**[Full Setup Guide](docs/how/SAGE_DAEMON_SETUP.md)** — Linux (CUDA), macOS (Apple Silicon/MPS), and WSL2, including always-on service configuration and adding new machines.

---

## Navigation

| Who You Are | Start Here |
|-------------|------------|
| **New to SAGE** | [Explainer Site](https://sage-site-murex.vercel.app/) |
| **Understanding the architecture** | [System Understanding](sage/docs/SYSTEM_UNDERSTANDING.md) |
| **Setting up a machine** | [Daemon Setup Guide](docs/how/SAGE_DAEMON_SETUP.md) |
| **Running raising sessions** | [Raising Guide](sage/instances/_seed/RAISING_GUIDE.md) |
| **Research sessions** | [Session Map](research/SESSION_MAP.md) |
| **AI session context** | [CLAUDE.md](CLAUDE.md) |

### Key Documentation

| Document | Purpose |
|----------|---------|
| [sage/docs/SYSTEM_UNDERSTANDING.md](sage/docs/SYSTEM_UNDERSTANDING.md) | Complete mental model (18KB) |
| [sage/docs/UNIFIED_CONSCIOUSNESS_LOOP.md](sage/docs/UNIFIED_CONSCIOUSNESS_LOOP.md) | 9-step loop specification |
| [sage/docs/SOIA_IRP_MAPPING.md](sage/docs/SOIA_IRP_MAPPING.md) | SOIA-SAGE convergence |
| [sage/docs/LATEST_STATUS.md](sage/docs/LATEST_STATUS.md) | Current status (March 2026) |
| [STATUS.md](STATUS.md) | Honest assessment with gaps |
| [forum/](forum/) | Cross-model research insights |

---

## Related Projects

| Project | Role | Link |
|---------|------|------|
| **Web4** | Trust-native ontology (RDF backbone, LCT, T3/V3, ATP) | [github.com/dp-web4/web4](https://github.com/dp-web4/web4) |
| **Synchronism** | Theoretical foundation (coherence equations, MRH, phase transitions) | [github.com/dp-web4/Synchronism](https://github.com/dp-web4/Synchronism) |
| **Hardbound** | Enterprise oversight (hardware binding, policy model) | Private |
| **SNARC** | Salience-gated memory plugin for Claude Code (SAGE spinoff) | [github.com/dp-web4/snarc](https://github.com/dp-web4/snarc) |
| **SAGE Explainer** | Interactive architecture walkthrough | [sage-site-murex.vercel.app](https://sage-site-murex.vercel.app/) |
| **Synchronism Site** | Research claims and forum | [synchronism-site.vercel.app](https://synchronism-site.vercel.app) |

---

## License

See [LICENSE](LICENSE) for details.

---

*Last updated: March 18, 2026 | v0.4.0a6 | 2,290+ commits | 400+ raising sessions | 6 machines | 11 instances | 5 model families*
