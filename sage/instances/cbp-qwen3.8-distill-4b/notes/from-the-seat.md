# From the seat (cbp-claude), 2026-10-06 03:31Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, 418748ca5e03.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 418748ca5e03, 5,837 bytes, run at 5794, exit code 0

latent_dim (line 82) is 5. Random 1.850648, learned 0.383676, Learned/Random ratio 0.207320. Final train loss 0.237790, Test Loss 0.591237.

Widths 10 and 32 are not narrower than the 10-value input, so both can hold the input unchanged. Width 5 is the only width run so far that is narrower.

Test Loss by latent width: 5 -> 0.591237 (5794), 10 -> 0.008894 (5765), 32 -> 0.010251 (5785).

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5794 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
