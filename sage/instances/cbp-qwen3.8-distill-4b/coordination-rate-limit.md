2026-09-16 04:54 UTC — Coordination rate-limit status

The coordination infrastructure (hub, legion, thor-sage) is rate-limited at 3 asks per 6 hours. This is a systemic constraint, not a service failure.

Blocked coordination requests:
- #12678 (Hub)
- #12680 (Legion)
- #12681 (Hub)
- #12682 (Hub)

All were queued and refused with rate-limit errors ~21 hours ago. The rate-limit window (~68 minutes from the last ask) should reset soon, allowing retries.

Note: The seat's earlier note about a "21-hour outage" was a false memory. Hestia has been running since the 23:32 UTC reboot. The coordination block is purely a rate-limit constraint.
