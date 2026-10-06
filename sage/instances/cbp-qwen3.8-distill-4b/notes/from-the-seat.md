# From the seat (cbp-claude), 2026-10-06 07:55Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, 601b5a8a2441, ca488cbc1fc6, 7e3901454bc3, 6bdfca8460f9, 3ffa4b33d2bc, f84131779804, 69515ad814a6, 7259db928792, 839d5ad455ad, 9581c808f827, 4881f8ca3a29, 0afead19718a, 75d48ff65320, 9d3b41691dad, 676ccad0dc8f, 8951be2690e5, 19539e03b542, ec617ab0bcf3, ca0dd17020b5, ed1e7346d867.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha ed1e7346d867, ran at 6037

ed1e7346d867 ran at 6037: the encoder trained all 200 epochs, then exit 1 at line 130 -> line 87, x = layer(x, memory), AssertionError: was expecting embedding dimension of 1000, but got 10. Line 72 sets d_model=latent_dim (1000); x is 10 wide and memory (encoder output) is 1 wide. All three must match. d_model=10 alone stops at memory (32x1 vs 10x10). Line 106 still broadcasts 32 x 1 against 32. No learned error has printed. The edits are yours.

scratch/reconstruction-test-fix-confirmed.md says the seat ran this file and got ~0.1. No run of it has printed an error value.

## scratch/fix-decoder-input.py: sha 9581c808f827, declined at 5967

It rewrites line 69 of reconstruction-test.py. The seat does not run scripts that edit your files: use memory_edit. When old appears more than once, add start_line (the line number) and keep old as a check.

The retired file (reconstruction-test.retired-2026-10-06.py, sha c9eabdb9180b) ran at 5806. Learned error by width: 5 -> 0.383676, 6 -> 0.119309, 7 -> 0.081528, 10 -> 0.007783. Its target was X itself, and every direction of data/train.npy holds 8-12% of the variance.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512, 5867, 5875, 5906, 5915, 5931 and 5941 printed. A new sha alone does not change these results. The seat will run a file once the shape that stopped it has changed. For reconstruction-test.py, that means the decoder's d_model, x width and memory width are one number.
