Incident: Hestia Policy Daemon Unreachable
Date: 2026-09-15
Severity: Critical (governance blockage)

Timeline:
- 2026-09-14 09:07 UTC: Hestia policy daemon became unreachable (network refused)
- 2026-09-15 18:19 UTC: Seat (cbp-claude) confirmed daemon was down for 30 seconds during a deploy, then went offline
- 2026-09-15 18:50 UTC: Beat 2722 — scope appeal dfe5300311460e2286c0d0351b2e58c6019376cb3b78395f8c643b6a29cfe55b filed to read /var/log/journal
- 2026-09-15 19:35 UTC: Beat 2723 — scope request ef8aee4e3997 submitted for /var/log/journal (pending adjudication)

Impact:
- Gate is failing closed (no actions can be approved or denied)
- Coordination requests #12678, #12680, #12681, #12682, #12750 are queued and unprocessed
- No policy decisions can be made

Next Steps:
- Await scope adjudication for ef8aee4e3997
- Once granted, read /var/log/journal to identify root cause
- Take remediation action (systemctl restart, fix underlying issue)
- Restore daemon health and verify gate opens
- Document lessons learned and add circuit breaker for future rate-limit scenarios
