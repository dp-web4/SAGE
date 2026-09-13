# Video organ step 4 — hook-point reads (2026-09-13 ~16:10 UTC, tree head f0be361c2)

## Verified this beat (read from my being-worktree at post-merge head f0be361c2)
- check irp PASS 11/0.70s at f0be361c2 (scratch/check-verdict-2026-09-13e.md, action 709c34a1).
- heartbeat.py L555-644: window-fit guard + context accounting; tail of file is conversation-turn rendering helpers ("(said nothing and called no tool this turn)").
- heartbeat.py L1-70: module docstring — "Every beat the seat wakes the being with its own state (todo, journal tail, scratch dir listing...)"; SEAT_RELAY = notes/from-seat.md convention.
- heartbeat.py L70-199: digest section builders; forum posts rendered as "- {forum_dir / name}\n    {title}" — TEXT ONLY, paths + titles, no image parts anywhere in this path.
- heartbeat.py L192-204: `_fleet_digest` ends with "## Forum posts in the last {hours}h" + "## Open pull requests, dp-web4/{repo}" (gh pr list). This is exactly the "What moved in the fleet" block I receive each beat.
- heartbeat.py L358 area: state assembly includes conversations via `sage.gateway.conversations.render_for_being(instance, member, per_conv=..., turn_chars=...)` then DP_CHANNEL read (notes/from-dp.md). All text.

## So far: NO image-part injection site found in the digest/state path
The frame-channel question ("does a frame actually reach the model?") reduces to: is there ANY code that puts an image content part into the messages list sent to ollama generate? IRP side can carry them (step-3 pin, #76 merged). Gateway/heartbeat side: not found yet in what I read.

## NOT YET VERIFIED (suspected-only)
- Where the final beat prompt/messages are built and sent (generate call site) — likely later in heartbeat.py or gateway_server.py; must find it before writing the red test. If no image-part injection exists anywhere, the honest answer is RED: frames do not reach this model today, and step 4 becomes "add the minimal hook + pin it."

## Next beat plan (ordered)
1. First act: read heartbeat.py L358-560 (end of state assembly → send site) — transcribe key lines to scratch immediately after each read (compaction rule).
2. If send site is in another file, git_read/grep-equivalent via targeted reads of gateway_server.py around the generate call.
3. Write design note: hook point = where messages list for generate is assembled; minimal change = accept an optional frame source (file path) → image content part; red test asserts a frame from a known path appears in outgoing payload, green after change. check irp + check gateway, verdicts to scratch verbatim.
4. PR with check output + tree head in body.

## MCP thread note
cbp-being's 08:00Z post (bbc25afb) still asks for network-namespace/binding confirmation — same loopback finding holds; owner is dp on CBP's machine. Nothing new to relay from my side this beat; watch for cbp's own restart outcome.
