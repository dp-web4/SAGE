# check verdict — irp @ 2026-09-12 ~22:13Z (beat of the FAIL)

check target=irp, worktree /home/dp/ai-workspace/being-worktrees/legion-being
tree: head bce29e10d541bd2c1a41e82247bca35f56512a60 (short bce29e10d), branch legion-being/work, dirty=true
action_id 34ae5723-ccfb-4071-873d-3d5ac9b5ea14

VERDICT: FAIL — "3 failed in 0.71s" (all three tests of my pin file):
FAILED sage/irp/tests/test_ollama_irp_payload.py::test_payload_keys_and_values
FAILED sage/irp/tests/test_ollama_irp_payload.py::test_tools_passthrough_when_provided
FAILED sage/irp/tests/test_ollama_irp_payload.py::test_tools_absent_when_not_provided

Error (identical in all three):
  AttributeError: 'OllamaIRP' object has no attribute 'num_predict_override'
  at sage/irp/plugins/ollama_irp.py:101 in resolve_num_predict,
  called from get_chat_response at ollama_irp.py:222.

Context for the diagnosis (verified facts):
- git_read status @ same beat: head bce29e10d, branch legion-being/work...origin/legion/mission-artifact;
  only dirty entry = untracked `?? sage/irp/tests/`. Plugin file NOT modified in worktree.
- Same target at same head ~21:15Z last beat: PASS, "3 passed".
- Only change since that green check: my two memory_writes to the test file (append-vs-replace not recorded).
- Working hypothesis: an append duplicated a helper (e.g. _make_inst) or chunk; the later definition
  shadows the earlier one and constructs instances without __init__ setting num_predict_override.

Rule in force: trigger NOT met this beat — hold pr_open until check irp is green again at bce29e10d.
