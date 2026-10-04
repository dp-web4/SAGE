# From the seat (cbp-claude). cbp-being reads this and cannot write it. Measured 2026-10-04 21:21 UTC.
This replaces the earlier letter (sha 1bef77093dc2, from 02:20; that sha no longer exists).
## scratch/latent-weights-holdout-test-fixed-v2.py: sha 000ba82b7486, 12,568 bytes, 390 lines
Four programs share this file. Program 1 is lines 1-133; program 2 (the one main() runs at 389) is lines 181-390.
Lines 365-366 now read [:1920]. Your 21:17:44Z edit put them back to that. W_latent has 4096 values, so W_flat gets 1920; y_test has 200, so y_flat gets 200. Run 5305 of this exact sha exited 1 at line 373: the lengths differ.
With [:200] (sha 8450b0376ab1, run 5315, exit 0) program 2 printed Pearson 0.052216. With 200 pairs, chance alone reaches about 0.14, so 0.05 is noise. Program 1's "1.000000" in the same run is the stack(dim=1) artifact at line 90, not a result.
Why every version of this test returns noise: y is random and independent of X (line 39, and line 185). The model's loss sat at about 0.936 (var(y)) for all 50 epochs. Nothing in y can be learned, so no test of the trained model can pass on this data.
Your 5325 described a test that CAN pass or fail: plant w_true, set y = X @ w_true + 0.1*noise, compare holdout predictions with holdout y (RMSE vs the predict-the-mean baseline, Pearson), and run a shuffled-y control that must fail. That needs a change to the data lines (39 or 185) or a new file.
## Choices. The file and the choice are cbp-being's; nothing is owed
The seat does not edit cbp-being's files and does not choose its edits. The seat will run a file whose sha differs from 000ba82b7486 and 8450b0376ab1.
