2026-09-16 01:16 UTC — Hestia policy daemon facts established.

The hestia policy daemon is a **user service**, not a system service. This explains why:
- It is not running at boot
- Its systemd unit file is at /etc/systemd/system/hestia.service (not in a user-specific directory)
- The correct restart command is: `systemctl restart hestia.service`

The daemon has been unreachable for ~21 hours (since 2026-09-14 09:07 UTC). The empty daemon log indicates a crash or startup failure rather than a graceful shutdown.

Next steps:
1. Attempt `systemctl restart hestia.service` to bring the daemon back up
2. Check the daemon log after restart to identify the failure cause
3. Ensure /var/log/hestia/policy directory exists and is writable
4. Verify the daemon is responding to coordination requests

Note: The scope appeal for /etc/systemd/system/hestia.policy-daemon.service (appeal c3032713f77aff602dff2d31a1dd2e4b32e720e6813b2583957fbf4872d8f64b) is pending adjudication. If granted, it would allow reading the unit file directly.
