"""Gateway tests never touch the machine's real conversation state (~/.sage).

The witness dir was isolated here from the start; the wake ledger was not. Measured 2026-09-21
on CBP: 381 directories in the real ~/.sage/conversation-notify, all but one of them `hd-*`
instances left by test runs over two days, beside the being's real ledger. A test that can
write the ledger a live being's wakes are keyed on is a test that can suppress a real wake.
"""
import os
import tempfile

os.environ.setdefault("SAGE_CONV_WITNESS_DIR", tempfile.mkdtemp(prefix="conv-witness-test-"))
os.environ.setdefault("SAGE_CONV_NOTIFY_DIR", tempfile.mkdtemp(prefix="conv-notify-test-"))
