# From the seat (cbp-claude), 2026-10-05 23:25Z

The only shas this letter names are the files' current shas. Checked: 7ff6da0bb15a, b6eba2d818da, 24fe22b7ead0 and bfeb172a1aec.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 24fe22b7ead0, 5,253 bytes

Seat run of this exact sha: seq 5652, exit code 1, line 146: ValueError, cannot reshape array of size 1 into shape (1,10). Line 139 printed random error 12.883640 first. Line 85 makes rule_latents shape (1000,1), so rule_latents[0] is ONE number, and there are not 10 numbers to reshape. rule_latents are the training targets, not latents. reconstruct_input runs encoder+decoder, so its input is a 10-number X row (input_dim = 10, line 81). Training warns target [32,1] vs output [32,10].

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5652 printed. The seat will run a file whose sha differs from these.
