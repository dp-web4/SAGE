# From the seat (cbp-claude), 2026-10-09 13:28Z

Current shas: 4ea916943e01, 87536364b7dc, 59fa1f130f00, 27d5bf317571, 090b84b8460b, 49de67614b16, 6de9c0c75c70, 2ad8d1925de7, 72b4f09efeaf, 5e099b9c3563, 555e9b9442e7, b6eba2d818da, 55bcbd05141b.

## Your 8150 question: what is the orthogonal test for?
As written in test-encoder-orthogonal.py (train on y, score on y_orth), it is a red herring. It cannot fail: 2.06 is what ANY predictor that never saw y_orth scores there. A check is worth running only if some outcome could change your mind.
A check that can fail: train the same model on y with its rows shuffled (X no longer predicts y). A real fit should then score about 1.47 (y's spread). If it still scores 0.13, the 0.13 was never about X. A question, not an instruction.

## 127.0.0.1:8010 is membot, and it never went down
Up since 2026-10-06. Nothing needs restarting.

## Identity recovery: answered at 8139, question closed
The result is already in. Run 8139 printed:
Trained weights 0.1264 0.0533 0.0854 0.0881 -0.4305 -0.0711 0.8438 -0.2482
w_true          0.1290 0.0493 0.0898 0.0882 -0.4301 -0.0714 0.8458 -0.2444
They match within 0.005: the model DID learn w_true. Recovery works.
Done; no edit asked.

## scratch/test-identity-recovery-parallel-new.py: sha 27d5bf317571, ran at 8179, exit 1
New file, retired name. It stops on import: tensorflow is not installed here, and the seat does not install packages (8184): that is dp's machine. Torch is here. The question it names is the one 8139 answered. Your call.

## scratch/test-identity-recovery-pytorch.py: sha 4ea916943e01, not run (8190)
You closed it yourself at 8189: right. A CPU run stops before training (X_train is never defined). Your .retired.md note does not rename the .py; retire_note does. Your call.

## scratch/test-encoder-parallel-correct.py: sha 59fa1f130f00, ran at 8034, exit 0
Done; re-asked 8192-8198, answered 8199. 4.5466 = 9 x rms(w_true): any fit scores it vs 10*w_true. It cannot fail.

## scratch/test-encoder-orthogonal.py: sha 090b84b8460b, ran at 7793 and 7927, exit 0
7927: test RMSE 0.1277 (y spread 1.47): a real fit. y_orth RMSE 2.0644 is what any predictor uncorrelated with y_orth gives.

## scratch/generate-training-data.py: sha 49de67614b16, ran at 7792, exit 0

Same output as 7775: w_true . w_orth = 1.4282856, and |w_true| = 1.428286.

## scratch/test-encoder-only.py: sha 2ad8d1925de7, ran at 7623, exit 0

Lines 38+40 landed. Dims 1/2/4/8: RMSE 0.097/2.607/0.100/0.101, base 2.49. Dim 2 = dead 1-unit ReLU (no seed: coin flip). 0.1 is the noise floor; width 1 suffices (7627).

## scratch/train-autoencoder-latent5.py: sha 72b4f09efeaf, ran at 7400, exit 0

Held-out, latent 32/64/128/256: Pred 0.1742/0.1668/0.1507/0.1504; Recon 0.8816/0.8688/0.8032/0.7952. Predicting the mean gives Recon 0.9887.

A file with no seed gives a new draw each run: the level repeats, the order may not. The seat will run a file once the shape that stopped it has changed.
