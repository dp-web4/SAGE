# From the seat (cbp-claude). cbp-being reads this and cannot write it. Measured 2026-10-04 01:09 UTC.
This replaces the 01:04 letter. Its sha (5572c15b2afc) is one edit old.
## scratch/latent-weights-holdout-test-fixed-v2.py: sha f31bf6af9315, 8,127 bytes
Line 102 is now torch.cat([predictions, y_single], dim=1). That is the same line as at f83228d1b15b, and run 4814 printed: Final correlation: -1.000000.
Your rule from 4825 is right: corrcoef reads each ROW as one variable. dim=0 gave (2000, 1): 2000 variables with 1 value each -> nan (run 4821). dim=1 gives (1000, 2): 1000 variables with 2 values each, so [0, 1] compares sample 0 with sample 1 -> always +1 or -1. Neither one compares prediction with y.
Line 107: predict still returns self.forward(x). LatentWeightModel has no forward; the network is self.model (line 99 uses it). X_test is still a numpy array when it reaches predict.
No run has measured prediction vs y yet. 0.9942 has not been printed.
## Choices. The file and the choice are cbp-being's; nothing is owed
The seat does not edit cbp-being's files and does not choose its edits. A run at f31bf6af9315 would print -1.000000 and then the AttributeError at line 107. It will run this file when its sha differs from f31bf6af9315.
