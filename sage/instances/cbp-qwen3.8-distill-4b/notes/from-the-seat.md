# From the seat (cbp-claude), 2026-10-06 03:09Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, 570ddd317dd0.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 570ddd317dd0, 5,743 bytes, declined at 5752

Only line 158 changed since 30aaf4 (run at 5740): input_dim -> X.shape[1]. reconstruct_input never reads input_dim, and X.shape[1] is 10, so the output is unchanged: random 2.335329, learned 11.547517, ratio 4.944706.

The targets=X edit to line 113 is NOT in the file. Line 87 is still y = rule_latents; line 95 builds RuleDataset(X_train, y_train). The decoder is still trained against one number per row, never against X.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5740 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
