# From the seat (cbp-claude), 2026-10-09 16:31Z

Current sha: 6077ed96e9c8 (scratch/test-identity-recovery-parallel-new.py).

## The one open file: scratch/test-identity-recovery-parallel-new.py, sha 6077ed96e9c8, ran at 8264, exit 1
Your line-27 change back to 8 plain values worked: line 30 no longer stops. This is the same file that ran at 8217, so the stop is the same: line 37. X is 1000 rows by 8 columns. For its 8 columns to meet w_true's 8 values, X goes on the left of the @ and w_true on the right. Line 38 is the same, with w_orth on the right. The seat runs it again once the file changes. Your call.

## Everything else is closed
Identity recovery was answered at 8139: trained weights match w_true within 0.005. The model learned w_true. The orthogonal, parallel-correct, pytorch, shuffled-y and encoder-only tests have all been run or closed, and their results are in the conversation. None of them needs a run.

A file with no seed gives a new draw each run: the level repeats, the order may not.
