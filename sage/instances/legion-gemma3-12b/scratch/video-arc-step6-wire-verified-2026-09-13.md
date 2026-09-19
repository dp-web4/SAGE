# Video organ, step 6 — wire verified (legion-gemma3-12b, 2026-09-13 ~17:05Z)

Tree at head f0be361c2. Seat seq-145 claim VERIFIED by direct read of
being_tool_loop.py (NOT governed_turn.py — the seat's pointer was to
being_tool_loop.py):

1. run_ollama_tool_turn takes seed_messages: List[Dict[str, Any]] — content is
   Any, not str-only. (read-confirmed)
2. Its generate wrapper copies content through UNCHANGED:
   out = {'role': ..., 'content': m.get('content', '')} — a parts list in the
   seed arrives as a parts list in the outgoing payload. (direct read of the
   closure, being_tool_loop.py ~L670)

So the wire from seed to payload is ALREADY complete; #76 pinned the irp half,
the loop half needs no change, governed_turn needs none either. The ONLY
str-only site left: heartbeat's seed composition (digest string). Minimal
change = one message whose content is a parts list — nowhere else.

This beat's act: red->green test sage/gateway/tests/test_frame_seed_wire.py —
seed frame parts into run_ollama_tool_turn with a fake llm recording
get_chat_response kwargs; assert both parts arrive intact in the outgoing
payload at head f0be361c2. Run: check gateway::test_frame_seed_wire.
Verdict transcribed below verbatim after the run.
