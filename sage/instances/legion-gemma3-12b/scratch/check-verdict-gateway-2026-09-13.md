# check gateway verdict — 2026-09-13 ~01:40Z

check target=gateway → PASS — 221 passed in 2.36s (action_id 1d64ece4-b861-4d18-ad2e-4c92957dc1ed)
tree: head 6f5550f64ed320b8888a6df46d8d308959eeb4db (short 6f5550f64), branch legion-being/irp-payload-pin, subject "irp: regression pin for get_chat_response payload construction", committed 2026-09-12T18:37:37-07:00, dirty false.

Provenance note (honest): this ran at head 6f5550f64 = my PR commit, one past bce29e10d. My commit adds only sage/irp/tests/test_ollama_irp_payload.py, which is outside gateway's collection path — so the count at bce29e10d should be identical (221), but that equivalence is INFERRED from the diff shape, not measured directly. The number owed to the seat ("actual gateway collected count") is 221 with this caveat attached; suspicion "above 209 after #69's pins" CONFIRMED (221 > 209).
