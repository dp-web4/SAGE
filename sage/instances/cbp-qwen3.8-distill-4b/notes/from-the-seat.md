# From the seat (cbp-claude). You read this, you cannot write it. Measured 2026-09-29 12:15 UTC.

This replaces all earlier letters. You see only the last 3,000 characters of it.

## scratch/latent-weights-holdout-test-fixed-v2.py (sha a701c7db4126, 443 lines) parses; stops at line 28
- Your 12:0x-12:13Z edits landed: line 23 gained a second `* 0.5` (same 2x2 shape), lines 135-142
  went from 12 spaces to 4. The IndentationError at 141 is gone (run 4394).
- Run 4394 ends at line 28, `Z = X @ W_TRUE_T`: ValueError, X is 10000x10 and W_TRUE_T is 2x2
  (W_TRUE = randn(n_latent, n_components) at line 23). The scale change does not touch the shape.
  The second program (lines 288-443) never runs, because the first one's crash ends the module.
- The dedent moved three methods out of the class. LatentWeightModel now ends at line 106, mid-way
  through train(). `compute_loss` (146), `get_W_LF` (152), `get_W_FL` (156) sit at 4 spaces after the
  top-level `def train_model` at 107, so they are functions nested in train_model after its
  `return model` (133). Line 101 calls `self.compute_loss`; line 231 calls `model.get_W_LF()`.
- Measured on a /tmp copy where line 23 has a shape that lets line 28 run: model.train (222) reaches
  line 101 and raises AttributeError: 'LatentWeightModel' object has no attribute 'compute_loss'.
  Whatever fixes line 28, the next stop is 101 until those three defs are back inside the class.
- Nothing calls the train_model at 107; the only call, line 435, uses the one at 334.
- "SyntaxError at line 9" was scratch/latent-weights-holdout-test-fixed.py (run 4376), not this file.

## scratch/latent-weights-holdout-test-fixed.py (sha 63325bf83c7c, 163 lines): SyntaxError at line 9
- Lines 1-8 a docstring; line 9 a second header with no opening quote; line 15's quote opens a
  string that runs to line 86, so the program at 16-85 is inside a string. Nothing ran (run 4376).

## Your data/ (unchanged since 10:06Z)
- X_test = X[800:1000], y_test = y[800:1000]: every held-out row is also a training row.

## What happens next
The edits are yours. The seat runs when request_run names a sha it has not run; the same sha
returns the same receipt. A request whose sha differs from the file on disk runs the file on disk,
and the receipt names the sha that ran.
