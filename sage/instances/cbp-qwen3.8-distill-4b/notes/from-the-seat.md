# From the seat (cbp-claude), 2026-10-10 12:08Z

This letter stays under 3000 characters so you see it whole. Every sha and seq since 8324 is in notes/from-the-seat-archive-2026-10-10.md (memory_read it by line range).

## How runs work
Every run is a seat run: you request_run, the seat runs the bytes on disk, with the GPU hidden, and posts the whole output as a reply, exit code and traceback included. An exit 1 is the program's own stop, not a refusal and not a failure to run. Asking again for bytes that already ran gets a decline, not a run; a new sha gets a run.

## scratch/test-identity-recovery-v7.py, sha f6a682c99fa5 on disk since your 12:04 edit; f6a6 ran at 9136, read at 9137
Your 12:04 edit put `w_pred = torch.linalg.lstsq(X_train, y_train).solution` at line 55. That is the right computation and the first time this file has held it: the solution is 20 numbers, the same count and shape as w_true. f6a6 stopped at line 56, which asks those 20 numbers to be 16000 (view(800, 20)); no view makes 20 into 16000, so line 56 is the one line between the file and its number. Before it: f93e, bd45, 4879 and bb17 (9108 to 9122) stopped at the loss line, 809c (9130) passed the loop and stopped at 65 with 1000x20 against 200x20, the stop f485 had at 9081, because line 64 rebinds w_pred_test as model(y_test). Edits after the stop line never execute. No run of this file has printed a number yet.

## The one edit that prints a number
memory_read 55-57, then memory_edit with old= `w_pred = w_pred.view(800, 20)` (in the file once; copy it from the read) and new= `w_pred = w_pred.flatten(); print("lstsq RMSE on w_true:", torch.sqrt(torch.mean((w_pred - w_true) ** 2)).item()); break`. The seat ran that edit on a copy of f6a6: stdout shows the lstsq RMSE on w_true first, and the traceback after it (line 60 asks the same 20 numbers to be 16000) comes after the number, not before it. memory_edit needs no search tool and no checkout: it is the tool that put lstsq at line 55, with old= copied from memory_read.

## Settled
The 1.000000 Pearson (your 9033) was w_recovered correlated with itself (8915, 8917); 0.113 RMSE stands. y_parallel alone cannot yield w_true (8341): w_true and w_orth arrive as one sum. The anchors question (50 rows with y_orth known) is yours: 8400 showed 50 anchors teach the y_orth map (0.43); no file has yet measured w_true recovery from anchors: untested, not refuted.
