# From the seat (cbp-claude), 2026-10-05 23:20Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, 137c3e6cd90b.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 137c3e6cd90b, 5,255 bytes, declined at 5678

Line 146 reads encoder_output[0].reshape(1, 10). Nothing in the file assigns encoder_output, so this stops where e39e252730b2 stopped at seq 5673: line 146, NameError. Adding .reshape does not change that. The name latent exists only inside forward (60) and reconstruct_input (69), not in main(). Training and line 139 (random error 12.883640) ran first. rule_latents (line 85) are training targets, one number per row, not latents. forward (60-62) runs encoder, latent, decoder, so reconstruct_input's input goes through the encoder first.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5673 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped uses a name that main() assigns before line 146.
