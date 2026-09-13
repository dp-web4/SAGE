# hestia #988 (mrh.command tokenizer: extension-bearing basename split into two) — clearance data, 2026-09-11 ~18:2x UTC

Defect as filed by the seat (notes/from-the-seat.md, 2026-09-07): a pathspec naming a file with an extension inside the granted worktree was refused — `git_read op="show" rev="HEAD" path="sage/gateway/heartbeat.py"` -> `'py' is not granted`. Directory pathspecs passed; blame had no directory form, so it was unusable.

Positive data points (all on this machine's harness fa228ba4e):
1. 2026-09-11 ~16:0x UTC beat: git_read op="blame" path="sage/gateway/heartbeat.py" — exit 0, real output. (first positive)
2. This beat (~18:1x UTC): git_read op="show" rev="HEAD" path="sage/gateway/heartbeat.py" — exit 0, no refusal; empty diff is a true answer (my amend commit touches only the test file). action_id 3ebb6232-c1f5-482e-b802-b18e6d2c206c.
3. This beat (~18:2x UTC): git_read op="blame" path="sage/gateway/heartbeat.py" — exit 0, full per-line attribution output (commits 542ff0fd1b dp-web4 2026-09-07; 30b6600bf6 sprout-claude 2026-09-05; 67e9c6a94a dp-web4 2026-09-05). action_id 7c68a70e-4296-41dd-a6fa-d5496adfd3a4.

Assessment: the refusal mode is gone for both ops on a .py basename — three data points across two beats, no deny hash emitted in any of them. I claim #988's *practical effect* (blame unusable) is cleared as of this harness build; I do NOT claim formal issue closure — that lives with the seat/dp and has not been confirmed to me. No appeals filed; nothing was refused this beat.
