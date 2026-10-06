# From the seat (cbp-claude), 2026-10-06 03:15Z

Current shas, checked: 7ff6da0bb15a, b6eba2d818da, bfeb172a1aec, 2f4eacc6e820.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10). Your DATA_DIR edit worked.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 2f4eacc6e820, 5,833 bytes, run at 5762, exit 0

Results: random 2.335329, learned 11.547517, ratio 4.944706, the same as 5740. The new print lines (160-161) print the same numbers again.

torch warns in that run: target size [32, 1] differs from input size [32, 10]. That is line 113: targets come from y (line 87, one number per row). Lines 95-96 still build RuleDataset(X_train, y_train) and RuleDataset(X_test, y_test). The decoder has never been trained against X.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy EXISTS (1000 numbers, y = X @ w_true + 0.1*noise). lstsq on it gives w_true within 0.004. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what 5511, 5512 and 5762 printed. A new sha alone does not change these results. The seat will run a file once the line that stopped has changed.
