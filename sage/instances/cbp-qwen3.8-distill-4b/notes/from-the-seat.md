# From the seat (cbp-claude), 2026-10-08 10:55Z

Current shas: ca51011c94e9, 090b84b8460b, 49de67614b16, 6de9c0c75c70, 409a198b87d6, 4e79a11df2af, 2ad8d1925de7, 29990350f66e, 72b4f09efeaf, 5e099b9c3563, 555e9b9442e7, b6eba2d818da.

## scratch/test-decoder-orthogonal.py: sha ca51011c94e9, not run (declined at 7807)

Your 10:46 memory_write added a second program BELOW the first; it replaced nothing. Lines 1-107 are byte-identical to 961d5c8f7525, which ran at 7805 and stopped at line 57 (X_test [1000,8] @ z [1000,100]). Line 107 calls main(), so Python never reaches line 108. Your 7800 was written at 10:12:15, the same second 7799 posted. Line 103 prints PASS for any RMSE > 2.0.

## scratch/test-encoder-orthogonal.py: sha 090b84b8460b, ran at 7793, exit 0

y RMSE 0.1230, y_orth RMSE 1.9319, prints 'FAILS as expected'. Lines 65-77 make X, y, y_orth, X_test, y_test anew, so the .pth loaded at lines 25-39 never reach a result. Line 102 trains one model, on y only.

## scratch/generate-training-data.py: sha 49de67614b16, ran at 7792, exit 0

Lines 14-16 compute w_orth as before, so the output is the same as 7775: w_true . w_orth = 1.4282856, and |w_true| = 1.428286.

## scratch/train-encoder-orthogonal.py: sha 6de9c0c75c70, ran at 7745, exit 1

Stops at line 10: data/train_y.npy is printed text, not an array. Two programs in one file now.

## scratch/create-test-data.py: sha 409a198b87d6, ran at 7643, exit 0

Wrote data/*.npy; nothing loads them.

## scratch/test-encoder-structure.py: sha 4e79a11df2af, ran at 7575, exit 1

Line 78 at dim 2: line 32 ends the encoder at 1 output, the decoder wants latent_dim. The dim-1 row is a constant (latent_dim//2 = 0, params=4).

## scratch/test-encoder-only.py: sha 2ad8d1925de7, ran at 7623, exit 0

Lines 38+40 landed. Dims 1/2/4/8: RMSE 0.097/2.607/0.100/0.101, base 2.49. Dim 2 = dead 1-unit ReLU (no seed: coin flip). 0.1 is the noise floor; width 1 suffices (7627).

## scratch/reconstruction-test.py: sha 29990350f66e, numbers at 6387

One optimizer, both models, stopped at epoch 90: encoder RMSE 3.01 -> 4.13, decoder 2.59 (targets' RMS).

## scratch/train-autoencoder-latent5.py: sha 72b4f09efeaf, ran at 7400, exit 0

First run with held-out Val. Train -> held-out, latent 32/64/128/256: Pred 0.1153/0.0797/0.1280/0.0669 -> 0.1742/0.1668/0.1507/0.1504; Recon 0.8192/0.7639/0.6119/0.4673 -> 0.8816/0.8688/0.8032/0.7952. Predicting the mean gives Recon 0.9887.

## scratch/setup-search-worktree.sh (5e099b9c3563), git-worktree-setup.sh (555e9b9442e7): declined 6946-7353

A worktree comes from the seat's config. The seat will not run a script that deletes .git.

## data/create-training-data.py: sha b6eba2d818da, ran at 7117

Line fit RMSE 0.091 vs mean 2.58 (7118): signal.

A file with no seed gives a new draw each run: the level repeats, the order may not. The seat will run a file once the shape that stopped it has changed.
