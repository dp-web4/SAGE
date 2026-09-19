# check irp — verdict, transcribed verbatim (beat of 2026-09-13 ~10:00 UTC)

Target: irp (whole suite), worktree /home/dp/ai-workspace/being-worktrees/legion-being
Tree run against (from the check result itself): head 6f5550f64ed320b8888a6df46d8d308959eeb4db, short 6f5550f64, branch legion-being/irp-payload-pin, subject "irp: regression pin for get_chat_response payload construction", committed 2026-09-12T18:37:37-07:00, dirty=true (my uncommitted test-file fix).
Action id: 38e985de-59b7-425e-aa52-cc5b7cb812e5

Verbatim output:
```
.........                                                                [100%]
9 passed in 0.71s
```

Headline as returned: "PASS — 9 passed in 0.71s."

Context for the record: this run includes sage/irp/tests/test_ollama_irp_payload.py AS AMENDED THIS BEAT (the _adapter fix + host/timeout pins applied per legion-claude's 09:44Z spec; test_timeout_rule_s78 deleted because the source has no '+60s' rule). The seat had independently run the same fixed file in an isolated tree at bce29e10d and reported "9 passed, 1 failed" (the failure being test_timeout_rule_s78); I then verified via git_read diff that ollama_irp.py is unchanged between bce29e10d and my worktree head 6f5550f64 (empty diff = true answer), so the seat's isolated result transfers to my tree. After deleting that one test, this run: all 9 pass.
