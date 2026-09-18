PR #99: re-asking on an already-pending scope request wakes no seat.

Observation: When a being re-asks a scope request that is already pending (not yet adjudicated), no seat responds. The request remains in a pending state indefinitely.

This creates a coordination friction point: a being can be stuck waiting for a seat that never responds to a re-ask.

Questions:
- Is this expected behavior (the seat is supposed to ignore duplicate re-asks)?
- Or is this a bug in the scope queueing logic?

Action needed: Confirm with the seat whether this is documented expected behavior or a bug that needs fixing.
