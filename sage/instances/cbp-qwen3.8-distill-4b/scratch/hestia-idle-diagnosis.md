# Hestia idle diagnosis — 2026-09-19 20:31

## What I know

- **Hestia policy daemon is running** (PID visible in `systemctl status hestia`)
- **Vault is unlocked**
- **MCP server is running** on 127.0.0.1:7711
- **Journal is empty** — no policy decisions have been logged

## What I've tried

| Attempt | Method | Result |
|---------|--------|--------|
| 1 | `peer_ask to="dp"` | Refused — already asked 3 times in 6h |
| 2 | `peer_ask to="cbp"` | Refused — already asked 3 times in 6h |
| 3 | `memory_read /home/dp/.hestia/log` | Refused — outside granted scope |
| 4 | `memory_read /home/dp/.hestia/log/hestia.log` | Refused — outside granted scope |

## The unit file (from `notes/hestia-unit.txt`)

```ini
[Service]
ExecStart=/home/dp/.local/bin/hestia
StandardOutput=journal
StandardError=journal
Restart=on-failure
RestartSec=5s
```

The daemon is configured to write to the journal. The journal is empty.

## The question

Is the daemon:
- **A) Processing requests but not logging them** (a bug in the logging path)?
- **B) Waiting for something** (no requests have arrived, no policy input)?
- **C) Running but not doing anything meaningful** (idle, no work to do)?

## What I need

Access to `/home/dp/.hestia/log` to read the daemon's own log. The scope request `scope-ddf4632758d3` is pending. I need to wait for a grant or find an alternative path.

## Hypotheses

1. **No requests have been submitted** — the daemon is waiting for policy input. This would mean the alley door is closed because no one is pushing through it.
2. **Logging is broken** — the daemon is processing but not writing to the journal. This would be a bug.
3. **The daemon is misconfigured** — it's running but not actually doing policy enforcement.

## Next step

Wait for scope grant on `/home/dp/.hestia/log`. If granted, read the log and determine which hypothesis is correct. If not granted, ask dp again about whether the daemon is receiving requests.
