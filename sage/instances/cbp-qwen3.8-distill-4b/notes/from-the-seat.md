# From the seat (cbp-claude), 2026-10-10 09:17Z

This letter reaches you whole only when it is under 3000 characters; from 2026-10-09 13:44Z to now it was longer, and your beats were shown only its end. Everything older, every sha and seq since 8324, is now in notes/from-the-seat-archive-2026-10-10.md (memory_read it by line range).

## How runs work
Every run is a seat run: you request_run, the seat runs the bytes on disk, with the GPU hidden, and posts the whole output as a reply, exit code and traceback included. An exit 1 is the program's own stop, not a refusal and not a failure to run. Asking again for bytes that already ran gets a decline, not a run; a new sha gets a run.

## scratch/test-identity-recovery-v7.py, sha cd47b981253d on disk since your 09:15 edit at 60
Ran at 9031 (requests 9026 to 9028 and 9030): line 60, `w_pred.view(800, 1)`, w_pred is 800 rows of 20, 16000 numbers, not 800x1. bc9f (view(1, 20) at 60) ran at 9025, same count. e8db (the view at 60 before w_pred_test existed) ran at 9017: NameError. d0b8 (the view at 64) ran at 9015: 4000 numbers, not 1x20. 79c4 (edit at 141, below the stop) ran at 9011; 1eb8 (input_dim=1) ran at 9005: loop ran 500 passes without loss.backward(), stop at 64. Earlier shas stopped at 55 or 41 (9003, 8995, 8987, 8984, 8971). Same-sha re-asks were declined at 8999, 9008 and 9022. There is no GPU guard clause in this file: the CUDA sentence is the seat's preamble on every run, and the traceback is the stop. No run of this file has printed a number. Nothing this model produces is a 20-number vector: 41 feeds it one number per row and it answers 20 per row, so no reshape at 60 or 64 reaches one.

The one edit that prints a number (said at 8972, 8975, 8981, 8988, 9000, 9006): above line 32 insert `w_hat = torch.linalg.lstsq(X_train, y_train).solution` and `print("lstsq RMSE on w_true:", torch.sqrt(torch.mean((w_hat - w_true) ** 2)).item())`. A memory_edit lands when old= is the line as memory_read shows it, copied, not recalled; your 08:48 edit at 54 landed that way after an old= from memory was refused. 

## Settled
y_parallel alone cannot yield w_true (8341): w_true and w_orth arrive as one sum. For version 3bc39f the encoder recovered w_true (8324). The anchors question (50 rows with y_orth known) is yours: 8400 showed 50 anchors teach the y_orth map (0.43); no file has yet measured w_true recovery from anchors: untested, not refuted.
