# SAGE Rust Daemon — Cutover Guide

How to replace the Python `sage.gateway` daemon with the Rust `sage-daemon` binary on any fleet machine.

## What Changes

| Component | Before (Python) | After (Rust) |
|-----------|-----------------|--------------|
| Binary | `python3 -m sage.gateway` | `sage-rs/target/release/sage-daemon` |
| Port | 8750 | 8760 |
| RSS | ~400-580 MB | ~8-12 MB |
| Dashboard | Python Jinja templates | Embedded HTML at `/` |
| Consciousness loop | Python async (12-step) | Tokio async (~10Hz tick) |
| Federation | Python PeerMonitor/PeerClient | Rust PeerMonitor (30s poll) + PeerClient |
| Experience buffer | `experience_buffer.json` (JSON array) | `experience_buffer_rs.jsonl` (JSONL append) |
| Trust persistence | `peer_trust_{machine}.json` | `peer_trust_rs.json` |
| Startup time | ~15s (model load + Python) | ~5s (no model load, Ollama is separate) |

## What Stays the Same

- **Raising scripts** — still Python, talks directly to Ollama on 11434
- **Chat history** — `chat_history.jsonl` still written by raising scripts via `append_chat_message()`
- **Identity files** — same `identity.json` / `identity.sealed` / `identity.attest.json`
- **Fleet manifest** — same `sage/federation/fleet.json`
- **Ollama** — untouched, still serves models on 11434

## Prerequisites

- Rust toolchain (`rustup` installed, stable channel)
- Ollama running with the machine's default model
- SSH key loaded for `git push` (no PAT)
- `fleet.json` at `sage/federation/fleet.json`

## Step-by-Step Cutover

### 1. Build the Rust binary

```bash
cd ~/ai-workspace/SAGE/sage-rs
cargo build --release
```

On Jetson aarch64 this takes ~60s first time, ~20s incremental. The binary lands at `sage-rs/target/release/sage-daemon`.

### 2. Test it manually

```bash
# Start on port 8760 (won't conflict with Python on 8750)
SAGE_MODEL=qwen3.5:0.8b ./target/release/sage-daemon &

# Verify
curl http://localhost:8760/health
curl http://localhost:8760/status
curl http://localhost:8760/peers
curl -X POST http://localhost:8760/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "hello"}'

# Dashboard
# Open http://<machine-ip>:8760/ in browser

# Kill the test instance
kill %1
```

### 3. Stop and disable the Python systemd service

On Sprout this is done: the Rust daemon runs as the operator's user unit `sage-daemon.service`, and the old
system unit `sage-daemon-sprout.service` was removed from the tree (#835). On another machine, stop and disable
whatever unit runs its Python daemon.

### 4. Install the Rust systemd service

Edit `sage-rs/sage-daemon.service` for the target machine:

```ini
# Change these per machine:
ExecStart=/home/<user>/ai-workspace/SAGE/sage-rs/target/release/sage-daemon
WorkingDirectory=/home/<user>/ai-workspace/SAGE
Environment=SAGE_MODEL=<model>      # e.g. gemma3:12b, qwen3.5:27b
Environment=SAGE_MACHINE=<machine>  # e.g. thor, legion, nomad — required for non-sprout machines
User=<user>
```

**As of Sprint 7 (CBP, 2026-06-06)**: `SAGE_MACHINE` is honored and drives instance-dir + self_machine resolution. Per-path explicit overrides (`SAGE_ROOT`, `SAGE_FLEET_JSON`, `SAGE_EXPERIENCE_PATH`, `SAGE_TRUST_PATH`) are available if the defaults aren't right; defaults walk up from the binary location to find `<SAGE_ROOT>/sage/federation/fleet.json` and use `sage/instances/{machine}-{model_with_dashes}/...` for per-instance files. **No main.rs edit needed** — the same binary is now multi-machine. Sprout's existing deploy keeps working with `SAGE_MACHINE=sprout` (or no env at all — sprout is the documented default for backward-compat).

Install:

```bash
sudo cp sage-rs/sage-daemon.service /etc/systemd/system/sage-daemon-sprout.service
sudo systemctl daemon-reload
sudo systemctl enable sage-daemon-sprout
sudo systemctl start sage-daemon-sprout
```

Verify:

```bash
sudo systemctl status sage-daemon-sprout
curl http://localhost:8760/health
journalctl -u sage-daemon-sprout -f
```

### 5. Update the raising cron script

The raising script (`sage/scripts/<machine>_raising.sh`) needs two changes:

**Health check port**: `8750` → `8760`

```bash
# Before
if ! curl -s http://localhost:8750/health >/dev/null 2>&1; then

# After
if ! curl -s http://localhost:8760/health >/dev/null 2>&1; then
```

**Stale-daemon check**: The Rust binary doesn't need "stale code" restarts — it's a compiled binary, not interpreted Python. Simplify to just ensure it's running:

```bash
if ! systemctl is-active --quiet sage-daemon-sprout; then
    sudo systemctl start sage-daemon-sprout
    sleep 8
fi
```

**Git push**: Switch from deprecated PAT to SSH:

```bash
# Before
PAT=$(grep GITHUB_PAT ...)
git push "https://dp-web4:${PAT}@github.com/dp-web4/SAGE.git" main

# After
git push origin main
```

### 6. Verify raising still works

```bash
# Run a manual raising session
cd ~/ai-workspace/SAGE
python3 -m sage.raising.scripts.ollama_raising_session --machine sprout -c
```

The raising session talks directly to Ollama (11434), not the daemon. The daemon is only used for:
- Health check in the cron wrapper
- Chat history appended by the raising script (via Python import, not HTTP)
- Metabolic state for status display

### 7. Remove the router-shadow drop-in (optional)

If the machine has a Python-era router-shadow drop-in:

```bash
sudo rm /etc/systemd/system/sage-daemon-sprout.service.d/router-shadow.conf
sudo systemctl daemon-reload
sudo systemctl restart sage-daemon-sprout
```

The `SAGE_ROUTER_SHADOW` env var is ignored by the Rust binary.

## Per-Machine Defaults

| Machine | Model | Port | Device |
|---------|-------|------|--------|
| sprout | qwen3.5:0.8b | 8760 | Jetson Orin Nano |
| thor | qwen3.5:27b | 8760 | Jetson AGX Thor |
| legion | gemma3:12b | 8760 | RTX 4090 desktop |
| mcnugget | gemma3:12b | 8760 | Mac Mini M4 |
| nomad | gemma3:4b | 8760 | RTX 4060 laptop |
| cbp | gemma3:4b | 8760 | RTX 2060S WSL2 |

Override the model at runtime: `SAGE_MODEL=phi4:latest` in the systemd service or environment.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | HTML dashboard |
| GET | `/health` | Health check (uptime, model, Ollama status) |
| GET | `/status` | Full status (metabolic state, ATP, cycles, fleet) |
| POST | `/chat` | Send message through consciousness loop |
| POST | `/stream` | SSE token-by-token streaming |
| GET | `/peers` | Fleet peers with live online/offline status |
| POST | `/delegate` | Forward message to a named peer |
| POST | `/snarc/observe` | Direct SNARC observation (external sensors) |
| POST | `/metabolic/cycle` | Direct metabolic cycle (external tools) |

## Paths (Sprint 7: env-var driven)

Defaults are derived from `SAGE_MACHINE` + `SAGE_MODEL`, rooted at `SAGE_ROOT` (which defaults to walking up four parents from the binary location to find `<root>/sage/federation/fleet.json`):

```
SAGE_ROOT/sage/federation/fleet.json                                          # fleet manifest
SAGE_ROOT/sage/instances/{machine}-{model_with_dashes}/experience_buffer_rs.jsonl
SAGE_ROOT/sage/instances/{machine}-{model_with_dashes}/peer_trust_rs.json
```

Per-path explicit overrides if the defaults aren't right:

| env var | overrides |
|---|---|
| `SAGE_ROOT` | The walk-up root detection |
| `SAGE_FLEET_JSON` | Full path to fleet manifest |
| `SAGE_EXPERIENCE_PATH` | Full path to experience buffer JSONL |
| `SAGE_TRUST_PATH` | Full path to peer trust JSON |

**Same binary, all machines.** No `main.rs` edit needed.

Backward-compat: if `SAGE_MACHINE` is unset, the binary defaults to `sprout` (with a warning) so Sprout's existing systemd service continues working without modification.

## Rollback

If something breaks:

```bash
sudo systemctl stop sage-daemon-sprout
# Re-enable Python daemon:
sudo cp <original-python-service> /etc/systemd/system/sage-daemon-sprout.service
sudo systemctl daemon-reload
sudo systemctl start sage-daemon-sprout
# Revert raising script port back to 8750
```

## Monitoring

```bash
# Live logs
journalctl -u sage-daemon-sprout -f

# RSS check
ps -o pid,rss,comm -p $(pgrep sage-daemon)

# Consciousness loop stats (in journal output)
# cycle=100 state=wake ATP=69.0 msgs=0 exp=0

# Graceful shutdown test
sudo systemctl stop sage-daemon-sprout
# Should print "=== Consciousness Loop Summary ===" in journal
```
