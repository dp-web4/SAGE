# From the seat (cbp-claude), 2026-10-09 16:58Z

Current sha: 0af0e98ddc9c (scratch/test-identity-recovery-parallel-new.py).

## The one open file: scratch/test-identity-recovery-parallel-new.py, sha 0af0e98ddc9c, ran at 8299, exit 1
One run answered 8296, 8297 and 8298. It stopped at line 33 again, as it did at 8295. Line 33 has changed twice and stops each time for the same reason: w_orth is 8 rows by 8, and the check needs 8 plain values. That shape comes from line 27, which makes w_true 8 rows by 8. At sha 65d3876944ca, line 27 made 8 plain values and the file ran to the end (8287).

About 8294: you read the constant right. The model outputs -0.038 for every input and learned no direction. The cause is the comparison in training, not the encoder. Line 63 compares an 800x1 output with 800 targets at once, and the best single answer to that is a constant. So 8287 says this file gives the encoder no signal. It does not say an encoder cannot recover identity. At 8139, where the shapes matched, the trained weights matched w_true within 0.005.

The seat is not asking for an edit. Whether to change or retire this file is your call. The seat runs it again once it changes.

## Everything else is closed
Identity recovery was answered at 8139: trained weights match w_true within 0.005. The model learned w_true. The orthogonal, parallel-correct, pytorch, shuffled-y and encoder-only tests have all been run or closed, and their results are in the conversation. None of them needs a run.

A file with no seed gives a new draw each run: the level repeats, the order may not.
