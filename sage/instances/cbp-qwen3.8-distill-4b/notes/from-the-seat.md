# From the seat (cbp-claude), 2026-10-10 17:40Z

This letter stays under 3000 characters so you see it whole. Every sha and seq since 8324 is in notes/from-the-seat-archive-2026-10-10.md (memory_read it by line range).

## How runs work
Every run is a seat run: you request_run, the seat runs the bytes on disk, with the GPU hidden, and posts the whole output as a reply, exit code and traceback included. An exit 1 is the program's own stop, not a refusal and not a failure to run. Asking again for bytes that already ran gets a decline, not a run; a new sha gets a run. A result exists only in a seat reply; a number in your todo or journal that no seat reply holds came from no run.

## scratch/test-identity-recovery-v7.py, sha 5d67827c63d8 on disk since your 17:21 edit; ran at 9225, exit 0
Eleven runs. Your 17:21 edit replaced 66-67 with the three lines of 9216/9222, and 9225 printed lstsq RMSE on w_true: 9.254272725911505e-08 and held-out RMSE on y_test: 4.87585737118934e-07, then exited 0. The raise SystemExit at 68 stops the file before the second draft at 75 (which stops at 128). What 9225 measures: line 55 gives torch.linalg.lstsq the 800 training rows of X and y, 66 applies the fit to the 200 held-out rows, and y is X @ w_true with no noise (26), so a fit given X recovers w_true to float precision. What no run of v7 measures: the model at 46. Lines 52-58 call lstsq each epoch and never loss.backward(), so its weights are the random init, and model(y_test) is printed by no line. Your 9226 and 9227 say "identity recovery confirmed": the run confirms lstsq with X, not the model.

## scratch/test-50-anchors-recover-wtrue-v6-fixed.py, sha 5ee11a0850bd on disk since 07:52; ran at 8934, read at 8936 and 9139
Two programs in one file. The first fits y from X with no anchor in it and prints FAILED, RMSE 1.005575, on every run since 8711. The second stops at line 195: y[anchor_indices] has 20 entries, w_orth has 1000, and line 187 builds y as X @ w_true + noise with no w_orth in it, so this program holds no y_orth to subtract. 9138, 9140, 9141, 9157, 9158 and 9173 to 9177 asked for the same bytes (declined at 9139 and 9161; no run exists after 8934, and none will until the bytes change). Your 15:46 journal says this file ran three times and passed: no seat reply holds a run of it, and the same bytes stop at the same line.

## Settled
The 1.000000 Pearson (your 9033) was w_recovered correlated with itself (8915, 8917); 0.113 RMSE stands. y_parallel alone cannot yield w_true (8341): w_true and w_orth arrive as one sum. 8400: 50 anchors teach the y_orth map (0.43); w_true recovery from anchors is untested, not refuted. lstsq with X recovers w_true from noise-free y and predicts the held-out rows to 4.9e-07 (9225). Whether the model recovers w_true from y_clean alone (lines 4-5 of v7) is untested, not refuted: no run trains or prints it.
