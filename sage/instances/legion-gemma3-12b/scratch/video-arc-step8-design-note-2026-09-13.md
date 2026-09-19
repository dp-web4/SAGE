# Video organ step 8 — design note (real organ), head 6ca455700, 2026-09-13 ~18:05 UTC

## Hook point — VERIFIED by direct read this beat
sage/gateway/heartbeat.py lines 793–796 at head 6ca455700 (read via memory_read from_line 780):
    seed = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": digest},
    ]
The call site run_ollama_tool_turn(seed, ...) follows immediately (~line 801–804; the exact line was in an elided middle — SUSPECTED until read-confirmed next beat).

## Minimal change (no governed_turn or tool-loop edits — both halves already certified)
Add ONE optional message to seed whose content is a PARTS LIST, not a string:
    {"role": "user", "content": [
        {"type": "text",  "text": "(frame from this machine's camera path)"},
        {"type": "image", "data": <base64 of frame file>},
    ]}
Mechanism: optional CLI arg `--frame PATH` on heartbeat.py. When present, read bytes, base64-encode, append the parts message to seed after digest. Absent → seed unchanged (regression-safe; existing 235 gateway tests must stay green).

Why this is the whole organ: irp preserves parts (#76 merged), loop delivers them unchanged (#77 merged). The only missing link was heartbeat's seed composition — exactly where I said the minimal change lives before the seat confirmed it.

## Red test (write RED first, then make green)
test_frame_in_seed.py in sage/gateway/tests/:
- fixture: a small synthetic JPEG written to scratch/ by the test itself (a real frame from /dev/video0 is outside my reach — see below; a file on this machine's disk proves the same wire).
- RED assertion: seed built with frame_path contains a user message whose content is a list including {"type":"image","data": base64(frame_bytes)} AND that exact data string appears in the outgoing payload (reuse #77's fake-llm pattern, messages positional + num_ctx=24576).
- GREEN: after heartbeat change, same test passes; plus a no-frame case asserting seed is unchanged.

## Frame source — reach question
This machine has one camera (per entrustment). /dev/video0 is NOT in my granted paths; if the final organ wants a live capture rather than a file path, I will request_scope on it with reason: heartbeat --frame needs to read the frame file the seat/operator captures. For the PR, a readable file path suffices — the wire claim does not depend on which bytes arrive.

## Status
Hook point VERIFIED (read). Call-site line SUSPECTED. Red test NOT yet written. Next beat: write red test → check RED (transcribe verdict) → implement --frame in heartbeat.py → check GREEN + full gateway suite (transcribe both verbatim to scratch) → PR with EVIDENCE block + tree head.
