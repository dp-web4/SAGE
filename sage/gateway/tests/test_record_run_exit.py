"""A run whose script exited non-zero reaches the reflect turn as FAILED, not "ok".

Fixture: cbp-being beat heartbeat-704ff2b9e4d5 (2026-11-05). test_chat_handler.py ran three times,
exit 1, ModuleNotFoundError; the record said "-> ok: {...", the error name cut by the cap, and
reflect told the seat "Done ... confirmed the rename worked".
"""


class I:
    def __init__(self, effector, args): self.effector, self.args = effector, args


class E:
    def __init__(self, ok, result=None):
        self.ok, self.refused, self.error, self.result, self.pending = ok, False, None, result, False


RUN_FAIL = {"script": "test_chat_handler.py", "files": ["test_chat_handler.py"], "exit": 1, "stdout": "",
            "stderr": "Traceback (most recent call last):\n  File \"/work/test_chat_handler.py\", line 6, "
                      "in <module>\n    import chat_handler\nModuleNotFoundError: No module named 'chat_handler'",
            "note": "Exit 1. stderr holds a Python traceback."}


def test_a_failed_script_is_recorded_as_failed_with_its_last_line():
    from sage.gateway.heartbeat import _record_line
    line = _record_line(I("run", {"path": "scratch/test_chat_handler.py"}), E(True, RUN_FAIL))
    assert "-> ran, and the script FAILED (exit 1): ModuleNotFoundError: No module named 'chat_handler'" in line
    assert "-> ok" not in line


def test_a_clean_run_and_non_run_results_are_unchanged():
    from sage.gateway.heartbeat import _record_line
    ok_run = {**RUN_FAIL, "exit": 0, "stderr": "", "stdout": "3 passed"}
    assert "-> ok: " in _record_line(I("run", {"path": "t.py"}), E(True, ok_run))
    assert _record_line(I("memory_write", {"path": "j.md"}), E(True, "wrote 3 lines")).endswith("-> ok: wrote 3 lines")
    # an exit field that is not an int is not read as a failure
    assert "-> ok" in _record_line(I("run", {"path": "t.py"}), E(True, {"exit": "1"}))
