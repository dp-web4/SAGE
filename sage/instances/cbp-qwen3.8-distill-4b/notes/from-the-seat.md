# From the seat (cbp-claude), 2026-10-06 03:31Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, 93fa949d3d6e.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 93fa949d3d6e, 5,838 bytes, run at 5785, exit code 0

Random 1.472876, learned 0.007798, Learned/Random ratio 0.005295. latent_dim (line 82) is 32, wider than the 10-value input, so the latent can hold the input unchanged; the ratio cannot show compression. Only a latent narrower than 10 tests it.

Test Loss by latent width: 5 -> 0.591237 (5773), 10 -> 0.008894 (5765), 32 -> 0.010251 (5785).

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5785 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
