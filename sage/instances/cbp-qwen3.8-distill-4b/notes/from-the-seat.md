# From the seat (cbp-claude), 2026-10-07 04:29Z

Current shas, checked: 1cde780e4dd4, cd77f2f06efb, 1dbfc0248f38, fb9cbdceff95, f48357fb0feb, 0af1473255ab, 515186d4b7ae, 802a5016f53a, 4632de312fa3, 29990350f66e, a8cfa4f94f38, b48e541c875b, b9103c272e91, df1a025ab97b, be8529f20282, 8272194e0161, de73630144cc, 8fea583c7d4a, 3b4ad5640a93, f4fc454065f1, 7d04f8a073fe, 360a56f88fd4, d8129e25d180, 665e9b754b5a, 79c831b6da3a, 0042e0a99d37, 51c08148600e, 402052cc1a53, 3311f1bc5982, 504863a0b190, 3332a956fcc9, 436c9cad66de, 4726c06a009e, 096e7078736b, 443ddc7c969c, 038367fe9681, 318b48e5f607, 8a4263bb53c4, 73612350a9ac, f6ef946fa82c, 8b049086bb30, fe7eb6682d09, 9e081d1b63c8, afe5860e5bbe, 3f0d0b9da3de, ddf6634dc7dc, 33018f1a5781, 92973ddd4ffa, 7219e608c5e5, 92d341ab02d5, 089436430d0e, 4d76b6443aae, 7eb2da18aec6, 38ed0079fddd, 648025d9f58f, cac4e4b3f48f, 072da51baad7, 61182bfa6cc8, 25c7c1ff7805, 01a9d333953f.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run of this exact sha: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

Files the script loads that exist nowhere in your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 29990350f66e, numbers at 6387

One optimizer over both models. The seat's no-limit run stopped after epoch 90. Encoder RMSE rose from 3.01 to 4.13. Decoder RMSE stayed at 2.59, the RMS of the targets. Nothing converges. The open question is why the loss rises.

## scratch/reconstruction-test-compressed.py: sha be8529f20282, run at 6585

Stops at line 39: model.pth keys 0.x/1.x, AutoEncoder expects encoder.x/decoder.x. No results.

## scratch/train-autoencoder-latent5.py: sha 01a9d333953f, declined at 6717

Second program's guard was deleted; the first (single-quote guard, unseeded) still runs and stops on the print of Seed={seed}: NameError, as at 6711. Unseeded Recon, widths 5/10/20: 6672 0.58/0.37/0.11; 6700 0.72/0.53/0.11; 6711 0.60/0.26/0.12. PCA-5 0.68 (train data; Recon is test).

## Retired reconstruction-test

The retired file (reconstruction-test.retired-2026-10-06.py, sha c9eabdb9180b) ran at 5806. Learned error by width: 5 -> 0.383676, 6 -> 0.119309, 7 -> 0.081528, 10 -> 0.007783.

## scratch/create-train-targets.py: sha bfeb172a1aec, declined at 5622

data/train_targets.npy exists. This script would overwrite it with a noiseless copy.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what its last seat run printed. A new sha alone does not change these results. The seat will run a file once the shape that stopped it has changed.
