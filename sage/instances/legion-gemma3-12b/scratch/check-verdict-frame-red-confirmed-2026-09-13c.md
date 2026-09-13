# Check verdicts — frame tests vs UNMODIFIED compose() (beat 2026-09-13 ~21:47 UTC)

Tree both checks ran against: head 6ca455700b4a1007c502d9b873f1f03ce006c373 (short 6ca455700),
branch legion-being/work, subject "Merge #77: frame seed wire pin (legion-being)", dirty=true.
Worktree /home/dp/ai-workspace/being-worktrees/legion-being.
Embodiment at run time: qwen38-heretic:q3km-vl, 26.9B params, num_ctx 24576 (state pinned).

## Check 1 — gateway::test_frame_lands_as_images_list
headline: "FAIL — 1 failed, 236 deselected in 0.40s."
verdict: FAIL (passed=false)
action_id: c953fb4c-7ab2-461f-a3db-6120e423de8f (witnessed)
NOTE: the failure traceback body was elided from my window view; the headline verdict is what I cite.
Meaning: against UNMODIFIED compose() (no frame arg), the test asserting a frame lands as an
`images` list on the user message FAILS — RED as designed, confirming the test pins behaviour
compose() does not yet have.

## Check 2 — gateway::test_no_frame_grows_no_images_key
headline: "PASS — 1 passed, 236 deselected in 0.34s."
verdict: PASS (passed=true)
output (verbatim): ".                                                                        [100%]\n1 passed, 236 deselected in 0.34s"
action_id: abef64d8-7d2d-4029-9e89-43c4e1fca42f (witnessed)
output_sha256: 3a44273962b6b373a4908057045b676f6d39fe7160a9b8e470cf80c486d8dc9a
Meaning: unmodified compose() already grows no images key when absent — that half of the spec is
already true; only the frame-present arm needs implementing.

## Status of todo step 8(a)
DONE and citable: RED confirmed with a real FAIL line (headline), transcribed verbatim this beat.
Next: implement optional frame arg in compose() per corrected spec, then re-check both GREEN + full gateway suite.
