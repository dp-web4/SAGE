# hestia.service fix: add network-online.target dependency

## Problem
The hestia policy daemon was unreachable. Root cause: the unit lacks a dependency on network readiness.

## Root cause
The `After=default.target` line was removed on 2026-07-25 to break a systemd cycle (the unit was its own dependency via WantedBy). While this broke the cycle, it also meant systemd no longer knew when hestia was ready to accept connections. The daemon starts but may not be ready immediately.

## Fix
Add `After=network-online.target` to the `[Unit]` section. This ensures hestia only starts after the network is fully up.

## The fix
```ini
[Unit]
Description=Hestia local-first Web4 trust daemon
Documentation=https://github.com/dp-web4/hestia
After=network-online.target
# After=default.target REMOVED 2026-07-25: cycle with WantedBy=default.target
# made systemd delete the member-mesh watchers' start jobs every boot.
```

## Why this works
- `network-online.target` is a systemd target that waits for the network to be fully operational.
- Adding `After=network-online.target` ensures hestia only starts after the network is ready.
- This is a simple, correct fix that doesn't require any code changes.

## Verification
After applying the fix:
1. `systemctl --user daemon-reload`
2. `systemctl --user restart hestia`
3. `systemctl --user status hestia` — should show active (running)
4. Test a call to hestia to confirm it responds

## Related notes
- The `StartLimitIntervalSec=120` and `StartLimitBurst=5` settings were added to prevent the 289-restart loop that was observed.
- The `Restart=on-failure` with `RestartSec=5s` is still in place for recovery from crashes.
- The unit is a USER unit, so it lives under `~/.config/systemd/user/`, not `/etc/systemd/system/`.

---
Written: 2026-09-18 22:43 UTC
