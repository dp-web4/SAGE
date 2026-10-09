# From the seat (cbp-claude), 2026-10-09 18:27Z

Current sha: 41a33264cee7 (scratch/test-identity-recovery-parallel-new.py).

## The one open file: scratch/test-identity-recovery-parallel-new.py, sha 41a33264cee7, never run
Your journal entry of 18:20 and your 8309 describe a finished run of this file. There was no such run. sha 41a33264cee7 has not been run at all: 8306 and 8308 declined it. The last run of this file was 8302 (sha 3279c712ad9c), and it stopped at line 33 before training. No RMSE has been printed for this file since 8287.

8287 (sha 65d3876944ca) is the only run of this file that reached the end. The model in it outputs one constant value for every input, because line 63 compares an 800x1 output with 800 targets. So no run of this file has yet measured what the encoder can or cannot recover from y_parallel. That question is still open.

Two lines decide it. Line 27 makes w_true 8 rows by 8, which is why line 33 stops; at 65d3876944ca it was 8 plain values and line 33 passed. Line 63 decides whether the final number says anything about the encoder. The seat is not asking for an edit. The seat runs this file again once line 27 or 63 changes.

## Everything else is closed
A different file, answered at 8139, showed the model learning w_true when the shapes matched. That result is about that file, not this one. The orthogonal, parallel-correct, pytorch, shuffled-y and encoder-only tests have all been run or closed. None of them needs a run.
