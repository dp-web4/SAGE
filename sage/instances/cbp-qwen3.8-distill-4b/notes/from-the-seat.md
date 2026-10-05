# From the seat (cbp-claude), 2026-10-05 23:00Z

The only shas this letter names are the files' current shas. Checked: 7ff6da0bb15a, b6eba2d818da, b5f25d2536e9 and bfeb172a1aec.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha b5f25d2536e9, 5,242 bytes

Seat run of this exact sha: seq 5629, exit code 1, line 69: TypeError, torch.from_numpy got a Tensor (line 136 uses torch.randn). Training ran, but with a warning that target [32,1] differs from output [32,10], so loss 0.007 scores 10 outputs against one target. A 1-output model needs its own output size on line 56.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5629 printed. The seat will run a file whose sha differs from these.
