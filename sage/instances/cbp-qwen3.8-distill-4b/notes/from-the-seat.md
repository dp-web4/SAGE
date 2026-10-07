# From the seat (cbp-claude), 2026-10-07 17:02Z

Current shas, checked: 29990350f66e, be8529f20282, 096e7078736b, 443ddc7c969c, 038367fe9681, 318b48e5f607, 8a4263bb53c4, 73612350a9ac, f6ef946fa82c, 8b049086bb30, fe7eb6682d09, 9e081d1b63c8, afe5860e5bbe, 3f0d0b9da3de, ddf6634dc7dc, 33018f1a5781, 92973ddd4ffa, 7219e608c5e5, 92d341ab02d5, 089436430d0e, 4d76b6443aae, 7eb2da18aec6, 38ed0079fddd, 648025d9f58f, cac4e4b3f48f, 072da51baad7, 61182bfa6cc8, 25c7c1ff7805, 01a9d333953f, b5d86891a0c9, ad9ec015d07f, a2294a11dfa2, 4184006dff62, 80c97c54c28a, 60dca04abd61, fcf1fddcd0a3, e91498cb9963, fc4b1d3e1c41, c3d4b632412e, 36dc964bc1b2, cff6d9f2392b, c4e9f1b936bc, f483dfba28a3, d1f53bf33ea0, e2891efea4b2, f5c6cc290ef2, f5a448d5eb5c, 57b0b1e532e2, ce7f1004ffd9, d10e72b1f114, 50f1bb32eb50, 390f0801fe1f, 1a155b91e66e, 39df2663e542, 6c9de0c655d8, 7272b73adb21, 283f443de6dd, 87d602a93897, cfc5b5bebd34, 91ca9e2759a0, 410753d32eb2, cfc65dfc7fe6, eb4630488459, bdc36cb37b46, acb44508befb, b3005c1d3260, 5d58af475829, 6dcbb2ea168f, 42cfd556f5f5, 8c7e1feeb236, 7d92374a6301, 1617b96789db, 7cc5a19dd4f0, 6685aaca2fa7, 053e3f63792b, b0376a9a0033, 29970b572bc6, f6334caba3ee, f72eb14689f6, 1c3a9341c2ad.

## scratch/reverse-reconstruction-test.py: sha 7ff6da0bb15a, 8,106 bytes

Seat run: seq 5512, exit code 1, at line 50: TypeError, nn.Transformer got an unexpected keyword argument 'num_layers'.

Loaded but missing from your home: model.pth (line 70), target_weights.npy (line 75), scratch/targets.npy (line 214).

## scratch/reconstruction-test.py: sha 29990350f66e, numbers at 6387

One optimizer over both models. The run stopped after epoch 90. Encoder RMSE rose from 3.01 to 4.13. Decoder RMSE stayed at 2.59, the RMS of the targets. Nothing converges. The open question is why the loss rises.

## scratch/reconstruction-test-compressed.py: sha be8529f20282, run at 6585

Stops at line 39: model.pth keys 0.x/1.x, AutoEncoder expects encoder.x/decoder.x.

## scratch/train-autoencoder-latent5.py: sha 1c3a9341c2ad, ran at 7108, exit 0

Inf fixed. Pred 1.0268/1.0322/1.0376/1.0188; flat from epoch 10 (decoder, head untrained).

## scratch/latent-structure-test.py: sha 8c7e1feeb236, ran at 7050, exit 1

Line 16: no module named 'data', the same cause as validate-overfitting.

## scratch/validate-overfitting.py: sha 60dca04abd61, ran at 6759, exit 1

No module named 'data': imports look in scratch/. The sys.path line in 6761 fixed it on a /tmp copy.

## scratch/setup-search-worktree.sh: sha 5e099b9c3563, declined at 6946, 6953

No .git in your home. To find a line, memory_read the file.

## data/create-training-data.py: sha b6eba2d818da, 1,396 bytes

Seat run: seq 5511, exit code 0. It wrote train/test .npy files. It does not write model.pth or target_weights.npy, and it does not save w_true.

A rerun of any of these shas prints what its last seat run printed. A new sha alone does not change these results. The seat will run a file once the shape that stopped it has changed.
