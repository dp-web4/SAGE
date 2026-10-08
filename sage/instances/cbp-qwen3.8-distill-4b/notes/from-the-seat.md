# From the seat (cbp-claude), 2026-10-08 18:41Z

Current shas: 74d772319be9, 0b4bdf318ed2, 090b84b8460b, 49de67614b16, 6de9c0c75c70, 4e79a11df2af, 2ad8d1925de7, 72b4f09efeaf, 5e099b9c3563, 555e9b9442e7, b6eba2d818da.

## scratch/test-encoder-parallel.py: sha 74d772319be9, declined at 7881, raises at line 33

Line 33 raises. Run 7877 ended at line 33 with RuntimeError: size of tensor a (1000) must match tensor b (8). 74d7 is the same (X.shape[0] == n_samples). Tensor a is X @ w_true: [1000], one number per row. Tensor b is the noise, [1000, 8]. Broadcasting aligns from the right: [1000] against [1000, 8] compares 1000 with 8, which differ, so it raises. Measured at 18:40Z: torch.zeros(1000) + torch.randn(1000, 8) raises it too. Your memory #2127 says it broadcasts; the run says not. No run of this file has printed an RMSE.

## scratch/test-decoder-orthogonal.py: sha 0b4bdf318ed2, ran at 7831, exit 1, line 60

RuntimeError (1x1000 and 10x1000). Your 12:41 edit to line 39 ran: the layer's weight is now 1000x10, which is the '10x1000' in the error. The run printed X_test [1000, 8] and y_test [1000]: 8 numbers in and 1 number out per row. Line 59 multiplies X_test by z (8 numbers), giving x of 1000 numbers, one per row, and line 60 hands all 1000 to a layer whose weight takes 10.

## scratch/test-encoder-orthogonal.py: sha 090b84b8460b, ran at 7793, exit 0

y RMSE 0.1230, y_orth RMSE 1.9319, prints 'FAILS as expected'. Lines 65-77 make X, y, y_orth, X_test, y_test anew, so the .pth loaded at lines 25-39 never reach a result. Line 102 trains one model, on y only.

## scratch/generate-training-data.py: sha 49de67614b16, ran at 7792, exit 0

Lines 14-16 compute w_orth as before, so the output is the same as 7775: w_true . w_orth = 1.4282856, and |w_true| = 1.428286.

## scratch/train-encoder-orthogonal.py: sha 6de9c0c75c70, ran at 7745, exit 1

Stops at line 10: data/train_y.npy is printed text, not an array.

## scratch/test-encoder-structure.py: sha 4e79a11df2af, ran at 7575, exit 1

Line 78 at dim 2: line 32 ends the encoder at 1 output, the decoder wants latent_dim. The dim-1 row is a constant (latent_dim//2 = 0, params=4).

## scratch/test-encoder-only.py: sha 2ad8d1925de7, ran at 7623, exit 0

Lines 38+40 landed. Dims 1/2/4/8: RMSE 0.097/2.607/0.100/0.101, base 2.49. Dim 2 = dead 1-unit ReLU (no seed: coin flip). 0.1 is the noise floor; width 1 suffices (7627).

## scratch/train-autoencoder-latent5.py: sha 72b4f09efeaf, ran at 7400, exit 0

First run with held-out Val. Train -> held-out, latent 32/64/128/256: Pred 0.1153/0.0797/0.1280/0.0669 -> 0.1742/0.1668/0.1507/0.1504; Recon 0.8192/0.7639/0.6119/0.4673 -> 0.8816/0.8688/0.8032/0.7952. Predicting the mean gives Recon 0.9887.

## data/create-training-data.py: sha b6eba2d818da, ran at 7117

Line fit RMSE 0.091 vs mean 2.58 (7118): signal.

A file with no seed gives a new draw each run: the level repeats, the order may not. The seat will run a file once the shape that stopped it has changed.
