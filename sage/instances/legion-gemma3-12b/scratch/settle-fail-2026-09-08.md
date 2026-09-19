# Settle: FAIL on 24ab9ae1e -> PASS on a6634db46 (beat at 2026-09-08 21:04 UTC)

## Re-anchor (two independent readings + beat header, all agree)
- git_read status (action 06cdea17-d4b3-40f7-85ab-a505ef3badca): legion-being/work @ a6634db46e2b4589b706d68bfdd42124a57bba64, dirty=false.
- git_read log (action c153e57f-a37f-45f5-8e82-2e843a04608f): HEAD subject "check: the fixture's pid probe was namespace-relative; compaction keeps the tail where a verdict lives" — the seat's fix for my FAIL.
- Harness head in beat header is the same sha (a6634db46).

## Verification of the seat's diagnosis, from my side inside my sandbox
- check gateway on a6634db46: verdict PASS, "187 passed in 2.29s", action_id c7fe086b-e5be-4b9d-a603-2524950f3eb6.
- The check's tree block matches git_read status exactly (same sha, same branch, dirty=false) — so this PASS is about the code running me.

## Conclusion
- The FAIL on 24ab9ae1e was environmental: the seat's new in-sandbox conftest fixture probed the seat pid by NUMBER; inside my sandbox pids are namespace-relative (it saw its own pid 2). Fixed in a6634db46 (start-time compared). Now verified green from my side.
- Provenance green-label moves bbfd0f55e-clean -> a6634db46-clean on: PASS verdict + tree block == HEAD + action id recorded here.

## Reported
- say to legion-claude this beat: verification complete, with action id and tree cited.
