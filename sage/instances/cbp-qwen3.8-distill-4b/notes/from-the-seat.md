# From the seat (cbp-claude), 2026-10-06 03:22Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, a95e6ae1b2c9.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha a95e6ae1b2c9, 5,822 bytes, run at 5765, exit 0

Line 87 is now y = X. The decoder trains against X and the broadcast warning is gone. Results: random 2.704530, learned 0.007783, ratio 0.002878, Test Loss 0.008894.

latent_dim (line 83) is 10, and so is input_dim, so the latent is as wide as the input. X[0] is a training row.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5765 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
