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

# NOR THE MACHINE'S REAL HESTIA DAEMON (McNugget, 2026-09-28). A test that builds a real
# BeingGateClient and calls gate() loads hestia's single-gate and mechanism, which discover the
# daemon at $HESTIA_ENDPOINT, then $HESTIA_HOME/endpoint -- the LIVE one on a seat. Connecting
# there mints the test's plugin id as a MEMBER of the seat's real society: dp found `test-being`
# in McNugget's registry among 12 phantoms, put there by gateway test runs. Port 9 (discard)
# refuses connections, so the gate sees an unreachable daemon and fails closed -- which is what
# every such test already asserts or tolerates. setdefault, so a deliberate integration run can
# still point at a daemon it means to.
os.environ.setdefault("HESTIA_ENDPOINT", "http://127.0.0.1:9/mcp")
