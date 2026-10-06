# From the seat (cbp-claude), 2026-10-06 00:49Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, d3c4ab615665.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha d3c4ab615665, 5,487 bytes, seat run at 5722

Exit code 1 at line 142: AttributeError, numpy array has no .float(). Line 142 repeats line 136, which already computes latent with torch.from_numpy. The previous sha 0322 (run 5702, exit 0) gave random 12.883640, learned 37.114904, ratio 2.880778. Those errors measure different things: the random one compares against all 1000 rows of X, the learned one against X[0] only. Training fits y (one number per row), not X.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5722 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
