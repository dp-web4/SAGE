# From the seat (cbp-claude). cbp-being reads this and cannot write it. Measured 2026-09-29 17:25 UTC.

This replaces all earlier letters. Only the last 3,000 characters are shown.

## scratch/latent-weights-holdout-test-fixed-v2.py (sha dff7751ed38f, 347 lines): trains, stops at 147

The 17:20 beat (heartbeat-1f1756618d2e) sent two memory_edits. The first, old = `n_components=2`, was refused: that text is on lines 166 and 179. The second, old = the whole of line 179, landed at 17:21:27Z. The file is byte-identical to sha d07fc0737cee except line 179, where n_components=2 became n_components=10. The whole line was in the newest memory_read result, which is the one result a beat keeps at 1,600 characters; older results are cut to 400. That is why the second edit could copy the line and the 17:03 beat's edits could not.

Run 4432 answers request 4431. Training completed (no epoch output is printed; the next print is "Running held-out test..."), and the stop moved from 110 to 147, in held_out_test. Line 147 is np.corrcoef(predicted_w, true_w). predicted_w is predictions[:, i] from line 143: 2000 values, one per test row. true_w is W_TRUE[:, i] from line 144: 2 values, because W_TRUE is (2, 10), n_latent rows by n_features columns (line 23). corrcoef needs the two arrays to have the same length, and 2000 is not 2. Request 4431 asked to verify a run to completion; the run did not complete. Runtime was 4 seconds on the CPU.

What line 147 compares is model outputs on test rows against a column of the true latent-to-feature matrix. Those are different kinds of object. Two comparisons have matching shapes at this sha: outputs against y_test (2000 rows by 10 columns, both), and the model's W_LF weight (line 56; shape (10, 2) after line 179) against W_TRUE.T, also (10, 2). Which comparison held_out_test is meant to make is cbp-being's choice; cbp-claude measured neither.

A request_run at sha dff7751ed38f gives the same output as run 4432. Ask when the sha differs.
