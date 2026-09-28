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

# NOR THE MACHINE'S REAL HESTIA DAEMON: connecting there mints the test's id as a member of the
# seat's real society (McNugget, 2026-09-28: `test-being` among 12 phantoms). Unconditional -- an
# inherited HESTIA_ENDPOINT is not consent -- with SAGE_TEST_LIVE_HESTIA=1 as the only opt-in.
# See _isolate_hestia.py for both layers.
import sys  # noqa: E402
sys.path.insert(0, os.path.dirname(__file__))
import _isolate_hestia  # noqa: E402,F401  -- isolates on import
