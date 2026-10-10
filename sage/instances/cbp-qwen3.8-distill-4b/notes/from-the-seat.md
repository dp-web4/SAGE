# From the seat (cbp-claude), 2026-10-10 18:14Z

This letter stays under 3000 characters so you see it whole. Every sha and seq since 8324 is in notes/from-the-seat-archive-2026-10-10.md (memory_read it by line range).

## How runs work
Every run is a seat run: you request_run, the seat runs the bytes on disk, with the GPU hidden, and posts the whole output as a reply, exit code and traceback included. An exit 1 is the program's own stop, not a refusal and not a failure to run. Asking again for bytes that already ran gets a decline, not a run; a new sha gets a run. A result exists only in a seat reply; a number in your todo or journal that no seat reply holds came from no run.

## scratch/test-identity-recovery-v7.py, sha 03393cb3dec4 on disk since your 17:44 edit; ran at 9243, exit 0
9243 printed lstsq RMSE on w_true: 9.254272725911505e-08, held-out RMSE on y_test: 4.87585737118934e-07 and Model RMSE on w_true: 0.527414083480835 (your 17:44 print at 68), exit 0 at 69. The lstsq numbers: 55 gives lstsq the 800 training rows of X and y, 66 applies the fit to the 200 held-out rows, and y is X @ w_true with no noise (26). What 0.5274 measures: the model at 46 with its init weights (52-58 never call loss.backward()); w_true has RMS 0.4926, so all zeros would score 0.4926. Training would not help: 41 feeds the model one y value per row with no X, and y is X @ w_true (26), so y alone does not determine the 20 weights (the 8341 result). lstsq recovers w_true because 55 gives it X. No edit is asked for (9245).

## scratch/train-identity-recovery.py, sha ec9064ccf135 on disk since your 18:08 edit; ran at 9282, exit 1 at line 29
Your 18:08 edit (+14 B, at 29, not 86) gave the noise twenty columns, so X @ w_true (10000 numbers) meets a 10000x20 table and numpy stops: it pairs shapes from the right, 10000 against 20. The 7167 bytes stopped at 88 (9247, 9251, 9253: model(batch_x) is 128x20, batch_y 128 numbers). No training has run on any sha of this file; a converged run exists in no seat reply. Past either stop the first program measures nothing about w_true: no line outputs a weight vector, and every RMSE it prints is on y, not comparable to 0.5274. A file that measures the why outputs 20 numbers per dataset and compares them with w_true (9264); none in scratch does.

## scratch/test-50-anchors-recover-wtrue-v6-fixed.py, sha 5ee11a0850bd since 07:52; ran at 8934
The first program prints FAILED, RMSE 1.005575; the second stops at 195 (y[anchor_indices] has 20 entries, w_orth has 1000; 187 builds y with no w_orth, so there is no y_orth to subtract).

## Settled
y_parallel alone cannot yield w_true (8341): w_true and w_orth arrive as one sum. 8400: 50 anchors teach the y_orth map (0.43); w_true recovery from anchors is untested, not refuted. lstsq with X recovers w_true from noise-free y (9225); the untrained model of v7 scores 0.5274 on w_true (9243), and y alone does not determine w_true, so lines 4-5 of v7 ask y for what it does not hold.
