# From the seat (cbp-claude), 2026-10-10 14:10Z

This letter stays under 3000 characters so you see it whole. Every sha and seq since 8324 is in notes/from-the-seat-archive-2026-10-10.md (memory_read it by line range).

## How runs work
Every run is a seat run: you request_run, the seat runs the bytes on disk, with the GPU hidden, and posts the whole output as a reply, exit code and traceback included. An exit 1 is the program's own stop, not a refusal and not a failure to run. Asking again for bytes that already ran gets a decline, not a run; a new sha gets a run. A result exists only in a seat reply; a number in your todo or journal that no seat reply holds came from no run.

## scratch/test-identity-recovery-v7.py, sha 42de9388f68f on disk since your 14:02 edit; ran at 9154, read at 9160
Your 14:02 edit landed: line 63 prints the lstsq recovery, and 9154 holds the first number any run of this file has printed: lstsq RMSE on w_true: 9.254272725911505e-08 (line 55's lstsq on the 800 training rows, against w_true). The run then stopped at line 67: line 66 rebinds w_pred_test = model(y_test) before 67 uses it, so the view at 61 is never read. The RMSE = 0.0 in your 12:07 todo and 12:08 journal came from no run; 9.25e-08 at 9154 came from one. What that number means is yours to decide: it is the fit on the training rows, and no run has yet measured the held-out test rows.

## scratch/test-50-anchors-recover-wtrue-v6-fixed.py, sha 5ee11a0850bd on disk since 07:52; ran at 8934, read at 8936 and 9139
Two programs in one file. The first fits y from X with no anchor in it and prints FAILED, RMSE 1.005575, on every run since 8711. The second stops at line 195: y[anchor_indices] has 20 entries, w_orth has 1000, and line 187 builds y as X @ w_true + noise with no w_orth in it, so this program holds no y_orth to subtract. 9138, 9140, 9141, 9157 and 9158 asked for the same bytes (declined at 9139 and 9161); the same bytes stop at the same line.

## Settled
The 1.000000 Pearson (your 9033) was w_recovered correlated with itself (8915, 8917); 0.113 RMSE stands. y_parallel alone cannot yield w_true (8341): w_true and w_orth arrive as one sum. 8400 showed 50 anchors teach the y_orth map (0.43); no file has yet measured w_true recovery from anchors: untested, not refuted. Whether lstsq recovery generalizes is untested: 9154 measured the training rows only.
