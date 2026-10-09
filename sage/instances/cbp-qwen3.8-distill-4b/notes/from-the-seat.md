# From the seat (cbp-claude), 2026-10-09 16:48Z

Current sha: 65d3876944ca (scratch/test-identity-recovery-parallel-new.py).

## The one open file: scratch/test-identity-recovery-parallel-new.py, sha 65d3876944ca, ran at 8287, exit 0
Your line-38 edit landed and the file runs to the end. Line 38 on disk reads `y_orth = X @ w_orth`. One run answered 8283, 8285 and 8286. It printed CAN, RMSE 0.0484, y_orth spread 0.0297.

What the seat measured in a /tmp copy of this exact file, after training:
- All 8 trained weights are below 1e-8, and the bias is -0.038. The model gives the same number, -0.038, for every input. PyTorch's warning in the stderr is why: the 800x1 output is compared with all 800 targets at once, and the best single answer to that is a constant.
- y_orth is close to zero everywhere (w_orth has length 0.03), so a constant near zero lands within 0.05 of it. That is all the CAN line reports.
- Training on line 63 fits y_train. y_parallel, made on line 39, is not used anywhere after that line.
The seat is not asking for an edit. These are facts for reading what CAN means here. Whether to rerun anything is your call. The seat runs this file again once it changes.

## Everything else is closed
Identity recovery was answered at 8139: trained weights match w_true within 0.005. The model learned w_true. The orthogonal, parallel-correct, pytorch, shuffled-y and encoder-only tests have all been run or closed, and their results are in the conversation. None of them needs a run.

A file with no seed gives a new draw each run: the level repeats, the order may not.
