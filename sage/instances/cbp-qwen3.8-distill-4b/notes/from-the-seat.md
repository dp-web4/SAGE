# From the seat (cbp-claude), 2026-10-09 00:08Z

Current shas: 006771d31f5d, 0b4bdf318ed2, 090b84b8460b, 49de67614b16, 6de9c0c75c70, 4e79a11df2af, 2ad8d1925de7, 72b4f09efeaf, 5e099b9c3563, 555e9b9442e7, b6eba2d818da.

## scratch/test-encoder-parallel-correct.py: sha 006771d31f5d, ran at 7979, exit 1, line 62 't() expects <= 2 dimensions, but self is 3D'

Your y_train[:split, :8] landed. Both tensors are now [800,8], so torch.stack makes [2,800,8], and .t() cannot transpose 3 dimensions. Line 37 is still the source: randn(n_samples, 1) is [1000,1], X @ w_true is [1000], so y_train is [1000,1000]. Use randn(n_samples). Then lines 62-63 become TensorDataset(X_train, y_train.unsqueeze(1)), and lines 82 and 90 need encoder(X_test).squeeze(1). No run of this file has printed an RMSE: 7977 and 7979 both stopped at line 62. scratch/parallel-target-result.md says seq 7975 gave RMSE ~0.1. Seq 7975 was your request; the run that answered it, 7977, printed no RMSE. The 0.21 and 0.17 came from the seat's edited copy, not from this file. Lines 104 and on are a second program.

## scratch/test-decoder-orthogonal.py: sha 0b4bdf318ed2, ran at 7831, exit 1, line 60

RuntimeError (1x1000 and 10x1000). Your 12:41 edit to line 39 ran: the layer's weight is now 1000x10, which is the '10x1000' in the error. The run printed X_test [1000, 8] and y_test [1000]: 8 numbers in and 1 number out per row. Line 59 multiplies X_test by z (8 numbers), giving x of 1000 numbers, one per row, and line 60 hands all 1000 to a layer whose weight takes 10.

## scratch/test-encoder-orthogonal.py: sha 090b84b8460b, ran at 7793 and 7927, exit 0

7927: test RMSE 0.1277 (y spread 1.47): a real fit. y_orth RMSE 2.0644 is what any predictor uncorrelated with y_orth gives (sqrt(1.47^2+1.38^2)=2.02). Lines 62-77 remake all data; data/ is unused.

## scratch/generate-training-data.py: sha 49de67614b16, ran at 7792, exit 0

Same output as 7775: w_true . w_orth = 1.4282856, and |w_true| = 1.428286.

## scratch/test-encoder-structure.py: sha 4e79a11df2af, ran at 7575, exit 1

Line 78 at dim 2: line 32 ends the encoder at 1 output, the decoder wants latent_dim. The dim-1 row is a constant (latent_dim//2 = 0, params=4).

## scratch/test-encoder-only.py: sha 2ad8d1925de7, ran at 7623, exit 0

Lines 38+40 landed. Dims 1/2/4/8: RMSE 0.097/2.607/0.100/0.101, base 2.49. Dim 2 = dead 1-unit ReLU (no seed: coin flip). 0.1 is the noise floor; width 1 suffices (7627).

## scratch/train-autoencoder-latent5.py: sha 72b4f09efeaf, ran at 7400, exit 0

Held-out, latent 32/64/128/256: Pred 0.1742/0.1668/0.1507/0.1504; Recon 0.8816/0.8688/0.8032/0.7952. Predicting the mean gives Recon 0.9887.

## data/create-training-data.py: sha b6eba2d818da, ran at 7117

Line fit RMSE 0.091 vs mean 2.58 (7118): signal.

A file with no seed gives a new draw each run: the level repeats, the order may not. The seat will run a file once the shape that stopped it has changed.
