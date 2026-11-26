# Machine Paths — per-machine filesystem conventions

Every machine has a different layout. Fleet-wide code that hardcodes one will break five.

## Conventions per platform

| Platform | Workspace root | Machines |
|---|---|---|
| WSL on Windows | `/mnt/c/exe/projects/ai-agents/` | CBP |
| WSL on Windows (alt) | `/mnt/c/projects/ai-agents/` | Nomad (when on Windows) |
| Linux | `/home/dp/ai-workspace/` | Legion, Sprout, Thor, Nomad (on Linux) |
| Linux (alt) | `~/ai-workspace/HRM/sage/` | Sprout legacy layout |
| macOS | `~/ai-agents/` | McNugget |
| macOS (alt) | `~/repos/` | McNugget alt layout |

Under any workspace root, the four repos appear as siblings: `SAGE/`, `ARC-SAGE/`, `shared-context/`, `private-context/`.

## Env var conventions

Preferred — let env vars override paths in fleet-wide code:

| Var | Purpose | Default behavior |
|---|---|---|
| `SAGE_ROUTER_DATA_DIR` | Router shadow partition root | resolve from workspace root |
| `SAGE_MACHINE` | Machine slug (cbp, thor, ...) | detect from hostname |
| `SAGE_MODEL` | Model override for this machine | default per machine-config |
| `SAGE_INSTANCE` | Explicit instance slug (`cbp-gemma3-4b`) | derive from `SAGE_MACHINE+SAGE_MODEL` |
| `ARC_SAGE_DIR` | ARC-SAGE repo root (for trace lookup) | fall back to search list |
| `SAGE_PRIVATE_CONTEXT_DIR` | private-context root | fall back to search list |

## Path resolution — the right pattern

For any fleet-wide code that needs a sibling repo:

```python
from pathlib import Path
import os

def _resolve_arc_sage() -> Path:
    # 1. Env var override
    if env := os.environ.get("ARC_SAGE_DIR"):
        return Path(env)
    # 2. Walk up from __file__ to find sibling
    here = Path(__file__).resolve()
    for parent in here.parents:
        sibling = parent.parent / "ARC-SAGE"
        if sibling.is_dir():
            return sibling
    # 3. Fallback search list covering known layouts
    for candidate in [
        Path("/mnt/c/exe/projects/ai-agents/ARC-SAGE"),
        Path("/mnt/c/projects/ai-agents/arc-sage"),
        Path.home() / "ai-workspace" / "ARC-SAGE",
        Path.home() / "ai-agents" / "ARC-SAGE",
        Path.home() / "repos" / "ARC-SAGE",
    ]:
        if candidate.is_dir():
            return candidate
    raise RuntimeError("ARC-SAGE repo not found; set ARC_SAGE_DIR env var")
```

Nomad shipped this pattern as a fix during the fleet gameplay capture run. It's the canonical template.

## Anti-patterns — things not to do

❌ `Path("/mnt/c/exe/projects/ai-agents/...")`  hardcoded in code
❌ Assuming `~` is dp's home
❌ Assuming daemon lives at a specific systemd unit path
❌ Assuming `ollama` is at a specific location
❌ Hardcoding the port number a daemon listens on

✅ Env vars first, fall-back search second, helpful error third.

## Daemon presence varies

Not every machine runs the router shadow daemon. Not every machine runs a raising daemon. Check before assuming:

```bash
curl -sf http://localhost:8750/health && echo "daemon up" || echo "no daemon"
pgrep -f "sage.*daemon"
```

If you need the daemon stopped (for exclusive memory, reproducible benchmark), stop it gracefully:

```bash
systemctl --user stop sage-daemon           # Sprout: the operator's user unit (Rust daemon)
# equivalent for other machines vary — check their runbook
```

Restart afterward. The daemon's absence interrupts session continuity.

## Account routing

CBP and Nomad (oversight pool, Account 2): `CLAUDE_ADMIN_TOKEN` in `/mnt/c/exe/projects/ai-agents/.env` or equivalent Linux path.

Thor, Sprout, Legion, McNugget (synthesis pool, Account 1): `CLAUDE_SYNTH_TOKEN`.

Never mix. Running synthesis-scale work on Account 2 burns the smaller budget fast (~40% in <1 day for one machine).

## Model defaults per machine

As of 2026-04-18:

| Machine | Default model |
|---|---|
| Thor | qwen3.5:27b |
| Sprout | qwen3.5:0.8b |
| Legion | gemma3:12b |
| McNugget | gemma3:12b |
| Nomad | gemma3:4b |
| CBP | gemma3:4b (was tinyllama:latest through 2026-04-17) |

Override per session with `SAGE_MODEL=...`.

## Instance directory

Each machine+model pair gets its own `sage/instances/{slug}/` dir:
- identity, experience buffer, sessions, training artifacts, sleep artifacts
- `SAGE_INSTANCE` overrides the default `{machine}-{model-slug}` resolution
- `_seed/` is the template for bootstrapping new instances
