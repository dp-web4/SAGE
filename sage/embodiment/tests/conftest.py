"""Embodiment tests never reach the machine's real beat unit or pending set (SAGE #295).

Presence now wakes the being on every sense event through sage.gateway.arousal, which starts
`sage-heartbeat.service` or arms a successor with systemd-run, and records the event in
~/.sprout/pending_events.json. A test that reached either would start a real beat on the machine
running it, or leave work the being's next beat would claim.
"""
import os
import subprocess

import pytest


@pytest.fixture(autouse=True)
def _no_systemd_and_no_live_pending_set(monkeypatch, tmp_path_factory):
    monkeypatch.setenv("SAGE_NO_SYSTEMD", "1")
    # Pin the systemd path so these tests read the same on a Mac (arousal picks launchd where
    # there is launchctl and no systemctl); the launchd tests set it themselves.
    monkeypatch.setenv("SAGE_WAKE_BACKEND", "systemd")
    monkeypatch.setenv("SAGE_ACTIVITY_REPORT", "0")
    pend = str(tmp_path_factory.mktemp("pending") / "pending_events.json")
    monkeypatch.setenv("SAGE_PENDING_EVENTS", pend)
    from sage.gateway import arousal, being_join
    monkeypatch.setattr(arousal, "PENDING_PATH", pend)
    _isolate_wake_marker(monkeypatch, tmp_path_factory, being_join)
    _isolate_the_ear(monkeypatch, tmp_path_factory)
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


def _isolate_the_ear(monkeypatch, tmp_path_factory):
    """Every path the ear writes, routed to a temp body dir. Measured on Sprout 2026-10-09: a full-suite run built a real
    audio.Hearing(), whose start-up mark() wrote mode "" into the LIVE ~/.sprout/listen.json, and the cortex (run with
    SAGE_LISTEN=wake) silently stopped listening for its name until the file was put back. speak() marks it too."""
    from sage.embodiment import listening
    body = tmp_path_factory.mktemp("body")
    for attr, name in (("LISTEN_PATH", "listen.json"), ("HEARD_PATH", "heard.jsonl"), ("EAR_LOG", "ear.jsonl"),
                       ("UNHEARD_PATH", "unheard.jsonl"), ("CHIME_PATH", "chime.wav")):
        monkeypatch.setattr(listening, attr, str(body / name))
    monkeypatch.setattr(listening, "BODY_DIR", str(body))
