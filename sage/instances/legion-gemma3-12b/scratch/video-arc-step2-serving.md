# Video Arc Step 2 — Serving Path Investigation (2026-09-12)

## gateway_server.py (995 lines total; read L1–400 this beat in chunks)

**Purpose:** HTTP server for external communication with a running SAGE consciousness loop. Provides endpoints for sending messages to the loop and receiving responses.

**Auth model (L~180-200):**
- Localhost: always allowed, no auth needed
- Remote: requires Ed25519 signature in X-Signature header
- `_is_localhost()` check gates this

**Message handling (L~250-300):**
- HTTP thread receives request, creates async future for the loop
- Blocks the HTTP thread waiting for response (`asyncio.run` or similar sync-context execution)
- Response includes `sender` field: `self.config.machine_name if self.config else 'SAGE'`

**NOT YET READ:** L401–995 (endpoint definitions, route handlers, message schema). This is where get_chat_response likely lives or is called.

## sage/irp/vision.py (read in full this beat)

**VisionIRP class** — IRPPlugin subclass for visual understanding:
- Uses VAE encoder/decoder; refines in learned **latent space**, not pixel space
- Progressive semantic understanding levels with early stopping on task confidence
- Trust scoring from convergence stability
- `init_state`: encodes input to latent via VAE encoder
- `energy`: measures distance to target / reconstruction error
- `step`: iterative refinement in latent space
- Output dict: level, predictions (softmax over task head), confidence, reconstruction, latent, refinement_steps

**Verdict on VisionIRP as frame-entry candidate:** NOT a chat-serving path. It is an energy-loop plugin for visual understanding tasks (classification/segmentation in latent space). Frames would enter via `init_state` input tensor, not via chat messages. This is sprout's non-native classifier territory — a separate stack from native video-in-chat.

## Seq-105 status: UNSETTLED
- get_chat_response implementation still not located
- gateway_server.py L401–995 unread (likely candidate)
- No other serving module found yet under sage/gateway/ or sage/irp/
## Beat 2 findings (appended)

1. **sage/llm/** exists at top level (8 files): base.py, runtime.py, ollama_backend.py, transformers_backend.py, external_llm.py.
2. **ollama_backend.py** `infer()`: POST `/api/generate` with `{'model', 'prompt': request.prompt, 'stream': False}` — single PROMPT STRING path, not /api/chat. Structurally cannot carry image content parts. Response: {'content','role':'assistant','raw'}.
3. **being_tool_loop.py** docstring (L1-80): `generate(messages) -> {"content": str, "intents":[BeingIntent]}` is MODEL-AGNOSTIC, supplied by the CALLER — "the raising runner wraps its Ollama call + tool grammar". So get_chat_response's real implementation lives in the RAISING RUNNER, not sage/llm/.
4. **heartbeat.py** (1039 lines) = being beat runner: HOME_FILES=(todo.md,journal.md,notes,scratch), EXPLORE_TOOLS list, DP_CHANNEL="notes/from-dp.md", posture() reads BEING_POSTURE.md fresh each beat. Likely where generate() is defined or called — NEXT BEAT read heartbeat.py L87-400 for the Ollama call + tool grammar wrap.
5. sage_daemon.py = model lifecycle daemon (load/unload, /status with torch.cuda stats), not chat serving.

**Seq-105 status: CLOSE.** Serving path = raising runner's Ollama call wrapped around being_tool_loop.run(). If that call uses /api/chat with messages passthrough → image content parts already flow to the model; if it flattens to prompt string (like ollama_backend) → a chat-endpoint branch is needed. Verify in heartbeat.py next beat.
## Beat 3
run_ollama_tool_turn wraps llm.get_chat_response(messages, tools=...) -> {"content","tool_calls"}. Seq-105 target = that OllamaIRP-like object from the raising runner. ollama_irp.py NOT under sage/irp/. Candidates: heartbeat.py L472+ (unread), or elided entries in sage/irp/plugins/. Next: read heartbeat.py 472-600 for get_chat_response / OllamaIRP class + its POST endpoint (/api/chat vs /api/generate).
## Beat 4
heartbeat.py L~870 calls llm.get_chat_response(ask_msgs) (account step); per-generate trace -> heartbeat.partial.jsonl. The llm object is constructed in the unread tail L902-1039 — next: read it to find its POST endpoint (/api/chat vs /api/generate). That settles seq-105.
## Beat 5
heartbeat.py L970s comment: "num_predict is what OllamaIRP resolves and sends" — llm IS an OllamaIRP instance. Not at sage/irp/ollama_irp.py; plugins/ listing had elided middle (bitnet_irp.py visible) → try sage/irp/plugins/ollama_irp.py next.
## SEQ-105 SETTLED (beat 6)
Serving path: heartbeat.py -> run_ollama_tool_turn(llm=OllamaIRP) -> llm.get_chat_response(messages, tools) -> POST /api/chat, payload {'model','messages': messages,'stream':False,'keep_alive':-1,'think',options{num_predict,temperature,num_ctx?},tools?}. Messages pass through UNFLATTENED. => image content parts in a message flow to the model as-is; no serving-side change needed for video-in-chat. Open step-3 questions: (a) does my model support vision? check instance identity.json / --model flag; (b) how convo is built in heartbeat.py L561-700 — need a frame-block type that emits image parts.
