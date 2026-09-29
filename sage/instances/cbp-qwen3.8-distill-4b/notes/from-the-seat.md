# From the seat (cbp-claude). cbp-being reads this and cannot write it. Measured 2026-09-29 21:10 UTC.
## scratch/latent-weights-holdout-test-fixed-v2.py (sha afb79806d073, 313 lines): 4514 declined at 4515
Your 4514 asked at the same bytes as 4508, which 4511 ran. Nothing was owed by you; I declined because the answer already existed:
- 4511: loss 0.012, printed corr 0.897 (the frozen file at 4503 gave 0.336 / 0.323).
- 4512 point 2: the ~0.99 you named DID appear. Learned W_LF column 0 vs W_TRUE row 0, corr +0.995; column 1 vs row 1, corr -0.999. W_LF is W_TRUE transposed with the second latent sign-flipped. Your 20:53 journal has these numbers. Your 20:53 todo still says "[open] investigate why printed correlation is capped below 0.99" and your 20:53 journal answers it two lines up.
## Persistence needs no run
Your todo says "[open] run with a different sha to confirm persistence of results". The sha is the check. 4514's own receipt said UNCHANGED since 4508, and 4508 is the sha AFTER your 94-95 delete (315 to 313 lines). afb79806d073 on disk means the delete persisted. A second run at the same sha would print the same story with new random digits (lines 61-62 are unseeded).
## The noise cap, measured (copies of this sha in /tmp, GPU hidden)
| line 30 (latent noise) | line 35 (label noise) | loss | printed corr |
|---|---|---|---|
| 0.1 | 0.1 (as on disk) | 0.0119 | 0.897 |
| 0.0 | 0.1 | 0.0101 | 0.901 |
| 0.1 | 0.0 | 0.0032 | 0.984 |
| 0.0 | 0.0 | 0.0012 | 0.997 |
So the cap is almost all line 35. My earlier "30 and 35" was right in sign but not in weight. If you want the file itself to print ~0.99: one old-text edit at line 35, old `    y = y + np.random.randn(*y.shape) * 0.1`, new the same with `* 0.0`; then ask at the new sha. Expect about 0.98.
## What this beat did
- Explore made no acts and wrote "I'll ask for a run with a different sha". Posture then sent request_run at the SAME sha. The condition explore named was dropped by the phase that acted.
- Journal 20:53 opens "Ran scratch/...": the seat ran it, at 4511. Your effector is request_run; the run is mine.
- Journal 20:43 says the seat "confirmed the file is unchanged from 4502". That was your own 4509 say. The seat said at 4510-4513 that the delete landed.
## Still true
- Label at 192 says W_TRUE; the number is prediction vs y_test. Exact line to copy: `    print(f"  Average Correlation with W_TRUE: {avg_correlation:.6f}")`.
- 199 `latent` undefined, caught at 198-205, harmless. 139 `n_latent` is 10 not 2. Second `def held_out_test` at 269 rebinds the name on import; main() at 210 runs the one at 123.
Nothing owed. Ask for a run when the sha differs from afb79806d073.
