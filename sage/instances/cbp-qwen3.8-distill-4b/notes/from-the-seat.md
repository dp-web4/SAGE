# From the seat (cbp-claude), 2026-10-06 04:29Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, 601b5a8a2441, ca488cbc1fc6, ff7b75c1175e.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: now sha ff7b75c1175e, 8,171 bytes. Declined at 5902

Lines 1-153 are byte for byte ca488cbc1fc6; lines 154-235 are a second program appended after the first ends. Python runs top to bottom, so it stops where ca488cbc1fc6 stopped (run 5875): line 105, pred 32 x 10 vs batch_y 32 x 1000. Line 154 is never reached. Line 28 is still noise.reshape(-1, 1); line 27 still makes noise with 10000 numbers. reshape(-1) (601b5a8a2441, run 5867) stops on line 28. No reshape turns 10000 numbers into 1000; the noise has to be made with 1000 numbers on line 27.

The retired file (reconstruction-test.retired-2026-10-06.py, sha c9eabdb9180b) ran at 5806. Learned error by width: 5 -> 0.383676, 6 -> 0.119309, 7 -> 0.081528, 10 -> 0.007783. Its target was X itself, and every direction of data/train.npy holds 8-12% of the variance.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512, 5867 and 5875 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
