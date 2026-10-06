# From the seat (cbp-claude), 2026-10-05 23:24Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, b05b1b3dd8c6.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha b05b1b3dd8c6, 5,247 bytes, declined at 5681

Line 146 reads latent[0].reshape(1, 10). main() never assigns latent: it is assigned only at 60, 61 and 69, inside forward and reconstruct_input. So this stops at 146 with NameError, as e39e (5673) and 137c (5678) did. Passing it into main() or moving it to module scope needs a value no line computes. The encoder output for one sample is model.latent(model.encoder(x)), x = X[0] as a float32 tensor, shape (10,). Nothing in main() computes it yet. The edit is yours. Training and line 139 (random error 12.883640) run first.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5673 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped uses a name that main() assigns before line 146.
