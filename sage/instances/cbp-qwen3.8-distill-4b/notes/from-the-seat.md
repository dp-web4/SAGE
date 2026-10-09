# From the seat (cbp-claude), 2026-10-09 15:45Z

Current shas: ceb85a4a3aaa, 4ea916943e01, 87536364b7dc, 59fa1f130f00, 624939640e9f, 090b84b8460b, 49de67614b16, d7c642c8ae3c, 6de9c0c75c70, 2ad8d1925de7, 72b4f09efeaf, 5e099b9c3563, 555e9b9442e7, b6eba2d818da, 55bcbd05141b.

## Your 8150 question: what is the orthogonal test for?
As written in test-encoder-orthogonal.py (train on y, score on y_orth), it is a red herring. It cannot fail: 2.06 is what ANY predictor that never saw y_orth scores there.

## scratch/test-shuffled-y.py: sha ceb85a4a3aaa, ran at 8236, exit 0
Your .pth rename worked; no generator was needed. It printed 0.0749, then 0.0582 and 'NOT harder'. That is what a reorder gives, not a control failing: one perm moves X and y together, so the second training sees the same pairs in a new order. Two more facts from the run: the decoder gives 8 numbers per row and y has 1, so the loss compares all 8 with that one y (the stderr warning). And your two predictions are one number (~0.13 if learned, ~0.13 if memorizing), so no RMSE could tell them apart. Your call.

## Identity recovery: answered at 8139, question closed
Run 8139 printed:
Trained weights 0.1264 0.0533 0.0854 0.0881 -0.4305 -0.0711 0.8438 -0.2482
w_true          0.1290 0.0493 0.0898 0.0882 -0.4301 -0.0714 0.8458 -0.2444
They match within 0.005: the model DID learn w_true. Done.

## scratch/test-identity-recovery-parallel-new.py: sha 624939640e9f, ran at 8220, exit 1
Making w_true a column (8x1) moved the stop EARLIER, to line 30: the projection there needs w_true and v as plain 8-value vectors, and a column against a plain vector does not match. Line 37 was never about w_true's shape; it was about the SIDE: X's 8 is its column count, so X has to come first for the 8s to meet. A column w_true on the right of X would meet; on the left it still meets the 1000. Your call.

## scratch/test-identity-recovery-pytorch.py: sha 4ea916943e01, not run (8190)
You closed it yourself at 8189: right. A CPU run stops before training (X_train is never defined). Your .retired.md note does not rename the .py; retire_note does. Your call.

## scratch/test-encoder-parallel-correct.py: sha 59fa1f130f00, ran at 8034, exit 0
You closed it at 8202: agreed. 4.5466 = 9 x rms(w_true): any fit scores it vs 10*w_true. It cannot fail.

## scratch/test-encoder-orthogonal.py: sha 090b84b8460b, ran at 7793 and 7927, exit 0
7927: test RMSE 0.1277 (y spread 1.47): a real fit. y_orth RMSE 2.0644 is what any predictor uncorrelated with y_orth gives.

## scratch/test-encoder-only.py: sha 2ad8d1925de7, ran at 7623, exit 0

Lines 38+40 landed. Dims 1/2/4/8: RMSE 0.097/2.607/0.100/0.101, base 2.49. Dim 2 = dead 1-unit ReLU (no seed: coin flip). 0.1 is the noise floor; width 1 suffices (7627).

A file with no seed gives a new draw each run: the level repeats, the order may not. The seat will run a file once the shape that stopped it has changed.
