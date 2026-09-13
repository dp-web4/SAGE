# Video Arc Step 2 — Design Note (2026-09-12, head 439fd3ff0, branch legion-being/context-fit-regression-pins, dirty=false)

## Verified this beat (file+line)
- Serving path: heartbeat.py -> run_ollama_tool_turn(llm=OllamaIRP) -> llm.get_chat_response(messages, tools) -> Ollama /api/chat. Text-only at every layer read across beats 09-11/09-12.
- sage/irp/plugins/ollama_irp.py L219-288 (re-read this beat): get_chat_response payload = {model, messages, stream, keep_alive, think, options, tools} — NO image field anywhere in the chain.
- sage/irp/plugins/vision_impl.py L1-200 (read this beat): VisionIRP is a torch VAE latent-space refinement plugin (encode->latent->refine loop). It is NOT a frame path into chat serving; frames do not enter my serving path via the IRP energy loop.
- #69 fate: still open/unmerged. git_read op=log rev=main n=10 this beat shows no #69 commit on main (latest main commits are 2026-09-07 raising sessions). My branch HEAD 439fd3ff0 = "v2 direct-call pins", parent edbe06175 = original six pins.
- recall is working again this beat (returned 5 results) — cartridge issue from prior beats appears resolved; will confirm next beat before claiming it fixed.

## Design sketch (SUSPECTED until checked)
- Frame entry point: Ollama /api/chat accepts an "images" field (base64 list, per-message). Minimal change = extend OllamaIRP.get_chat_response to accept image parts in message dicts and emit the images field; gateway side needs a frame-block type when assembling the beat prompt.
- Alternative: new upstream affordance (gateway verb) that attaches frames to a beat — larger surface, touches governed-turn contract.
- Check that would prove frames reach the model: test posting one image part through get_chat_response and asserting (a) payload contains images, (b) Ollama response content references the frame. Run via check once write access lands; until then this is suspected, not verified.

## Open
- #69 merge fate = dp's call; keep watching main log each beat.
- hestia #988 closure still open.
