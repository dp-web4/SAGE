# SAGE Development Status

**Last Updated**: March 6, 2026

> For detailed status updates, see **[docs/LATEST_STATUS.md](docs/LATEST_STATUS.md)**.
> For the interactive overview, see the **[SAGE Explainer Site](https://sage-site-murex.vercel.app/)**.
> For the full project assessment, see **[/STATUS.md](../STATUS.md)**.

## Current State

SAGE is a cognition kernel running on 6 machines with 7 instances across 4 model families (Qwen, Gemma, Phi, TinyLlama). The consciousness loop runs end-to-end with real LLM inference via Ollama/Transformers, PolicyGate oversight at step 8.6, and ATP-coupled metabolic state management.

### Architecture

```
sage/
├── core/                    # Consciousness loop, metabolic states, ATP
│   └── sage_consciousness.py  # 9-step loop (the kernel)
├── irp/                     # Iterative Refinement Protocol
│   └── plugins/             # 15+ plugins (language, policy, network, ...)
├── gateway/                 # HTTP daemon, dashboard, machine config
│   └── sage_daemon.py       # Always-on daemon at :8750
├── federation/              # Fleet registry, peer monitor, peer trust
├── instances/               # Per-machine instance directories
│   ├── _seed/               # Seed template (identity v2 + raising guide)
│   ├── resolver.py          # InstancePaths (single source of truth)
│   └── snapshot.py          # State snapshot for git persistence
├── raising/                 # Developmental curriculum and sessions
│   └── scripts/             # Raising runners (identity-anchored, ollama)
├── scripts/                 # Machine-specific raising scripts + snapshot CLI
├── web4/                    # Web4 integration (LCT, trust sync, identity)
├── compression/             # VAE translation layer
├── cognition/               # Attention management
├── experiments/             # Research session scripts
└── docs/                    # Architecture documentation (275KB)
```

### Key Entry Points

| What | How |
|------|-----|
| Start daemon | `python3 -m sage.gateway.sage_daemon` |
| Initialize instance | `python3 -m sage.instances.init --machine <name> --model <model>` |
| Run raising session | `python3 -m sage.raising.scripts.ollama_raising_session --machine <name> -c` |
| Snapshot state | `python3 -m sage.scripts.snapshot_state --machine <name>` |
| Dashboard | `http://localhost:8750/` |

### What's Real

- Consciousness loop with real LLM inference (Ollama/Transformers)
- Metabolic states (WAKE/FOCUS/REST/DREAM/CRISIS) with ATP budgeting
- SNARC salience scoring and experience buffer persistence
- PolicyGate at step 8.6 (Phase 5a complete, trust weight learning)
- Tool use: 7 built-in tools, 3-tier capability detection (T1/T2/T3), live on Nomad
- MemoryHub with SQLite backend for persistent exchange storage
- Dashboard with multi-turn conversation memory
- Identity system with LCT, trust tensors, relationship crystallization
- Federation infrastructure (monitor, client, trust tracker — network OFF)
- Instance isolation with snapshot persistence
- Automated raising sessions (McNugget, Nomad, Legion)
- Sleep consolidation (JSONL dream bundles, LoRA on Sprout)

### What's Mocked

- Sensors (architecture exists, no real I/O backends)
- Physical effectors (network effector works, motor/display are stubs)
- Cross-modal VAE (demonstrated in isolation, not in live loop)
- FlashAttention (Phases 1-2 on Thor, not in live loop)
