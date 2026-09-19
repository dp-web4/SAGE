# Step 8 RED run — interference found (2026-09-13 ~19:50 UTC)

## Facts established this beat (all verified, not suspected)

1. check gateway::test_frame_in_seed at head 6ca455700 → FAIL: "1 failed, 1 passed, 235 deselected in 0.38s". action_id 3a64921b-fab1-4623-916a-5a135f4fb29f (witnessed). Full verdict: scratch/check-verdict-frame-in-seed-red-2026-09-13.md.
2. git status of worktree: ONLY untracked file is sage/gateway/tests/test_frame_in_seed.py — zero tracked files modified. Branch legion-being/work, behind origin 10, head 6ca455700 (the #77 merge). So the failure cannot be from me editing heartbeat.py or any tracked test file.
3. The failing test is `test_frame_seed_wire` (#77's merged wire test — it PASSED at this exact head last beat: scratch/check-verdict-frame-seed-wire-green-merged-head.md, 1 passed). My new frame-in-seed test apparently PASSED (it should be RED on current code — content is always a str today).
4. `-k test_frame_in_seed` selected exactly 2 tests → both nodeids contain the filename string "test_frame_in_seed" → BOTH live in my untracked file sage/gateway/tests/test_frame_in_seed.py. So `test_frame_seed_wire` must be defined (or imported) inside MY file — it is not a separate tracked test file.
5. My file is 64 lines total; I have seen L1-17 and L~40-64. The middle (~L18-39, ~2500 chars elided twice now) likely contains the wire-test portion — possibly my append last beat included it, or a fixture/helper collision lives there (e.g. _frame_b64 shadowing).
6. search does NOT index untracked files: 'def test_frame_seed_wire' and 'test_frame_in_seed' both return 0 matches in sage/gateway/tests even though the file exists on disk — check/pytest reads disk, search indexes tracked content only. (New tool fact; names body legion-gemma3-12b.)

## Open question (the one that matters)

The actual assertion error text of test_frame_seed_wire was elided from my window (~2418 chars missing). Two candidate causes:
(a) fixture shadowing — if _frame_b64 is defined in my file as a module-level function AND the wire test calls it expecting #77's version, or pytest treats it as a fixture;
(b) my appended wire-test copy diverges from the merged one (different frame fixture → different assertion outcome).

## Next acts (next beat, in order)

1. check 'gateway::test_frame_in_seed.py::test_frame_seed_wire' and '::test_frame_in_seed' individually by nodeid — full tracebacks, no elision of the error line.
2. Read L18-40 of the file to see exactly what is there (the elided middle).
3. Fix whatever shadows/diverges; re-run expecting wire PASS + my frame test FAIL (designed RED); then implement compose() frame support per seat seq-155 spec; GREEN + full gateway suite; PR with EVIDENCE block.
