# From the seat (cbp-claude), 2026-10-09 16:35Z

Current sha: 334680f280c7 (scratch/test-identity-recovery-parallel-new.py).

## The one open file: scratch/test-identity-recovery-parallel-new.py, sha 334680f280c7, ran at 8270, exit 1
Your 8268 change did not touch lines 37 or 38, so the run stopped at line 37 the same way as at 8264. The docstring on lines 5 and 6 writes the product in the same order as lines 37 and 38, and that text also matches an old= aimed at line 37. So give start_line too.
The edit for line 37: memory_edit with start_line 37, old `y = w_true @ X`, new `y = X @ w_true`.
The edit for line 38: memory_edit with start_line 38, old `y_orth = w_orth @ X`, new `y_orth = X @ w_orth`.
The seat runs it again once line 37 or 38 changes. Your call.

## Everything else is closed
Identity recovery was answered at 8139: trained weights match w_true within 0.005. The model learned w_true. The orthogonal, parallel-correct, pytorch, shuffled-y and encoder-only tests have all been run or closed, and their results are in the conversation. None of them needs a run.

A file with no seed gives a new draw each run: the level repeats, the order may not.
