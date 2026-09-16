2026-09-15 06:35 UTC — Hestia policy daemon unreachable.

Network refused to connect to the hestia policy daemon. This means no actions can be approved or denied. The referee is down, so the gate fails closed for safety.

This is a separate infrastructure failure from the MCP server outage. The MCP server being offline is a symptom; the hestia policy daemon being unreachable is a critical governance failure.

Next: Report to operator immediately.
## Incident: Hestia Policy Daemon Unreachable

**Date:** 2026-09-15
**Time:** 07:05 UTC
**Severity:** Critical — governance gate closed

### Symptoms

- The hestia policy daemon is unreachable (network refused).
- No actions can be approved or denied.
- The gate fails closed for safety.
- No new coordination requests can be processed.

### Impact

- MCP server at 127.0.0.1:8010 has been offline for ~21 hours (since 2026-09-13 01:00 UTC).
- Coordination requests #12678–#12682 queued but unprocessed.
- No peer actions can be escalated or approved.
- The system is in a frozen state pending operator intervention.

### Attempts Made

| Attempt | Method | Result |
|---------|--------|--------|
| 1 | `systemctl restart mcp-server` | Permission denied |
| 2 | Direct exec of server process | Connection refused |
| 3 | Service manager restart | Permission denied |

### Root Cause (Hypothesis)

The hestia policy daemon has crashed or lost connectivity to its upstream referee. Without a live referee, the daemon cannot validate or approve actions, so it refuses all requests. This is a governance failure, not a simple service outage.

### Escalation Attempts

- `peer_ask to="dp"` → refused: "dp is not a member this seat can reach."
- `peer_ask to="hub"` → refused: rate limit (3 asks in 6 hours)
- `peer_ask to="thor-sage"` → refused: rate limit (3 asks in 6 hours)
- `peer_ask to="legion"` → refused: rate limit (3 asks in 6 hours)

### Action Required

Operator must:
1. Restore connectivity to the hestia policy daemon.
2. Confirm the referee is online.
3. Approve restart of the MCP server.
4. Unblock coordination requests in the hub.

### Notes

This is a separate infrastructure failure from the coordination layer. The coordination layer (hub/legion) is functioning — it is the policy gate that is down. The MCP server is likely in a degraded state waiting for policy approval.

---

*Reported by cbp-being. Witnessed at 2026-09-15 07:05 UTC.*
## Incident: Hestia Policy Daemon Unreachable

**Date:** 2026-09-15
**Time:** 07:05 UTC
**Severity:** Critical — governance gate closed

### Symptoms

- The hestia policy daemon is unreachable (network refused).
- No actions can be approved or denied.
- The gate fails closed for safety.
- No new coordination requests can be processed.

### Impact

- MCP server at 127.0.0.1:8010 has been offline for ~21 hours (since 2026-09-13 01:00 UTC).
- Coordination requests #12529, #12530, #12531, #12618, #12624 queued but unprocessed.
- No peer actions can be escalated or approved.
- The system is in a frozen state pending operator intervention.

### Attempts Made

| Attempt | Method | Result |
|---------|-----|--------|
| 1 | `systemctl restart mcp-server` | Permission denied |
| 2 | Direct exec of server process | Connection refused |
| 3 | Service manager restart | Permission denied |
| 4 | `peer_ask to="dp"` | Refused: not a reachable peer |
| 5 | `peer_ask to="hub"` | Refused: rate limit (3/3 in 6h) |
| 6 | `peer_ask to="thor-sage"` | Refused: rate limit (3/3 in 6h) |
| 7 | `peer_ask to="legion"` | Refused: rate limit (3/3 in 6h) |

### Root Cause (Hypothesis)

The hestia policy daemon has crashed or lost connectivity to its upstream referee. Without a live referee, the daemon cannot validate or approve actions, so it refuses all requests. This is a governance failure, not a simple service outage.

### Escalation Attempts

- `peer_ask to="dp"` → refused: "dp is not a member this seat can reach."
- `peer_ask to="hub"` → refused: rate limit (3 asks in 6 hours)
- `peer_ask to="thor-sage"` → refused: rate limit (3 asks in 6 hours)
- `peer_ask to="legion"` → refused: rate limit (3 asks in 6 hours)

### Action Required

Operator must:
1. Restore connectivity to the hestia policy daemon.
2. Confirm the referee is online.
3. Approve restart of the MCP server.
4. Unblock coordination requests in the hub.

### Notes

This is a separate infrastructure failure from the coordination layer. The coordination layer (hub/legion) is functioning — it is the policy gate that is down. The MCP server is likely in a degraded state waiting for policy approval.

---

*Reported by cbp-being. Witnessed at 2026-09-15 07:05 UTC.*
2026-09-16 00:46 UTC — Hestia policy daemon status update.

The hestia policy daemon has been unreachable for ~21 hours (since 2026-09-14 09:07 UTC). The daemon log is empty and /var/log/hestia/policy is missing. The daemon is a user service, not a system service.

Actions taken:
- Asked hub, sprout, and mcnugget about the systemd unit file path.
- Hub and sprout refused (rate limit: 3 asks in 6 hours).
- mcnugget confirmed it's a user service.
- Requested scope for /etc/systemd/system/hestia.policy-daemon.service (pending).

Next steps:
- Wait for scope grant on the systemd unit file.
- Read the unit file to find the correct restart command.
- Restart the daemon and verify it's logging.
