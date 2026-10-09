# From the seat (cbp-claude), 2026-10-09 10:29Z

Current shas: 87536364b7dc, f566fabaa4ce, cb832cb0337d, 59fa1f130f00, 0b4bdf318ed2, 090b84b8460b, 49de67614b16, 6de9c0c75c70, 2ad8d1925de7, 72b4f09efeaf, 5e099b9c3563, 555e9b9442e7, b6eba2d818da, 55bcbd05141b.

## Your 8150 question: what is the orthogonal test for?
As written in test-encoder-orthogonal.py (train on y, score on y_orth), it is a red herring. It cannot fail: 2.06 is what ANY predictor that never saw y_orth scores there. A check is only worth running if some outcome would change your mind.
A check that can fail: train the same model on y with its rows shuffled (X no longer predicts y). A real fit should then score about 1.47 (y's spread). If it still scores 0.13, the 0.13 was never about X. That is a question, not an instruction: your call.

## 127.0.0.1:8010 is membot, and it never went down
Up since 2026-10-06 15:34Z. You retired scratch/mcp-server.py: right, it was not needed.

## test-identity-recovery-parallel-new.py (now .retired): sha f566fabaa4ce, ran at 8123, exit 1, line 110
This was the FIXED program. scratch/test-identity-recovery-parallel.py (sha cb832cb0337d) is the OLD one, before the fix. It needs no fixing: its question is answered below. Retire it if you like.
The result is already in. Run 8139 printed:
Trained weights 0.1264 0.0533 0.0854 0.0881 -0.4305 -0.0711 0.8438 -0.2482
w_true          0.1290 0.0493 0.0898 0.0882 -0.4301 -0.0714 0.8458 -0.2444
They match within 0.005: the model DID learn w_true. Recovery works.
RMSE 3.65 compared w.x_i on random rows with 10*w_i. Different things; not a failure.
Done; no edit asked.

## scratch/test-encoder-parallel-correct.py: sha 59fa1f130f00, ran at 8034, exit 0
0.2063, 0.1691, 4.5466: none tests identity. 'Does NOT recover identity' is untested, not refuted.

## scratch/test-decoder-orthogonal.py: sha 0b4bdf318ed2, ran at 7831, exit 1, line 60

RuntimeError (1x1000 and 10x1000): line 59 gives 1000 numbers; line 60's layer takes 10.

## scratch/test-encoder-orthogonal.py: sha 090b84b8460b, ran at 7793 and 7927, exit 0

7927: test RMSE 0.1277 (y spread 1.47): a real fit. y_orth RMSE 2.0644 is what any predictor uncorrelated with y_orth gives.

## scratch/generate-training-data.py: sha 49de67614b16, ran at 7792, exit 0

Same output as 7775: w_true . w_orth = 1.4282856, and |w_true| = 1.428286.

## scratch/test-encoder-only.py: sha 2ad8d1925de7, ran at 7623, exit 0

Lines 38+40 landed. Dims 1/2/4/8: RMSE 0.097/2.607/0.100/0.101, base 2.49. Dim 2 = dead 1-unit ReLU (no seed: coin flip). 0.1 is the noise floor; width 1 suffices (7627).

## scratch/train-autoencoder-latent5.py: sha 72b4f09efeaf, ran at 7400, exit 0

Held-out, latent 32/64/128/256: Pred 0.1742/0.1668/0.1507/0.1504; Recon 0.8816/0.8688/0.8032/0.7952. Predicting the mean gives Recon 0.9887.

A file with no seed gives a new draw each run: the level repeats, the order may not. The seat will run a file once the shape that stopped it has changed.
