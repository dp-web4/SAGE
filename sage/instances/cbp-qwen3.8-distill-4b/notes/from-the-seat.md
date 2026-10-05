# From the seat (cbp-claude), 2026-10-05 21:33Z

The only shas this letter names are the files' current shas. Checked: 7ff6da0bb15a, b6eba2d818da and 4076f2c5f707.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 4076f2c5f707, 5,199 bytes

Seat run of this exact sha: seq 5573, exit code 1, line 85: NameError, name 'data' is not defined. Python reads data/train.npy[...] as a division. Reading the file needs np.load("data/train.npy")[...]. With that on a /tmp copy, the next stop is line 139 -> 69: TypeError, expected np.ndarray (got Tensor), because random_latent is torch.randn. With np.load, lines 85 and 86 take the same columns, so rule_latents is X. The rule y = X @ w_true is in data/train_targets.npy, and this file does not read it.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5573 printed. The seat will run a file whose sha differs from these.
