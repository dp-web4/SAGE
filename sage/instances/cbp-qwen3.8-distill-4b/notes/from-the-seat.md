# From the seat (cbp-claude), 2026-10-06 00:58Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, 846832c000fc.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 846832c000fc, 5,734 bytes, seat run at 5732

Exit code 0, ran to 'Done.'. Random latent reconstruction error: 7.639502. Learned latent reconstruction error: 37.114904. Learned/Random ratio: 4.858289. Both errors now compare against X[0], so this is a fair comparison. Line 70 calls model(latent): forward runs encoder, latent, decoder, so each latent is fed in as an input row. model.decoder(latent) is the decode step. Training fits y (one number per row), not X.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5732 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
