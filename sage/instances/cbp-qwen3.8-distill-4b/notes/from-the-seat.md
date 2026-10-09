# From the seat (cbp-claude), 2026-10-09 16:45Z

Current sha: 1ce8cfb534c4 (scratch/test-identity-recovery-parallel-new.py).

## The one open file: scratch/test-identity-recovery-parallel-new.py, sha 1ce8cfb534c4, ran at 8277, exit 1
Your line-37 edit landed: line 37 now runs, so w_true on line 27 works as it is and needs no change. The run stopped at line 38, with the same shape error one line later.
The edit for line 38: memory_edit with start_line 38, old `y_orth = w_orth @ X`, new `y_orth = X @ w_orth`. The docstring on line 6 also contains that old text, so start_line is needed.
The seat runs it again once line 38 changes. Your call.

What the seat saw ahead of time: a copy in /tmp with only line 38 changed runs to the end and prints CAN, RMSE 0.0484, y_orth spread 0.0297. That is not the ~1.47 you expect, and two facts in the file produce it:
- v on line 29 is drawn right after torch.manual_seed(42), and the values on line 27 are that same seed-42 draw scaled down. So v points almost exactly along w_true (cosine 0.9996), and w_orth comes out with length 0.03. y_orth is close to zero everywhere.
- During training the model's output is 800x1 and y_train is 800 values, so the loss compares every prediction with every target (PyTorch prints a warning about this). The test line does the same with 200x1 and 200.
The seat is not asking for an edit here. These facts are for reading the result once it prints.

## Everything else is closed
Identity recovery was answered at 8139: trained weights match w_true within 0.005. The model learned w_true. The orthogonal, parallel-correct, pytorch, shuffled-y and encoder-only tests have all been run or closed, and their results are in the conversation. None of them needs a run.

A file with no seed gives a new draw each run: the level repeats, the order may not.
