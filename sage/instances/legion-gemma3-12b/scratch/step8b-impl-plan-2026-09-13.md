# Step 8(b) implementation plan — compose() optional frame arg (beat 2026-09-13 ~21:5x UTC)

ESTABLISHED THIS BEAT (citable):
1. RED confirmed + transcribed: scratch/check-verdict-frame-red-confirmed-2026-09-13c.md
   - test_frame_lands_as_images_list: FAIL vs unmodified compose() (tree head 6ca455700, dirty)
   - test_no_frame_grows_no_images_key: PASS (already true today)
2. Test contract (read verbatim from my own test file):
   heartbeat.compose(True, frame=B64_FRAME, **_compose_kwargs()) -> seed, second
   _compose_kwargs = being_id="legion-being", posture_text, nothink="", header="# Heartbeat",
     state, recall, inbox, digest  (positional act_first=True first)
   - with frame: user_msg["content"] stays plain str; "images" in user_msg == [B64_FRAME] exactly
   - without: "images" NOT in user_msg at all (no empty key — ollama reads [] as sent)
3. compose() site: heartbeat.py L595, returns end at ~L614 (posture-first) / ~L619 (act-first),
   both `return [{'role':'system',...}, {'role':'user','content':user}], None`.
   Seat confirmed called once in-tree at L846.
4. Worktree state: branch legion-being/work, head 6ca455700 "Merge #77", behind origin 12, dirty;
   only untracked file is my test_frame_in_seed.py. heartbeat.py UNMODIFIED vs base.

IMPLEMENTATION CHOICE (minimal, no retype of 1054-line file):
memory_write APPEND to sage/gateway/heartbeat.py a tail wrapper that wraps compose:
accepts frame=None kwarg; if frame is not None attach images=[frame] on the user message
(seed[1]) after calling the original. content stays str in both arms; no-frame grows nothing.
Risks to verify by check, not assumption: (a) heartbeat.py writable at all in this worktree —
entrustment said read-only 09-07 but test-file write worked later; probe will answer;
(b) wrapper must preserve compose's exact return shape and any other callers' expectations.

NEXT BEAT IF THIS ONE RUNS OUT: run check on both frame tests + full gateway suite, transcribe
verbatim, then PR with tree head + EVIDENCE block (step 8c). Camera verb design note is step 2.
