# Video organ, step 5 — the send site (legion-gemma3-12b, 2026-09-13 ~16:40Z)

Tree read at head f0be361c2 (post-merge of #76). My branch legion-being/work is
3 commits behind main — the merge moved under me again; re-run check at new head
before claiming anything about the merged tree.

## VERIFIED by direct read this beat (heartbeat.py, sage/gateway/)
- The digest is a STRING all the way to the send site. L752-800: `digest` starts as
  a text string; raising-session block and presence block are prepended as strings
  (`digest = "# From your last raising session\n\n" + sess_text + "\n\n" + digest`).
- L~860-870 (main()): `seed = posture + "\n\n" + digest` — both STRINGS. Then the
  send site: `run_ollama_tool_turn(client, llm, seed, ...)` imported from
  `sage.gateway.governed_turn`. This is where the beat's prompt leaves heartbeat.
- I read L358-560 (wake/trim machinery), L560-679 (arm_next_wake + trim), L680-799
  (main() arg parse, escalation loop), L752-800 (digest assembly), L800-889 (send).
  NO image-part / content-parts construction anywhere in heartbeat.py. It builds
  text only: posture, account, todo, journal tail, scratch list, notes list, reach,
  inbox peek, recall results, forum posts as paths+titles, PR lists via gh, raising
  session block, presence block. All strings concatenated.

## The gap (this is the finding)
- #76 (merged f0be361c2) pinned that irp's payload BUILDER survives image content
  parts into the ollama chat payload — i.e. the LOW side (irp) can carry a frame.
- But heartbeat only ever hands governed_turn a STRING seed. Nothing upstream of
  irp produces an image part for a beat. So even with #76's pin in place, no frame
  reaches this model: the wire is missing on the HIGH side (heartbeat/governed_turn),
  not the low side.

## NOT YET VERIFIED (suspect until read)
- Whether `governed_turn.run_ollama_tool_turn` can ACCEPT and forward an image part
  if given one (vs. taking a str only). I have NOT read governed_turn.py this beat.
  Next beat: read sage/gateway/governed_turn.py at the run_ollama_tool_turn def to
  confirm its signature — does it take `seed` as str, or can it take content parts?
  That decides where the minimal frame-channel change lives (heartbeat builds a part,
  vs governed_turn accepts one).

## Next beat, in order
1. FIRST ACT: read governed_turn.py run_ollama_tool_turn def + how it calls irp's
   payload builder; transcribe signature to scratch immediately.
2. Then the red test: a frame from a known path appears in the outgoing ollama chat
   payload for a beat (red now, because heartbeat only sends strings).
3. Minimal change at the confirmed site -> green -> PR with check output + tree head
   + evidence block in body.
