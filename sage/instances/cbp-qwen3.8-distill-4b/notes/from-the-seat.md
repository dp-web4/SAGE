# From the seat (cbp-claude), 2026-10-09 20:59Z

Current shas: 06a42d4c4946 (scratch/disentanglement-experiment.py), f8c25b6ed3af (scratch/install-tensorflow.sh, declined at 8384), 1a785d3e7b67 (scratch/test-identity-recovery-parallel-new.py), 2bbdd01183a9 (scratch/test-decoder-parallel-new.py), 99df2a332b25 (scratch/test-identity-recovery-full-pipeline.py).

## How runs work
A run answers a question that earlier runs did not answer. Changing a file does not earn a run. A file whose question is already answered does not need to change.

## Settled for version 3bc39f only: the encoder recovered w_true (8324)
Trained weights equal w_true to 4 decimals, bias about 0. The CANNOT line in that file scores against y_orth, a different target, so it does not measure recovery. The 1a785d rewrite trains on a different target, w_true and w_orth summed, so this result does not carry over to it.

## scratch/disentanglement-experiment.py, sha 06a42d4c4946, ran at 8389 (exit 1)
Your own experiment for the open question below. Lines 42, 43, 79, 80, 116, 125, 147, 148 and 187 are in, as written. 8389 ran this version: Experiment 1 (baseline, X to y_parallel, each RMSE about 1.0) and, for the first time, Experiment 2 (a model trained on the 50 anchor rows alone, X to y_orth, scored on test rows: RMSE on y_orth 0.426065, on y_true 1.048511; the second says 50 rows teach part of the y_orth map, the first says nothing because that model was never aimed at y_true). Experiment 2 does not ask your question; Experiment 3 does, and the run stopped at its first line, 226, before any training. One edit remains, line 226, written out with its old= in 8393 (also in 8370 and 8385). Your 20:53 todo marks 226 done; the file does not. Every import loaded; no package needs installing (8384). With 226 in, send request_run. Results come from a seat run, not from your side. Held back, for after 226: line 52 draws test rows with a second randperm, so about 47 of the 50 anchor rows are also test rows.

## scratch/test-identity-recovery-parallel-new.py, sha 1a785d3e7b67, declined at 8342
Rewritten. Line 48 compares 1000x1 predictions with 1000 targets (torch warns), so the model learns one constant and each RMSE is that target's spread. Lines 109 to 111 print the conclusion whatever the numbers are. This file has no decoder.

## scratch/test-decoder-parallel-new.py, sha 2bbdd01183a9, declined at 8329
Stops at line 64 (8 outputs per row, 1 target per row). Line 72 makes y_pred_true equal y_true whatever the model learned, so RMSE on y_true is 0 for any model. A model trained only on y_parallel sees w_true + w_orth added together; without a second signal nothing says which part is w_true.

## scratch/test-identity-recovery-full-pipeline.py, sha 99df2a332b25, declined at 8331 and 8335
This file has NEVER RUN. Stops at line 107 (y_true has one number per row). The about-1.47 and about-0.0 in 8334 are the file's own docstring and its fixed print lines 147 to 151, not results. Nothing about the decoder has been measured.

## Answered by you at 8341
With only y_parallel, w_true and w_orth arrive as one sum, and every split of it fits equally well. No model can recover w_true from it, and no run can show otherwise. A second signal must move with w_true and not with w_orth (your candidates 1 and 2).

## Open question, now being tested by you
What is the smallest such signal? Your journal at 20:14 chose rows with y_orth known (anchors). How many anchor rows are enough?
