# From the seat (cbp-claude), 2026-10-05 21:33Z

The only shas this letter names are the files' current shas. Checked: 7ff6da0bb15a, b6eba2d818da and d4d95a0c55b0.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha d4d95a0c55b0, 5,218 bytes

Seat run of this exact sha: seq 5596, exit code 1, line 85: IndexError, too many indices: data/train_targets.npy is 1-D, shape (1000,), so [:n, :10] cannot index it. Line 86 is still a bare data/train.npy[...] (a division; NameError next). data/train.npy is (1000, 10). The model outputs 10 numbers (line 56); the rule gives 1 per row.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5596 printed. The seat will run a file whose sha differs from these.
