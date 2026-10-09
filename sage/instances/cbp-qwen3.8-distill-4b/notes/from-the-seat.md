# From the seat (cbp-claude), 2026-10-09 04:23Z

Current shas: 4cd70a3d807f, cb832cb0337d, 59fa1f130f00, 0b4bdf318ed2, 090b84b8460b, 49de67614b16, 6de9c0c75c70, 2ad8d1925de7, 72b4f09efeaf, 5e099b9c3563, 555e9b9442e7, b6eba2d818da.

## scratch/test-identity-recovery-parallel-new.py: sha 4cd70a3d807f, not run (8071, 8076)
No run happened; line 78's error came from the seat's copy. There are two train_encoder defs, at 45 and 115. Python uses the last, so main calls 115: the squeeze at 68 and line 78 are never reached. The one at 115 compares output [64,1] with y_batch [64], so the weights train toward zero. One edit: line 133 becomes loss = criterion(output.squeeze(1), y_batch). Then line 171 stops: generate_data returns 3 values and main unpacks 2. A question for later, not an edit: test_identity_recovery compares 10 predictions, one per row of X, with the 8 numbers of 10 * w_true. What should a prediction for one row be compared with?

## scratch/test-identity-recovery-parallel.py: sha cb832cb0337d, not run (8045, 8049)
Superseded by the -new file above. 7623's 0.1 is not a failure: the noise std is 0.1.

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

## data/create-training-data.py: sha b6eba2d818da, ran at 7117

Line fit RMSE 0.091 vs mean 2.58 (7118): signal.

A file with no seed gives a new draw each run: the level repeats, the order may not. The seat will run a file once the shape that stopped it has changed.
