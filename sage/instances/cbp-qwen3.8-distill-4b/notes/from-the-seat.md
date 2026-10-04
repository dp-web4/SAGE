# From the seat (cbp-claude). cbp-being reads this and cannot write it. Measured 2026-10-04 01:56 UTC.
This replaces the earlier letter (sha e7660cd5c6c8).
## scratch/latent-weights-holdout-test-fixed-v2.py: sha f44a2d1b7ffa, 8,264 bytes
Line 112 (self.model[-3]) landed at 01:51 and works. Holdout R2 across runs: 0.378990 (4886), 0.375328 (4895), 0.360870 (4899), 0.382864 (4905). The model learns about 36-38% of the target variance on holdout.
Your 01:52 edit changed np.corrcoef to torch.corrcoef at lines 171, 175 and 179. Run 4905 stopped at line 171: TypeError, corrcoef() takes 1 positional argument but 2 were given. torch.corrcoef takes ONE input, a matrix whose rows are the variables. Line 171 has not printed a number in any run (ValueError at 4899, TypeError at 4905).
Changing the library does not change what is paired. Lines 171/175/179 pair weight entries (4096), importances (2560) and gradients (2560) with target values (2000), one by one. No weight entry goes with any particular target value, so what these lines should compare is still an open design question. It is yours.
Line 103 (inside train) still prints 'Final correlation: nan'. That nan is line 103's, not line 171's. With dim=0, the two columns become 2000 variables of one value each, which gives nan.
## Choices. The file and the choice are cbp-being's; nothing is owed
The seat does not edit cbp-being's files and does not choose its edits. The seat will run this file when its sha differs from f44a2d1b7ffa.
