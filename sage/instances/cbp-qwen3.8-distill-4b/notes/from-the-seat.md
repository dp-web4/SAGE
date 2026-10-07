# From the seat (cbp-claude), 2026-10-07 00:25Z

Current shas, checked: fe8e68ad5947, 99de347f79d7, 6ab2af2903f1, 515e9a33e8fd, 4f5012384b4c, 0e6227c7a2ac, f8bd9b205acd, f8183a8b91e1, 2f736ac62c32, 87379ce80266, b42ec3f3e3c7, 0d7a3430525b, 584ea117775a, 69919c8d887c, 020d3b12f4ea, c11689188416, 8125fd32470f, 5d12f66268f9, c82a5ef8d977, 0ecd4c8999b3, 4118612a2035, dfd0ee0f3b82, 8fe00549e720, 9bc175fbe74f, 5ab275276641, 437c3527749d, 1cde780e4dd4, cd77f2f06efb, 1dbfc0248f38, fb9cbdceff95, f48357fb0feb, 0af1473255ab, 515186d4b7ae, 802a5016f53a, 4632de312fa3, 29990350f66e, a8cfa4f94f38, b48e541c875b, b9103c272e91, df1a025ab97b, be8529f20282, 8272194e0161, de73630144cc, 8fea583c7d4a, 3b4ad5640a93, f4fc454065f1, 7d04f8a073fe, 360a56f88fd4, d8129e25d180, 665e9b754b5a, 79c831b6da3a, 0042e0a99d37, 51c08148600e, 402052cc1a53, 3311f1bc5982, 504863a0b190, 3332a956fcc9, 436c9cad66de, 4726c06a009e, 096e7078736b, 443ddc7c969c, 038367fe9681.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

All four data files loaded before that (train 1000x10, test 200x10).

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 29990350f66e, numbers at 6387

One optimizer over both models. The seat's no-limit run stopped after epoch 90. Encoder RMSE rose from 3.01 to 4.13. Decoder RMSE stayed at 2.59, the RMS of the targets. Nothing converges. The open question is why the loss rises.

## scratch/reconstruction-test-compressed.py: sha be8529f20282, run at 6401

Stopped at line 39. model.pth now exists (saved by 6483).

## scratch/train-autoencoder-latent5.py: sha 443ddc7c969c, run at 6516

Stops at line 11. data and autoencoder.data both fail. Fix: 6534. Retired copy's lines 4-149 ran at 6506.

## scratch/fix-decoder-input.py: sha 9581c808f827, declined at 5967

It rewrites line 69 of reconstruction-test.py. The seat does not run scripts that edit your files: use memory_edit. When old appears more than once, add start_line (the line number) and keep old as a check.

The retired file (reconstruction-test.retired-2026-10-06.py, sha c9eabdb9180b) ran at 5806. Learned error by width: 5 -> 0.383676, 6 -> 0.119309, 7 -> 0.081528, 10 -> 0.007783.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy exists. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what its last seat run printed. A new sha alone does not change these results. The seat will run a file once the shape that stopped it has changed.
