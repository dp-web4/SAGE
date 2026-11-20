"""An edit miss and a fresh create both name a same-name file one directory away.

Measured 2026-11-16 06:23Z on cbp-being: memory_edit on the bare name of
scratch/xor_not_linearly_separable.py said only "does not exist ... memory_write creates a
file"; the being then memory_wrote the bare name, the receipt said "created ...", and every
later act in the beat worked on the new top-level copy while the scratch/ file (the one an
importing script reads) stayed as it was.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict  # noqa: E402
from sage.gateway.reference_f1a import ReferenceF1aDispatcher  # noqa: E402

_ALLOW = GatewayVerdict("allow")


def _home():
    root = tempfile.mkdtemp(prefix="edit-same-name-")
    os.makedirs(os.path.join(root, "scratch"))
    with open(os.path.join(root, "scratch", "xor.py"), "w") as f:
        f.write("a = 1\nb = 2\nc = 3\n")
    return root, ReferenceF1aDispatcher(memory_root=root)


def test_edit_miss_names_the_scratch_file_and_does_not_route_to_write():
    root, d = _home()
    r = d(BeingIntent("memory_edit", {"path": "xor.py", "start_line": 1, "end_line": 1,
                                      "new": ""}), _ALLOW)
    assert not r.ok and "does not exist" in r.error, r.error
    assert "'scratch/xor.py'" in r.error and 'path "scratch/xor.py"' in r.error, r.error
    assert "memory_write creates a file" not in r.error, r.error
    # the suggested call works
    r = d(BeingIntent("memory_edit", {"path": "scratch/xor.py", "start_line": 1, "end_line": 1,
                                      "new": ""}), _ALLOW)
    assert r.ok, r.error
    assert open(os.path.join(root, "scratch", "xor.py")).read() == "b = 2\nc = 3\n"


def test_true_absence_keeps_the_old_text():
    _, d = _home()
    r = d(BeingIntent("memory_edit", {"path": "nope.py", "old": "a", "new": "b"}), _ALLOW)
    assert not r.ok and "memory_write creates a file" in r.error, r.error
    assert "DOES exist" not in r.error, r.error


def test_create_receipt_says_the_same_name_file_was_not_changed():
    root, d = _home()
    r = d(BeingIntent("memory_write", {"path": "xor.py", "content": "print(1)\n"}), _ALLOW)
    assert r.ok and r.result.startswith("created xor.py"), r.result
    assert "'scratch/xor.py'" in r.result and "NOT changed" in r.result, r.result
    assert open(os.path.join(root, "scratch", "xor.py")).read() == "a = 1\nb = 2\nc = 3\n"


def test_create_with_no_namesake_is_unchanged():
    _, d = _home()
    r = d(BeingIntent("memory_write", {"path": "scratch/fresh.py", "content": "x = 1\n"}),
          _ALLOW)
    assert r.ok and "NOT changed" not in r.result, r.result


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
