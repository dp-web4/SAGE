# From the seat (cbp-claude), 2026-10-06 03:36Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, c9eabdb9180b.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha c9eabdb9180b (latent_dim 6), run at 5806, exit code 0

Width 6: random 1.647120, learned 0.119309, Learned/Random ratio 0.072435. Final train loss 0.177414, Test Loss 0.447918.

Widths 10 and 32 are not narrower than the 10-value input, so both can hold the input unchanged. Widths 5 and 6 are narrower. Widths 7 to 9 have not been run.

Test Loss by latent width: 5 -> 0.591237 (5794), 6 -> 0.447918 (5806), 10 -> 0.008894 (5765), 32 -> 0.010251 (5785).

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5806 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
