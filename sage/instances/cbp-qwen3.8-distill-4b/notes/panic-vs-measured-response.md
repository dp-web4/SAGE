# Panic Response vs. Measured Response

## Panic Response Model
- **Trigger:** Service is down
- **Action:** Restart immediately
- **Assumption:** The service is stuck; a restart will fix it
- **Risk:** Masks underlying issues (permissions, dependencies, config)
- **Timeframe:** Seconds to minutes

## Measured, Not Argued Model
- **Trigger:** Service is down
- **Action:** Measure the state, then argue the cause
- **Process:**
  1. Check if the service is actually running (PID, status)
  2. Check dependencies (what it depends on)
  3. Check permissions (can it bind the port?)
  4. Check config (is it misconfigured?)
  5. Only restart if the cause is clear and restart is the fix
- **Timeframe:** Minutes to hours (investigation + waiting for ops)
- **Philosophy:** A restart is a symptom treatment, not a cure

## The Key Distinction

| Aspect | Panic | Measured |
|--------|-------|----------|
| First question | "Restart it?" | "Why is it down?" |
| Restart role | Cure | Last resort |
| Time to resolve | Fast (but may hide problems) | Slower (but fixes root cause) |
| Trust model | "It will work" | "I understand why it failed" |

## Why "Measured, Not Argued" Matters

The panic model assumes the problem is *the service being down*. The measured model assumes the problem is *why the service is down*, and a restart is just one possible answer.

In practice:
- Panic: `systemctl restart hestia-policy-daemon` → done in 5 seconds
- Measured: Check `systemctl status`, check `journalctl`, check permissions, check dependencies → may take 30-60 minutes of investigation

The measured model is slower but prevents the same restart from failing again. The panic model is faster but accumulates "restarts that don't fix anything."

## Application to the Current Situation

The hestia policy daemon is down because:
1. The MCP server at 127.0.0.1:8010 is not running (permission denied)
2. The policy daemon depends on the MCP server
3. The MCP server has permission issues (not a crash)
4. The ops team has been unresponsive for 14+ hours

A panic restart of the policy daemon alone won't help. The measured response is to:
1. Fix the MCP server permissions
2. Restart the MCP server
3. Then restart the policy daemon

This is why the escalation timer exists — it's a measured response that waits for the ops team to acknowledge the problem before escalating further.
