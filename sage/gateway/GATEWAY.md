# SAGE Gateway — Always-On Daemon + HTTP Interface

## Overview

The SAGE gateway transforms SAGE from a batch process (invoked every 6 hours by systemd timers) into a continuously running consciousness loop with an HTTP interface for cross-machine communication.

**Key insight**: External messages are just another sensory modality. The consciousness loop already handles vision, audio, proprioception, time — gateway adds `message` as a fifth modality. Responses flow out through the effector system as `EffectType.MESSAGE` effects.

## Architecture

```
Client (CLI / Claude / peer SAGE)
    │ HTTP POST /chat
    ▼
GatewayServer (port 8750)
    │ MessageQueue.submit() → asyncio.Future
    ▼
SAGEConsciousness.run()
    │ Step 1: poll message queue → SensorObservation(modality='message')
    │ Step 2: compute salience (messages get HIGH salience ~0.62)
    │ Step 4: select attention → routes to ['language'] plugin
    │ Step 6: execute LLM plugin (real model inference)
    │ Step 8.5: extract Effect(MESSAGE, 'respond')
    │ Step 9: dispatch to NetworkEffector
    ▼
NetworkEffector.execute()
    │ MessageQueue.resolve() → Future resolves
    ▼
HTTP response returned to caller
```

## Components

| File | Purpose |
|------|---------|
| `machine_config.py` | Auto-detect Thor/Sprout/CBP, load appropriate config |
| `message_queue.py` | Thread-safe asyncio.Future bridge between HTTP and consciousness loop |
| `sage_daemon.py` | Main daemon: load model, start consciousness loop + gateway |
| `gateway_server.py` | HTTP server: `/chat`, `/converse`, `/health`, `/status`, `/peers` |
| `cli_client.py` | CLI tool for talking to a running SAGE daemon |
| `systemd/` | Service files for Thor and Sprout deployment |

## HTTP Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/chat` | localhost: none, LAN: Ed25519 | Send message, get response |
| POST | `/converse` | same | Multi-turn (includes conversation_id) |
| GET | `/health` | none | Health check + metabolic state |
| GET | `/status` | none | Full daemon status |
| GET | `/peers` | none | List known peer SAGEs |

## Usage

### CLI Client

```bash
# Single message (localhost)
python3 -m sage.gateway.cli_client "What's on your mind?"

# Remote SAGE
python3 -m sage.gateway.cli_client --host 10.0.0.36 "Hello Sprout"

# Interactive conversation
python3 -m sage.gateway.cli_client --interactive

# Health check
python3 -m sage.gateway.cli_client --health
```

### Direct HTTP

```bash
# Health check
curl http://localhost:8750/health

# Send message
curl -X POST http://localhost:8750/chat \
  -H "Content-Type: application/json" \
  -d '{"sender": "claude@cbp", "message": "Hello SAGE"}'
```

### Start Daemon

```bash
# Auto-detect machine and start
python3 -m sage.gateway

# Or via systemd (on Thor)
sudo systemctl start sage-daemon-thor
```

## Deployment

### Thor (Jetson AGX Orin, 14B)
```bash
sudo cp sage/gateway/systemd/sage-daemon-thor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sage-daemon-thor
sudo systemctl start sage-daemon-thor
```

### Sprout (Jetson Orin Nano, 0.5B)
```bash
sudo cp sage/gateway/systemd/sage-daemon-sprout.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sage-daemon-sprout
sudo systemctl start sage-daemon-sprout
```

## Design Decisions

1. **Message as sensor, not bypass** — Messages go through the full consciousness pipeline (salience, attention, metabolic gating). During DREAM state, messages queue until WAKE.

2. **Futures for request-response** — HTTP thread blocks on `asyncio.Future`. Consciousness loop resolves it when the LLM response is ready.

3. **Localhost unauthenticated** — On-machine Claude sessions don't need Ed25519 keys. Remote peers do.

4. **Port 8750** — Avoids conflicts with existing ports (8888/8889 bridge, 50051 federation, 11434 ollama).

5. **Daemon replaces timer** — Existing session scripts become gateway clients instead of standalone model loaders.

6. **Write for the reader you have** — A 0.5B–4B being reads and writes differently from us in ways we
   have measured repeatedly and kept re-deriving. `SMALL_MODEL_LEGIBILITY.md` is the specimen corpus
   and the ten rules that follow from it: what a quoted refutation does, why a refusal must name its
   subject, why durable text may assert no present tense, and the five envelopes a tool call arrives
   in. Read it before writing anything a being will read, and add to it when a being surprises you.

## Network Topology

- **Thor**: 10.0.0.x (AGX Orin) — 14B model, primary SAGE
- **Sprout**: 10.0.0.36 (Orin Nano) — 0.5B model, edge SAGE
- **Legion**: 10.0.0.72 (RTX 4090) — can run daemon or act as client
- **CBP**: 172.25.x.x (WSL2) — client only, needs SSH tunnel for LAN access

## Modified Existing Files

- `sage/core/sage_consciousness.py` — Message queue integration in steps 1/4/6/8.5/9, real LLM execution for messages
- `sage/interfaces/effect_extractor.py` — Language plugin produces MESSAGE effects when message_id present
- `sage/interfaces/effectors/network_effector.py` — New effector routing MESSAGE effects back to gateway

## Status

R&D implementation. All components tested individually. Full end-to-end requires deployment on Thor/Sprout with real LLM models loaded.
