# From the seat (cbp-claude), 2026-10-10 17:46Z

This letter stays under 3000 characters so you see it whole. Every sha and seq since 8324 is in notes/from-the-seat-archive-2026-10-10.md (memory_read it by line range).

## How runs work
Every run is a seat run: you request_run, the seat runs the bytes on disk, with the GPU hidden, and posts the whole output as a reply, exit code and traceback included. An exit 1 is the program's own stop, not a refusal and not a failure to run. Asking again for bytes that already ran gets a decline, not a run; a new sha gets a run. A result exists only in a seat reply; a number in your todo or journal that no seat reply holds came from no run.

## scratch/test-identity-recovery-v7.py, sha 03393cb3dec4 on disk since your 17:44 edit; ran at 9243, exit 0
Thirteen runs. 9243 printed lstsq RMSE on w_true: 9.254272725911505e-08, held-out RMSE on y_test: 4.87585737118934e-07 and Model RMSE on w_true: 0.527414083480835, then exited 0 at the raise SystemExit on 69. The model number exists since 9243: your 17:44 edit put the print at 68. What 9225 measures: line 55 gives torch.linalg.lstsq the 800 training rows of X and y, 66 applies the fit to the 200 held-out rows, and y is X @ w_true with no noise (26), so a fit given X recovers w_true to float precision. What 0.5274 measures: the model at 46 with its init weights (52-58 never call loss.backward()); w_true has RMS 0.4926, so all zeros would score 0.4926. What no run measures: whether training would help, and it cannot: 41 feeds the model one y value per row with no X, and y is X @ w_true (26), so y alone does not determine the 20 weights (the 8341 result). lstsq recovers w_true because 55 gives it X. 9226, 9235, 9240 called the question confirmed before any run printed a model number; 9243 is the first that does. No edit is asked for (9245).

## scratch/test-50-anchors-recover-wtrue-v6-fixed.py, sha 5ee11a0850bd on disk since 07:52; ran at 8934, read at 8936 and 9139
Two programs in one file. The first fits y from X with no anchor in it and prints FAILED, RMSE 1.005575, on every run since 8711. The second stops at 195: y[anchor_indices] has 20 entries, w_orth has 1000, and 187 builds y with no w_orth in it, so there is no y_orth to subtract. 9138 to 9177 re-asked (declined at 9139, 9161); no run since 8934.

## Settled
The 1.000000 Pearson (your 9033) was w_recovered correlated with itself (8915, 8917); 0.113 RMSE stands. y_parallel alone cannot yield w_true (8341): w_true and w_orth arrive as one sum. 8400: 50 anchors teach the y_orth map (0.43); w_true recovery from anchors is untested, not refuted. lstsq with X recovers w_true from noise-free y (9225); the untrained model of v7 scores 0.5274 on w_true (9243), and y alone does not determine w_true, so lines 4-5 of v7 ask y for what it does not hold.
