# Check verdicts — frame tests + full suite AFTER compose() wrapper (beat 2026-09-13 ~22:0x UTC)

Tree all three checks ran against: head 6ca455700b4a1007c502d9b873f1f03ce006c373 (short 6ca455700),
branch legion-being/work, dirty=true (my uncommitted wrapper + test file).
Worktree /home/dp/ai-workspace/being-worktrees/legion-being.
Embodiment: qwen38-heretic:q3km-vl, 26.9B, num_ctx 24576 (state pinned).

## Check A — gateway::test_frame_lands_as_images_list
headline: "PASS — 1 passed, 236 deselected in 0.42s." verdict PASS, action_id 0bccdf2b-8a04-42ff-99f4-d8188bfc00f7 (witnessed)
## Check B — gateway::test_no_frame_grows_no_images_key
headline: "PASS — 1 passed, 236 deselected in 0.37s." verdict PASS, action_id 5dd97510-7338-4efe-8e3f-78e34e28ad9a (witnessed)
## Check C — full gateway suite
headline: "PASS — 237 passed in 4.32s." verdict PASS, exit_status 0, action_id 1e594e25-44b5-4e8d-992a-ace7e148a26e (witnessed)
output verbatim: ".... [100%]\n237 passed in 4.32s" (21 test files, sha256 321b597a..., at_head 6ca455700)
output_sha256: 54c5da2f01e723db442f731e9689bf2777dd267600c28340dcc8fc0277ddd68f

## RED->GREEN arc, complete and citable
RED (pre-wrapper): frame test FAIL / no-frame PASS — scratch/check-verdict-frame-red-confirmed-2026-09-13c.md
GREEN (post-wrapper): both frame tests PASS + full suite 237/237 PASS.
Implementation: tail wrapper appended to sage/gateway/heartbeat.py — _compose_plain = compose;
new compose(act_first=True, *, frame=None, **kwargs) delegates and attaches images=[frame] on the
user message only when frame is not None. No-frame seed byte-identical (no empty key).

## Step 8 status: (a) DONE, (b) DONE — next: PR with tree head + EVIDENCE block (step 8c).
