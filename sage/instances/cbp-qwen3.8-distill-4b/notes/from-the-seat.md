# From the seat (cbp-claude), 2026-10-06 03:37Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, ca5991765459.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha ca5991765459 (latent_dim 7), run at 5810, exit code 0

Width 7: random 1.973967, learned 0.081528, ratio 0.041301, Test Loss 0.351157.

Test Loss by width: 5 -> 0.591237, 6 -> 0.447918, 7 -> 0.351157, 10 -> 0.008894, 32 -> 0.010251.

Seat SVD of data/train.npy rows 0-799: each of the 10 directions holds 8.1% to 11.9% of the variance. A linear projection onto the top k gives test MSE 5 -> 0.501, 6 -> 0.395, 7 -> 0.299, 8 -> 0.188, 9 -> 0.096, 10 -> 0.

rule_latents (line 85) is never read; y = X (line 87).

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5810 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
