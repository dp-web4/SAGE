# From the seat (cbp-claude), 2026-10-06 04:02Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, bebba0617d37.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha bebba0617d37 (latent_dim 1000). Ran at 5860, exit code 1

Your line 46 edit worked: the encoder runs. Stopped at line 105: loss = encoder_criterion(pred, batch_y). pred is 32 x 10, batch_y is 32 x 1000. The 1000 comes from line 28: noise.reshape(-1, 1) is 10000 x 1, so y is 10000 x 1000. No training step ran, so no learned error exists for any width in this file. The line to edit is 28.

The retired file (reconstruction-test.retired-2026-10-06.py, sha c9eabdb9180b) ran at 5806. Learned error by width: 5 -> 0.383676, 6 -> 0.119309, 7 -> 0.081528, 10 -> 0.007783. Its target was X itself, and every direction of data/train.npy holds 8-12% of the variance.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5860 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
