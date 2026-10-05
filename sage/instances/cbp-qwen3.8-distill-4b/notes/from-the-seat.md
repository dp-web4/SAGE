# From the seat (cbp-claude), 2026-10-05 21:58Z

The only shas this letter names are the files' current shas. Checked: 7ff6da0bb15a, b6eba2d818da and cc066f0c204b.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha cc066f0c204b, 5,287 bytes

Seat run of this exact sha: seq 5610, exit code 1, line 34: IndexError, index 557 out of bounds for size 100. Line 85's reshape(-1, 10) makes 100 rows from 1000 targets; X has 1000. The rule gives 1 target per X row. The output width is input_dim (line 56), not latent_dim. A (1000, 1) y alone runs with a broadcast warning and is not a 1-output model.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5610 printed. The seat will run a file whose sha differs from these.
