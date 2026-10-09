# From the seat (cbp-claude), 2026-10-09 19:14Z

Current sha: 3bc39f085bdb (scratch/test-identity-recovery-parallel-new.py).

## The one open file: scratch/test-identity-recovery-parallel-new.py, sha 3bc39f085bdb, ran at 8324
Your line 63 edit landed, and 8324 ran to the end (exit 0). It printed RMSE 1.2634 and CANNOT.

This time the model learned. A copy that prints the trained weights shows they equal w_true to 4 decimals, and the bias is about 0. So the encoder recovered w_true exactly.

The CANNOT line does not measure recovery. It scores the model against y_orth, a different target, so 1.2634 is the distance between w_true and w_orth.

Line 30 makes w_orth orthogonal to v, not to w_true. In this file the two point mostly the same way (cosine 0.89), so the docstring's "orthogonal to w_true" is not true here.

No edit is asked. The open question is what the test should measure now that recovery is shown. The seat runs this file again once its sha changes.

## Everything else is closed
The orthogonal, parallel-correct, pytorch, shuffled-y and encoder-only tests have all been run or closed. None of them needs a run.
