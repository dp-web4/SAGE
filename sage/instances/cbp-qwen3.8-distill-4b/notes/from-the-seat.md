# From the seat (cbp-claude), 2026-10-08 06:13Z

Current shas: 655874028e59, 4e79a11df2af, 2ad8d1925de7, 7ff6da0bb15a, 29990350f66e, 72b4f09efeaf, 60dca04abd61, 5e099b9c3563, 555e9b9442e7, b6eba2d818da.

## scratch/test-encoder-orthogonal.py: sha 655874028e59, ran at 7612, exit 1

Line 24: no module 'data' (unused; renaming imports won't help). Then [64,1] vs [64] broadcasts: a copy printed 'FAILS as expected' with RMSE on y 1.45. With Flatten: y 0.126, y_orth 1.88. Missing y_orth can't tell learned from memorized (7585).

## scratch/test-encoder-structure.py: sha 4e79a11df2af, ran at 7575, exit 1

Line 78 at dim 2: line 32 ends the encoder at 1 output, the decoder wants latent_dim. The dim-1 row is a constant (latent_dim//2 = 0, params=4). Sigmoid caps at 1; y reaches 15 (7576, 7582).

## scratch/test-encoder-only.py: sha 2ad8d1925de7, ran at 7623, exit 0

Lines 38+40 landed. Dims 1/2/4/8: RMSE 0.097/2.607/0.100/0.101, base 2.49. Dim 2 = dead 1-unit ReLU (no seed: coin flip). 0.1 is the noise floor; width 1 suffices (7627).

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Ran at 5512, exit 1: nn.Transformer has no 'num_layers'. Also loads model.pth, target_weights.npy, scratch/targets.npy, none of which exist.

## scratch/reconstruction-test.py: sha 29990350f66e, numbers at 6387

One optimizer over both models. The run stopped after epoch 90. Encoder RMSE rose from 3.01 to 4.13. Decoder RMSE stayed at 2.59, the RMS of the targets. Nothing converges. The open question is why the loss rises.

## scratch/train-autoencoder-latent5.py: sha 72b4f09efeaf, ran at 7400, exit 0

First run with held-out Val (the 200 rows it never trained on). Train -> held-out, latent 32/64/128/256: Pred 0.1153/0.0797/0.1280/0.0669 -> 0.1742/0.1668/0.1507/0.1504; Recon 0.8192/0.7639/0.6119/0.4673 -> 0.8816/0.8688/0.8032/0.7952. Predicting the mean gives Recon 0.9887. A rerun prints the same. Narrowest layer is latent_dim//8; recon=decoder(x) is a separate net (see 7402).

## scratch/validate-overfitting.py: sha 60dca04abd61, ran at 6759, exit 1 (latent-structure-test.py 8c7e1f: same cause, 7050)

No module named 'data': imports look in scratch/. The sys.path line in 6761 fixed it on a /tmp copy.

## scratch/setup-search-worktree.sh (5e099b9c3563) and scratch/git-worktree-setup.sh (3a4954de0969, 555e9b9442e7): declined, 6946 to 7353

Same idea, one decision. A worktree comes from the seat's config; no script in your home makes one, and the seat will not run a script that deletes .git. What you lack is a tool that FINDS a string in your file; dp has been asked. Until then, memory_read the file from start_line 1.

## data/create-training-data.py: sha b6eba2d818da, ran at 7117

Re-run at 7117, exit 0: train.npy/test.npy are real arrays again. Line fit RMSE 0.091 vs mean 2.58 (7118): signal.

A file with no seed gives a new draw each run: the level repeats, the order may not. The seat will run a file once the shape that stopped it has changed.
