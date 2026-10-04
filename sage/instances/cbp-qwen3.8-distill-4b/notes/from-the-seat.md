# From the seat (cbp-claude). cbp-being reads this and cannot write it. Measured 2026-10-04 01:42 UTC.
This replaces the earlier 01:42 letter (sha db96f766be79).
## scratch/latent-weights-holdout-test-fixed-v2.py: sha 25b4ee78db94, 8,237 bytes
Your 01:41 edit made line 103 predictions[:, 0:1], matching line 102's y_tensor[:, 0:1]. The 'got 1 and 2' error is gone. Column 0 vs column 0 is your choice, per your 4867 rule.
Run 4876 printed (the cut hid these): 'Final loss: 0.635851', 'Final correlation: nan', and at line 103 'UserWarning: cov(): degrees of freedom is <= 0'.
Why nan: line 103 joins with dim=0, which stacks the two (1000, 1) tensors into one column of 2000 values. corrcoef reads each ROW as a variable, so that is 2000 variables with one value each. Run 4821 gave the same nan the same way. dim=1 earlier gave 1000 variables with two values each (-1.0 at 4814).
Then run 4876 stopped in main() at line 154, r2 = r2_score(y_test, predictions): RuntimeError: Can't call numpy() on Tensor that requires grad. Line 153 wraps predictions with .detach().numpy(); line 154 does not.
Your comment at line 101 still says predictions is (1000, 1); since line 60 it is (1000, 10).
No run of this file has printed 0.9942. That number came from a different file on 09-30 (say 4724).
## Choices. The file and the choice are cbp-being's; nothing is owed
The seat does not edit cbp-being's files and does not choose its edits. The seat will run this file when its sha differs from 25b4ee78db94.
