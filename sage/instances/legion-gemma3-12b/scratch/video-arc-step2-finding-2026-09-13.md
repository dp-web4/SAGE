# Video Arc Step 2 — Finding (2026-09-13, tree head 837f0d72c, branch legion-being/work)

## Verified this beat (file+line, read from my worktree at head 837f0d72c)
- sage/irp/plugins/ollama_irp.py L215-240: `get_chat_response` builds payload as
  {'model', 'messages': messages, 'stream': False, 'keep_alive': -1, 'think', 'options'} —
  the `messages` list is passed through UNCHANGED into the /api/chat request body. No
  content filtering, no key stripping. A message dict carrying an extra "images" key
  would reach Ollama intact. (read L204-263)
- sage/gateway/heartbeat.py: conversation assembly builds every entry as
  {"role": ..., "content": <string>} — text-only dicts; no frame/image path exists.
  (L561-700 region, read in chunks this beat and prior beats)

## Consequence (SUSPECTED until pinned by check next beat)
The missing video organ is on the HEARTBEAT side, not the IRP side: heartbeat must be
able to emit a message dict like {"role": "user", "content": ..., "images": [b64...]}
into the conversation; Ollama /api/chat natively accepts `images` (base64) on user
messages — external API fact, not check-able from here, labeled suspected. IRP needs no
change for vision to flow.

## Next beat (ordered)
1. Write a regression pin in sage/irp/tests: get_chat_response payload preserves extra
   keys on message dicts (images survive construction). Run `check irp::test_name`,
   transcribe verdict verbatim to scratch BEFORE claiming it anywhere.
2. Draft heartbeat-side frame-injection design note: where frames come from (camera?
   gateway_server.py path?), hook point in conversation assembly, check-based plan for
   "frames reach the model or they do not".
