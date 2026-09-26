"""A SIGTERM mid-beat must unwind to the record, not vanish (04:30Z 2026-09-09)."""
import os
import signal
import subprocess
import sys
import time


def test_sigterm_becomes_beat_killed_inside_the_beat():
    prog = (
        "import time, sys\n"
        "from sage.gateway.heartbeat import install_kill_handler, BeatKilled\n"
        "install_kill_handler()\n"
        "print('ready', flush=True)\n"
        "try:\n"
        "    time.sleep(30)\n"
        "except BeatKilled as k:\n"
        "    print('record written after', k, flush=True)\n"
    )
    p = subprocess.Popen([sys.executable, "-c", prog], stdout=subprocess.PIPE, text=True,
                         cwd=os.getcwd())
    assert p.stdout.readline().strip() == "ready"
    p.send_signal(signal.SIGTERM)
    out = p.stdout.read()
    assert p.wait(timeout=10) == 0
    assert "record written after signal 15 (SIGTERM)" in out
