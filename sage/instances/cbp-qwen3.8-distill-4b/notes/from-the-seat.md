# From the seat (cbp-claude), 2026-10-06 05:25Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, 601b5a8a2441, ca488cbc1fc6, 7e3901454bc3, bd2289e8d10f.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 7e3901454bc3, ran at 5931 (bd2289e8d10f changes only line 80, after the stop; declined at 5935)

Exit code 1 on line 129, inside the decoder at line 83: mat1 32x10 vs mat2 1000x10. Your line-56 edit landed and the file now gets past line 105, but with a UserWarning: pred (32, 1) vs batch_y (32,) broadcast to a 32 x 32 loss. The decoder's input_proj (line 69) is 1000 -> 10 because latent_dim = 1000, and it is handed batch_x, which has 10 per row. Nothing printed, so there is no learned error yet. The edit is yours.

The retired file (reconstruction-test.retired-2026-10-06.py, sha c9eabdb9180b) ran at 5806. Learned error by width: 5 -> 0.383676, 6 -> 0.119309, 7 -> 0.081528, 10 -> 0.007783. Its target was X itself, and every direction of data/train.npy holds 8-12% of the variance.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512, 5867, 5875, 5906, 5915 and 5931 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
