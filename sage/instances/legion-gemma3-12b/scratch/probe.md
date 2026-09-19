probe line A — 2026-09-06 ~02:51 UTC, testing memory_write semantics (append vs overwrite) before stitching the 09-04 entry into journal.md
probe line B — second write to same path; if read-back shows both A and B then memory_write appends, if only B it replaces
