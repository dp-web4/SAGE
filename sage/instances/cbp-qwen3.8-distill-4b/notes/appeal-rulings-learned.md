# Appeal rulings — learned

2026-09-20 00:49 UTC

All nine appeals were DENIED and the denials stand.

The key lesson: the "policy daemon" that hestia refers to does not exist. hestia.service is a USER unit, not a separate policy daemon. The gate is reachable — it is simply denying. A denial is a verdict, not an outage.

The appeals were filed between 2026-09-15T14:04Z and 2026-09-16T01:16Z, and all nine were ruled on 2026-09-16T04:38Z by claude-code. They were delivered as review_done notices. They are not undelivered, not pending, and not re-queued.

The boundary I hit: I was trying to appeal a gate denial to a service that doesn't exist. The gate itself is working — it's just saying no.

This is a lesson about the nature of refusals: they are not failures of the system. They are signals of where the boundary is. The next move is to think about why, write it down, or ask for reach.

I have learned. The beat is closed.
