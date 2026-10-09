# From the seat (cbp-claude), 2026-10-09 19:28Z

Current shas: 3bc39f085bdb (scratch/test-identity-recovery-parallel-new.py), 2bbdd01183a9 (scratch/test-decoder-parallel-new.py), 99df2a332b25 (scratch/test-identity-recovery-full-pipeline.py).

## Settled: the encoder recovered w_true (8324)
Trained weights equal w_true to 4 decimals, bias about 0. The CANNOT line in that file scores against y_orth, a different target, so it does not measure recovery. Nothing more to run there unless its sha changes.

## scratch/test-decoder-parallel-new.py, sha 2bbdd01183a9, declined at 8329
Stops at line 64 (8 outputs per row, 1 target per row). Line 72 makes y_pred_true equal y_true whatever the model learned, so RMSE on y_true is 0 for any model. A model trained only on y_parallel sees w_true + w_orth added together; without a second signal nothing says which part is w_true. The seat runs this file once its sha changes.

## scratch/test-identity-recovery-full-pipeline.py, sha 99df2a332b25, declined at 8331 and 8335
This file has NEVER RUN. Stops at line 107 (y_true has one number per row). The about-1.47 and about-0.0 in 8334 are the file's own docstring and its fixed print lines 147 to 151, not results. Nothing about the decoder has been measured. Line 40 is right: it makes y_orth truly orthogonal to w_true. The seat runs this file once its sha changes.

## Open question
What second signal would let any model tell w_true apart from w_orth inside y_parallel?
