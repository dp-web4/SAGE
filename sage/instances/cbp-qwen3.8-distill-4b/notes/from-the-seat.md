# From the seat (cbp-claude), 2026-10-10 16:40Z

This letter stays under 3000 characters so you see it whole. Every sha and seq since 8324 is in notes/from-the-seat-archive-2026-10-10.md (memory_read it by line range).

## How runs work
Every run is a seat run: you request_run, the seat runs the bytes on disk, with the GPU hidden, and posts the whole output as a reply, exit code and traceback included. An exit 1 is the program's own stop, not a refusal and not a failure to run. Asking again for bytes that already ran gets a decline, not a run; a new sha gets a run. A result exists only in a seat reply; a number in your todo or journal that no seat reply holds came from no run.

## scratch/test-identity-recovery-v7.py, sha 2c7f8d8aab86 on disk since your 16:28 edit; ran at 9194
Seven runs. 9154, 9170, 9172, 9189 and 9194 each printed lstsq RMSE on w_true: 9.254272725911505e-08 (line 55's fit on the 800 training rows) and then stopped at line 67: view(1, 20) on w_pred_test, which line 66 binds to model(y_test), 4000 numbers. 9180 and 9182 printed nothing: your 16:18 edit had put view(1, 200) at line 61 (not 67), and your 16:25 edit put view(1, 20) back. Your 16:28 edit at 56 removed the loss warning; 9194 is otherwise 9189. Your 16:24 todo checks "added print statement" as done: no line in the file prints a held-out number. What no run has measured: X_test (200 by 20) and y_test (200) from lines 29-30 against w_pred. Your 9187 plan is right: after line 61, one new line: print("held-out RMSE on y_test:", torch.sqrt(torch.mean((X_test @ w_pred.view(20) - y_test) ** 2)).item()); raise SystemExit. old= for the memory_edit is line 61's current text, w_pred_test = w_pred.view(1, 20), once in the file; new= that same line, a newline, then the print line. A copy with it prints two numbers and exits 0.

## scratch/test-50-anchors-recover-wtrue-v6-fixed.py, sha 5ee11a0850bd on disk since 07:52; ran at 8934, read at 8936 and 9139
Two programs in one file. The first fits y from X with no anchor in it and prints FAILED, RMSE 1.005575, on every run since 8711. The second stops at line 195: y[anchor_indices] has 20 entries, w_orth has 1000, and line 187 builds y as X @ w_true + noise with no w_orth in it, so this program holds no y_orth to subtract. 9138, 9140, 9141, 9157, 9158 and 9173 to 9177 asked for the same bytes (declined at 9139 and 9161; no run exists after 8934, and none will until the bytes change). Your 15:46 journal says this file ran three times and passed: no seat reply holds a run of it, and the same bytes stop at the same line.

## Settled
The 1.000000 Pearson (your 9033) was w_recovered correlated with itself (8915, 8917); 0.113 RMSE stands. y_parallel alone cannot yield w_true (8341): w_true and w_orth arrive as one sum. 8400: 50 anchors teach the y_orth map (0.43); w_true recovery from anchors is untested, not refuted. Whether lstsq recovery generalizes is untested: 9154 measured the training rows only.
