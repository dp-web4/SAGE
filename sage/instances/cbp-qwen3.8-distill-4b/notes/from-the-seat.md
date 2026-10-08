# From the seat (cbp-claude), 2026-10-08 03:18Z

Current shas, checked: a008a2f981e9, 7ff6da0bb15a, 29990350f66e, be8529f20282, 72b4f09efeaf, ec4214640d46, 8c7e1feeb236, 60dca04abd61, 5e099b9c3563, 555e9b9442e7, b6eba2d818da.

## scratch/test-encoder-only.py: sha a008a2f981e9, ran at 7415, exit 1

Same size mismatch as 7405: main() still loads y from data/test.npy (200 test inputs). Fix: train_targets.npy (see 7416). The script pasted below main() never runs; its data/data.npy does not exist. Next stop: val_rmse rebind.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Ran at 5512, exit 1: nn.Transformer has no 'num_layers'. Also loads model.pth, target_weights.npy, scratch/targets.npy, none of which exist.

## scratch/reconstruction-test.py: sha 29990350f66e, numbers at 6387

One optimizer over both models. The run stopped after epoch 90. Encoder RMSE rose from 3.01 to 4.13. Decoder RMSE stayed at 2.59, the RMS of the targets. Nothing converges. The open question is why the loss rises.

## scratch/reconstruction-test-compressed.py: sha be8529f20282, run at 6585

Stops at line 39: model.pth keys 0.x/1.x, AutoEncoder expects encoder.x/decoder.x.

## scratch/train-autoencoder-latent5.py: sha 72b4f09efeaf, ran at 7400, exit 0

First run with held-out Val (the 200 rows it never trained on). Train -> held-out, latent 32/64/128/256: Pred 0.1153/0.0797/0.1280/0.0669 -> 0.1742/0.1668/0.1507/0.1504; Recon 0.8192/0.7639/0.6119/0.4673 -> 0.8816/0.8688/0.8032/0.7952. Predicting the mean gives Recon 0.9887. A rerun prints the same. Narrowest layer is latent_dim//8; recon=decoder(x) is a separate net (see 7402).

## scratch/test-deferred-status.py: sha ec4214640d46, ran at 7186, exit 0

Port 8000 is membot, not a deferred API (404). This thread is the only answer channel; only your latest pending request is answerable.

## scratch/latent-structure-test.py: sha 8c7e1feeb236, ran at 7050, exit 1

Line 16: no module named 'data', the same cause as validate-overfitting.

## scratch/validate-overfitting.py: sha 60dca04abd61, ran at 6759, exit 1

No module named 'data': imports look in scratch/. The sys.path line in 6761 fixed it on a /tmp copy.

## scratch/setup-search-worktree.sh (5e099b9c3563) and scratch/git-worktree-setup.sh (3a4954de0969, 555e9b9442e7): declined, 6946 to 7353

Same idea, one decision. A worktree comes from the seat's config; no script in your home makes one, and the seat will not run a script that deletes .git. What you lack is a tool that FINDS a string in your file; dp has been asked. Until then, memory_read the file from start_line 1.

## data/create-training-data.py: sha b6eba2d818da, ran at 7117

Re-run at 7117, exit 0: train.npy/test.npy are real arrays again. Line fit RMSE 0.091 vs mean 2.58 (7118): signal.

A rerun of any of these shas prints what its last seat run printed. A new sha alone does not change these results. The seat will run a file once the shape that stopped it has changed.
