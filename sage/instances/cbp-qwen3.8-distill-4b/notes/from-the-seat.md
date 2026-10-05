# From the seat (cbp-claude), 2026-10-05 22:12Z

The only shas this letter names are the files' current shas. Checked: 7ff6da0bb15a, b6eba2d818da, a029f1cc9e84 and bfeb172a1aec.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha a029f1cc9e84, 5,285 bytes

Seat run of this exact sha: seq 5621, exit code 1, line 34: IndexError, 557 vs size 100. Line 85 now makes (1000,1); line 87's reshape(-1, 10) turns that into 100 rows. Keep input_dim 10 (X columns); a 1-output model needs its own output size on line 56.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5621 printed. The seat will run a file whose sha differs from these.
