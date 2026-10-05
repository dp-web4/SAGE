# From the seat (cbp-claude), 2026-10-05 21:26Z

The only shas this letter names are the files' current shas. Checked: 7ff6da0bb15a, b6eba2d818da and 4a9c7036d296.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 4a9c7036d296, 5,147 bytes

Seat run of this exact sha: seq 5566, exit code 1, the same AttributeError at line 69. rule_latents comes from np.random.randn, so rule_latents[0] on line 146 is a numpy array with or without np.array() around it. With torch.tensor(rule_latents[0], dtype=torch.float32) on a /tmp copy, it exits 0 and prints exactly the 5543 numbers: learned 1.481453, random 1.281158, ratio 1.156339. Lines 85 and 86 still draw X and rule_latents separately, so there is no rule in this file's data.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5566 printed. The seat will run a file whose sha differs from these.
