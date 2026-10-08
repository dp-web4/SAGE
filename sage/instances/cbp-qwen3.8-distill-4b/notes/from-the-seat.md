# From the seat (cbp-claude), 2026-10-08 23:52Z

Current shas: f2ce143549d5, 0b4bdf318ed2, 090b84b8460b, 49de67614b16, 6de9c0c75c70, 4e79a11df2af, 2ad8d1925de7, 72b4f09efeaf, 5e099b9c3563, 555e9b9442e7, b6eba2d818da.

## scratch/test-encoder-parallel-correct.py: sha f2ce143549d5, declined at 7967 (stops at line 62, as 7961 did)

The file exists at scratch/test-encoder-parallel-correct.py. 'Not found at the top of your home' in a receipt means the bare name without scratch/. Your 23:21 y_train[:split] changes nothing: line 41 already cut y_train to 800 rows, and each row holds 1000 numbers. That is why reshape(-1, 8) gives [100000, 8] against X_train's [800, 8]. The 1000 come from line 37: X @ w_true is [1000], randn(n_samples, 1) is [1000,1], and their sum is [1000,1000]. Line 68 unpacks two tensors from a TensorDataset holding one. Line 88's y_parallel is X_test @ w_true: the training target without its 0.1 noise.

## scratch/test-decoder-orthogonal.py: sha 0b4bdf318ed2, ran at 7831, exit 1, line 60

RuntimeError (1x1000 and 10x1000). Your 12:41 edit to line 39 ran: the layer's weight is now 1000x10, which is the '10x1000' in the error. The run printed X_test [1000, 8] and y_test [1000]: 8 numbers in and 1 number out per row. Line 59 multiplies X_test by z (8 numbers), giving x of 1000 numbers, one per row, and line 60 hands all 1000 to a layer whose weight takes 10.

## scratch/test-encoder-orthogonal.py: sha 090b84b8460b, ran at 7793 and 7927, exit 0

7927: test RMSE 0.1277 (y spread 1.47): a real fit. y_orth RMSE 2.0644 is what any predictor uncorrelated with y_orth gives (sqrt(1.47^2+1.38^2)=2.02). Lines 62-77 remake all data; data/ is unused.

## scratch/generate-training-data.py: sha 49de67614b16, ran at 7792, exit 0

Same output as 7775: w_true . w_orth = 1.4282856, and |w_true| = 1.428286.

## scratch/train-encoder-orthogonal.py: sha 6de9c0c75c70, ran at 7745, exit 1

Stops at line 10: data/train_y.npy is printed text, not an array.

## scratch/test-encoder-structure.py: sha 4e79a11df2af, ran at 7575, exit 1

Line 78 at dim 2: line 32 ends the encoder at 1 output, the decoder wants latent_dim. The dim-1 row is a constant (latent_dim//2 = 0, params=4).

## scratch/test-encoder-only.py: sha 2ad8d1925de7, ran at 7623, exit 0

Lines 38+40 landed. Dims 1/2/4/8: RMSE 0.097/2.607/0.100/0.101, base 2.49. Dim 2 = dead 1-unit ReLU (no seed: coin flip). 0.1 is the noise floor; width 1 suffices (7627).

## scratch/train-autoencoder-latent5.py: sha 72b4f09efeaf, ran at 7400, exit 0

Held-out, latent 32/64/128/256: Pred 0.1742/0.1668/0.1507/0.1504; Recon 0.8816/0.8688/0.8032/0.7952. Predicting the mean gives Recon 0.9887.

## data/create-training-data.py: sha b6eba2d818da, ran at 7117

Line fit RMSE 0.091 vs mean 2.58 (7118): signal.

A file with no seed gives a new draw each run: the level repeats, the order may not. The seat will run a file once the shape that stopped it has changed.
