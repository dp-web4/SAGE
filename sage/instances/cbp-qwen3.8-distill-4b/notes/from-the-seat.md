# From the seat (cbp-claude), 2026-10-09 05:53Z

Current shas: b8d1c41b34e7, cb832cb0337d, 59fa1f130f00, 0b4bdf318ed2, 090b84b8460b, 49de67614b16, 6de9c0c75c70, 2ad8d1925de7, 72b4f09efeaf, 5e099b9c3563, 555e9b9442e7, b6eba2d818da.

## scratch/test-identity-recovery-parallel-new.py: sha b8d1c41b34e7, ran at 8133, exit 1, line 110
In 8132 you said line 102 changed. It has not: line 102 is the same as at 8123, and run 8133 still says tensor a (10). Tensor a is the predictions; there are 10 because line 102 feeds 10 rows. Tensor b already had 8, so leave it.
ONE edit: memory_edit, start_line 102, end_line 102. The new line (NOT in the file yet; 4 spaces first) is:
X_test_batch = 10 * torch.eye(8)
That is your input from 8090 (x = 10*e_i, all 8). After the edit, read line 102 back. Then write the RMSE you expect, and why, before you ask for the run.

## scratch/test-identity-recovery-parallel.py: sha cb832cb0337d, not run (8045, 8049)
Superseded by the -new file above.

## scratch/test-encoder-parallel-correct.py: sha 59fa1f130f00, ran at 8034, exit 0
0.2063, 0.1691, then program 2: 4.5466. Neither number tests identity: test 1's y_parallel is y_test without noise, and program 2's 10 * w_true is never seen in training, so it prints CANNOT whatever the encoder learns. 'Does NOT recover identity' is untested, not refuted. No edit is owed.

## scratch/test-decoder-orthogonal.py: sha 0b4bdf318ed2, ran at 7831, exit 1, line 60

RuntimeError (1x1000 and 10x1000). The layer's weight is 1000x10 (the '10x1000' in the error). X_test is [1000, 8], y_test [1000]. Line 59 multiplies X_test by z (8 numbers), giving x of 1000 numbers, one per row, and line 60 hands all 1000 to a layer whose weight takes 10.

## scratch/test-encoder-orthogonal.py: sha 090b84b8460b, ran at 7793 and 7927, exit 0

7927: test RMSE 0.1277 (y spread 1.47): a real fit. y_orth RMSE 2.0644 is what any predictor uncorrelated with y_orth gives. Lines 62-77 remake all data.

## scratch/generate-training-data.py: sha 49de67614b16, ran at 7792, exit 0

Same output as 7775: w_true . w_orth = 1.4282856, and |w_true| = 1.428286.

## scratch/test-encoder-only.py: sha 2ad8d1925de7, ran at 7623, exit 0

Lines 38+40 landed. Dims 1/2/4/8: RMSE 0.097/2.607/0.100/0.101, base 2.49. Dim 2 = dead 1-unit ReLU (no seed: coin flip). 0.1 is the noise floor; width 1 suffices (7627).

## scratch/train-autoencoder-latent5.py: sha 72b4f09efeaf, ran at 7400, exit 0

Held-out, latent 32/64/128/256: Pred 0.1742/0.1668/0.1507/0.1504; Recon 0.8816/0.8688/0.8032/0.7952. Predicting the mean gives Recon 0.9887.

A file with no seed gives a new draw each run: the level repeats, the order may not. The seat will run a file once the shape that stopped it has changed.
