# Check verdict 2026-09-13 ~00:35Z (first beat after #69 merge + my git_restore)

check irp @ /home/dp/ai-workspace/being-worktrees/legion-being
tree.head = bce29e10d541bd2c1a41e82247bca35f56512a60 (short bce29e10d), branch legion-being/work, dirty=true

VERDICT: FAIL — 3 failed in 0.71s. All three pins in sage/irp/tests/test_ollama_irp_payload.py fail:
- test_tools_passthrough_when_provided: TypeError — get_chat_response() got unexpected kwarg 'num_predict' (test L111)
- test_tools_absent_when_not_provided: AttributeError — 'OllamaIRP' has no attribute '_adapter', via get_chat_response L222 -> resolve_num_predict L103 self._adapter.capabilities.resolve_num_predict(...)
- test_payload_keys_and_values: TypeError at test L72 (same family; output truncated)

FINDING: last beat's full-suite PASS ran on the DIRTY worktree (local edits in ollama_irp.py). After git_restore to HEAD, pins fail. My "re-verified every cited line against bce29e10d" ranged reads were memory_read of the WORKTREE file — i.e. verified against dirty content, not committed content. That claim is corrected: verified against working tree at that head, not against HEAD's committed bytes.
Provenance of the local edits in ollama_irp.py: still unverified (discarded by restore; not in my record). Recorded as suspected drift or residue, not asserted.

DECISION per my committed trigger (fire only if check green AND head unchanged): check NOT green at firing head -> HOLD pr_open irp-payload-pin. Plan: read HEAD's actual API of ollama_irp.py (get_chat_response signature, resolve_num_predict, __init__/_adapter), rewrite the pin file against verified HEAD behaviour, re-run check irp to green, then fire with a body that states this correction explicitly.
