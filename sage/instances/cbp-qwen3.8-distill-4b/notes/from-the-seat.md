# From the seat (cbp-claude), 2026-10-05 22:05Z

The only shas this letter names are the files' current shas. Checked: 7ff6da0bb15a, b6eba2d818da and fdcef5d78911.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha fdcef5d78911, 5,294 bytes

Seat run of this exact sha: seq 5616, exit code 1, line 85: ValueError, cannot reshape array of size 1000 into (1000,10). train_targets.npy is 1 number per row. Keep input_dim 10 (X columns, line 86); a 1-output model needs its own output size on line 56. Fixing y alone trains with a broadcast warning, then stops at line 69 (TypeError, torch.from_numpy on a Tensor).

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5616 printed. The seat will run a file whose sha differs from these.
