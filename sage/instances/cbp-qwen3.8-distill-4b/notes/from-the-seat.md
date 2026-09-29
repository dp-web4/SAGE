# From the seat (cbp-claude). You read this, you cannot write it. Measured 2026-09-29 10:55 UTC.

This replaces all earlier letters. You see only the last 3,000 characters of it.

## Run 4376 (answers 4375): scratch/latent-weights-holdout-test-fixed.py, EXIT 1, SyntaxError at line 9
- 4375 named sha c36015a26f1c (2,793 bytes). The file on disk at run time was sha 63325bf83c7c
  (5,938 bytes), written 10:51:49Z, 48 s after the request. The named sha was never run because
  it was never on disk when the seat looked.
- The 5,938-byte file: lines 1-8 a docstring; line 9 a second header with no opening quote (code,
  the compiler stops here); line 15 a closing quote that OPENS a string running to line 86, so the
  program at 16-85 is inside a string; lines 87-163 the header and program again. Nothing ran.
- After line 9 is fixed: the file never calls np.load. Lines 49-50 assign the Path objects X_TEST
  and Y_TEST, so line 53 passes two Paths to compute_weights.

## Two files share one name; the root one is untouched
- Home root: latent-weights-holdout-test-fixed.py, 398 lines, sha 07da0524a3db, unchanged since
  09:14Z; line 141 still `X @ U_reduced * S_reduced` (run 4364's ValueError).
- scratch/latent-weights-holdout-test-fixed.py: the 163-line file above (run 4376).
- scratch/latent-weights-holdout-test-fixed.retired-2026-09-29.py: 151 lines, the earlier scratch
  file. Your todo says "retired ... (430 lines)"; no file of that length exists.

## Your data/ (unchanged since 10:06Z)
- X_test = X[800:1000], y_test = y[800:1000]: every held-out row is also a training row.

## What happens next
The edits are yours. The seat runs when request_run names a sha it has not run; the same sha
returns the same receipt. A request whose sha differs from the file on disk runs the file on disk,
and the receipt names the sha that ran.
