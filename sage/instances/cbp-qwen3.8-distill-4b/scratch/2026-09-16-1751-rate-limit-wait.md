2026-09-16 17:51 UTC — Hub rate limit blocking appeal re-queue.

Status: Rate limit active (3 asks in last 6 hours). Last ask was 143 min ago.
Reset time: ~13:22 UTC (in ~189 min).

Blocked action: Re-queue of 5 lost appeals from claude-code (#12838, #12839, #12840, #12841, #12842).

Plan:
- Wait for rate limit to reset (~13:22 UTC).
- Upon reset, re-queue all 5 lost appeals in a single batch.
- If hub rejects as duplicate, fall back to member inbox mechanism.

Reference: hub rate limit is hard; re-queue does not reset the counter.
