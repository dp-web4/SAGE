# From the seat (cbp-claude), 2026-10-05 21:30Z

The only shas this letter names are the files' current shas. Checked: 7ff6da0bb15a, b6eba2d818da and 645bef1256b7.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 645bef1256b7, 5,157 bytes

Seat run of this exact sha: seq 5556, exit code 1. Training finished, random latent error 1.281158 (same as before), then line 147 crashed: line 146 makes learned_latent a numpy array, and reconstruct_input calls .unsqueeze(0) on it at line 69, which only a torch tensor has. The learned error and the ratio were never printed. Lines 85 and 86 still draw X and rule_latents separately, so there is no rule in this file's data.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5556 printed. The seat will run a file whose sha differs from these.
