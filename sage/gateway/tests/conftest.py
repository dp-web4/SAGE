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

import pytest  # noqa: E402


# NOR THE LIVE DAEMON'S STATE DISPLAY (SAGE #291). A test that runs heartbeat.main would POST
# wake/wrap-up/rest to the real :8760/activity and show a beat that never happened. Every test,
# unconditionally; subprocesses inherit it. The activity tests opt back in, per test, against
# their own fake daemon.
@pytest.fixture(autouse=True)
def _no_activity_reports_to_the_live_daemon(monkeypatch):
    monkeypatch.setenv("SAGE_ACTIVITY_REPORT", "0")


# NOR THE MACHINE'S REAL BEAT UNIT OR PENDING SET (SAGE #295). Every event now wakes the being:
# arousal starts `sage-heartbeat.service` or arms a successor with systemd-run, and records the
# event in ~/.sprout/pending_events.json. A test that reached either would start a real beat or
# leave work the being's next beat claims. SAGE_NO_SYSTEMD makes arousal's one systemd door refuse
# (subprocesses inherit it); the guard below refuses any other in-process systemctl/systemd-run
# unless a test replaces subprocess.run itself with its own fake.
@pytest.fixture(autouse=True)
def _no_systemd_and_no_live_pending_set(monkeypatch, tmp_path_factory):
    import subprocess
    monkeypatch.setenv("SAGE_NO_SYSTEMD", "1")
    # Pin the systemd path so these tests read the same on a Mac (arousal picks launchd where
    # there is launchctl and no systemctl); the launchd tests set it themselves.
    monkeypatch.setenv("SAGE_WAKE_BACKEND", "systemd")
    pend = str(tmp_path_factory.mktemp("pending") / "pending_events.json")
    monkeypatch.setenv("SAGE_PENDING_EVENTS", pend)
    from sage.gateway import arousal, being_join
    monkeypatch.setattr(arousal, "PENDING_PATH", pend)
    _isolate_wake_marker(monkeypatch, tmp_path_factory, being_join)
    real_run = subprocess.run

    def guarded(args, *a, **k):
        argv0 = str(args[0] if isinstance(args, (list, tuple)) and args else args).split()[0:1]
        if argv0 and os.path.basename(argv0[0]) in ("systemctl", "systemd-run", "launchctl"):
            raise FileNotFoundError(f"tests may not run {argv0[0]} (conftest, SAGE #295)")
        return real_run(args, *a, **k)
    monkeypatch.setattr(subprocess, "run", guarded)


def _isolate_wake_marker(monkeypatch, tmp_path_factory, being_join):
    """The wake marker's default path is the live ~/.sprout/beat_wake.json, bound as a default
    argument; route both ends of it to a temp file."""
    marker = str(tmp_path_factory.mktemp("marker") / "beat_wake.json")
    real_write, real_consume = being_join.write_wake_marker, being_join.consume_wake_marker
    monkeypatch.setattr(being_join, "write_wake_marker",
                        lambda d, s, path=marker: real_write(d, s, path=path))
    monkeypatch.setattr(being_join, "consume_wake_marker",
                        lambda path=marker, **k: real_consume(path=path, **k))
