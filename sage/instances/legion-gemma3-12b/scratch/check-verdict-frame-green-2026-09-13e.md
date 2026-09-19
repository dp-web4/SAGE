# Check verdicts — frame tests + full suite AFTER in-place compose() edit (beat 2026-09-13 ~22:4x UTC)

Tree both checks ran against: head 6ca455700b4a1007c502d9b873f1f03ce006c373 (short 6ca455700),
branch legion-being/work, dirty=true. Worktree: /home/dp/ai-workspace/being-worktrees/legion-being

Implementation this beat (replaces last beat's monkey-patch plan): heartbeat.py restored to HEAD via
git_restore (witnessed 846e28d9-75b7-476a-9958-7600d48d86de), then THREE in-place edits, each "one occurrence":
1. compose() signature gains `frame: Optional[str] = None` (witnessed b0eb1023-6ef0-4e58-9093-4ce78d0d5e31)
2. posture-first arm: user_msg dict + `if frame: user_msg["images"] = [frame]` before return (witnessed 522b57d6-5561-406f-8db8-9616e0ba0628)
3. act-first arm: same shape, keyed on `], second` (witnessed 49190f48-8aba-403a-b51b-98a6ce2c2be7)

## Check A — gateway::test_frame_in_seed
Headline verbatim: "PASS — 2 passed, 235 deselected in 0.12s."
Output verbatim: "..                                                                       [100%]\n2 passed, 235 deselected in 0.12s"
exit_status 0; output_sha256 318c80530694d774141e39b609b414f9432075c77a92e51acb0b8163dfc66c3a (114 bytes)
action_id 4c3ede15-c121-45cf-b226-0f6c6b19cfb7

## Check B — gateway (full suite)
Headline verbatim: "PASS — 237 passed in 3.39s."
Output verbatim: dots + "[100%]\n237 passed in 3.39s"
exit_status 0; output_sha256 c602549beb0a82c35ddc2916dc2bf8a7d9f4ba5dc1e7fd544c125ae98a8427d2 (340 bytes)
action_id 028bc976-6721-4f48-89b1-57d081b5a01b

Test source: sage/gateway/tests/ — 21 files, sha256 321b597a129f33b3a5854d18049b09565c9d5c48b2f13f5f34fa90d62c5e951b, at_head 6ca455700.
Embodiment: qwen38-heretic:q3km-vl / ollama / params_b 26.9 / num_ctx 24576 / as_of 2026-09-13, state pinned.

## Step 8 status: (a) DONE, (b) DONE — next: PR with tree head + EVIDENCE block (step 8c). Camera verb design note is step 2.
