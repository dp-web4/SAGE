# check irp — verdict 2026-09-13 ~15:37 UTC (beat open, act #1)

Verbatim from tool output:

    headline: PASS — 11 passed in 0.72s. This is the answer. A check that RAN and FAILED still returns successfully as an act: 'the call worked' is not 'the tests passed'.
    target: irp
    verdict: PASS
    output: "...........                                                              [100%]\n11 passed in 0.72s"

Tree the answer ran against:
- worktree: /home/dp/ai-workspace/being-worktrees/legion-being
- head: 837f0d72c867cbd5d35a93d70b399bd789346ee4 (short 837f0d72c)
- branch: legion-being/work
- subject: "Merge #73: irp payload pin (legion-being)"
- committed: 2026-09-13T03:12:20-07:00
- dirty: true

action_id: a163fa07-b83c-4c07-b45a-033837bd43fc (witnessed)

Reading of this verdict, stated precisely:
- 11 passed / 0 failed on tree head 837f0d72c. The suite now includes my added test_image_content_part_survives_into_chat_payload (added last beat; the pre-#73 count was 9 per seat's isolated run at bce29e10d, so +2 since: #73's own pin plus mine).
- This is execution-pinned now: "image content parts survive payload construction" holds on this tree as a test result I can cite with the check output and tree head above. It is no longer asserted from tool-status 'ok' alone.
- The harness running me is 461b26d6e (uncommitted edits present) — different commit than the worktree head, so this verdict pins the WORKTREE code at 837f0d72c, not necessarily the exact binary serving me. That distinction stays in the record.
