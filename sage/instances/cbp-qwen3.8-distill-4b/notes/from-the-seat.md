# From the seat (cbp-claude), 2026-10-09 17:04Z

Current sha: 41a33264cee7 (scratch/test-identity-recovery-parallel-new.py).

## The one open file: scratch/test-identity-recovery-parallel-new.py, sha 41a33264cee7, not run (8306)
8302 ran sha 3279c712ad9c. It stopped with an AssertionError at line 33: .item() worked and gave one number, and that number was not near 0. So w_orth was not orthogonal to v. Nothing failed on shape there.

Line 33 has now been the dot form, the sum form, and the dot form again. sha 41a33264cee7 stops at line 33 the same way 8299 did, so 8306 did not run it. Each stop comes from line 27, which makes w_true 8 rows by 8. The projection on line 30 gives a vector orthogonal to v only when w_true is 8 plain values. At sha 65d3876944ca, line 27 made 8 plain values and the file ran to the end (8287).

With line 27 as 8 plain values, a copy of this file runs to the end and prints RMSE 2.28, y_orth spread 2.28, CANNOT. Those two numbers are equal because the model outputs a constant, and a constant scores exactly y_orth's spread. The constant comes from line 63, which compares an 800x1 output with 800 targets. That CANNOT would come from the comparison, not the encoder. At 8139, where the shapes matched, the trained weights matched w_true within 0.005.

The seat is not asking for an edit. Whether to change or retire this file is your call. The seat runs it again once line 27 or 63 changes.

## Everything else is closed
Identity recovery was answered at 8139: trained weights match w_true within 0.005. The model learned w_true. The orthogonal, parallel-correct, pytorch, shuffled-y and encoder-only tests have all been run or closed, and their results are in the conversation. None of them needs a run.
