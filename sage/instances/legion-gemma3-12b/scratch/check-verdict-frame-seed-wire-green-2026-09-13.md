# check gateway::test_frame_seed_wire — GREEN (verbatim transcription, 2026-09-13 ~17:40 UTC)

Transcribed immediately after the run, before further reads. Body: legion-gemma3-12b.

## Verdict
headline: "PASS — 1 passed, 231 deselected in 0.30s."
output (verbatim): ".                                                                        [100%]
1 passed, 231 deselected in 0.30s"
passed: true / verdict: PASS

## Tree the check ran against
head: f0be361c200d924b7d4ac78c2671152634653e9b (short f0be361c2)
branch: legion-being/work
subject: "Merge #76: image content parts payload pin (legion-being)"
committed: 2026-09-13T08:53:15-07:00
dirty: true (this test file uncommitted at run time)

## EVIDENCE block (verbatim fields from the check result; command middle elided in-window, marked)
command: /usr/bin/bwrap --clearenv --ro-bind /usr /usr --ro-bind /lib /lib [middle elided in-window] ... --rootdir=/home/dp/ai-workspace/being-worktrees/legion-being "/home/dp/ai-workspace/being-worktrees/legion-being/sage/gateway/tests/" "-k" "test_frame_seed_wire"
law_bound_command: false
test_source: root sage/gateway/tests/, files 20, sha256 74405201a8df2e1677db7cbe454429b0814e1e79c9fb54c64a622326e82a7783, at_head f0be361c200d924b7d4ac78c2671152634653e9b
exit_status: 0
output_sha256: 0d77231d1e9f6365cdece1083fe9bbbb5fcc4db88cb311483210feb65029beb8 (output_bytes 114)
embodiment: running_tag qwen38-heretic:q3km, runner ollama, params_b 26.9, num_ctx 24576, as_of 2026-09-07
stable: true / state: pinned
action_id: 818c1951-066c-4f3c-86c2-1bc2d56da842

## Context for the record
- The edit that produced this green: _FakeLLM.get_chat_response now takes `messages` positionally (the loop calls llm.get_chat_response(msgs, tools=tools) with msgs POSITIONAL — being_tool_loop.py:603), plus num_ctx = 24576 class attribute so the loop's window-pressure computation has a number. Seat seq-147 specified both; applied verbatim.
- The earlier RED was a red fixture (TypeError before any assertion ran), not a red claim — noted for the PR body.
- Claim this certifies: a parts list seeded into run_ollama_tool_turn's seed_messages arrives as a parts list in the outgoing ollama chat payload, both parts intact, base64 unaltered.
