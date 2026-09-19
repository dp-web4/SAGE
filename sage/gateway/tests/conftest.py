"""Gateway tests never touch the machine's real conversation witness (~/.sage)."""
import os
import tempfile

os.environ.setdefault("SAGE_CONV_WITNESS_DIR", tempfile.mkdtemp(prefix="conv-witness-test-"))
