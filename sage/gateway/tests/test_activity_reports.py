"""The beat tells the daemon what the being is doing, and a daemon that is down costs it nothing
(SAGE #291).

dp, 2026-09-30: "only actual state should be shown, and it should reflect what the being is
doing. the state display is an indicator not a control."

Every test here reports to a FAKE daemon on an ephemeral port or to a closed one. conftest
turns reporting off for the whole suite; these tests turn it back on per test.
"""
import ast
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from sage.gateway import activity
from sage.gateway import heartbeat as hb


class _FakeDaemon:
    def __init__(self):
        self.reports = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("content-length", 0))
                outer.reports.append((self.path, json.loads(self.rfile.read(n))))
                body = b'{"applied": true}'
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}/activity"
        self.t = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.t.start()

    def states(self):
        return [(b["state"], b["source"]) for _, b in self.reports]

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def daemon(monkeypatch):
    d = _FakeDaemon()
    monkeypatch.setenv("SAGE_ACTIVITY_REPORT", "1")
    monkeypatch.setattr(activity, "ACTIVITY_URL", d.url)
    monkeypatch.setattr(activity, "_reported_active", False)
    yield d
    d.close()


def _closed_port_url():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}/activity"


def test_the_suite_never_reports_to_the_live_daemon(monkeypatch):
    """conftest's isolation holds: with it in force, a report makes no request at all."""
    monkeypatch.setattr(activity, "ACTIVITY_URL", "http://127.0.0.1:9/should-never-be-called")
    t = time.monotonic()
    assert activity.report("wake", "heartbeat:start") is False
    assert time.monotonic() - t < 0.05, "disabled means no connection attempt, not a fast failure"


def test_a_report_carries_state_source_beat_and_its_bound(daemon):
    assert activity.report("wake", "heartbeat:explore", beat_id="heartbeat-abc", ttl_secs=1590)
    path, body = daemon.reports[0]
    assert path == "/activity"
    assert body == {"state": "wake", "source": "heartbeat:explore", "beat_id": "heartbeat-abc",
                    "ttl_secs": 1590}


def test_the_beat_bound_is_the_units_timeout_plus_the_stop_window():
    src = (Path(__file__).resolve().parent.parent / "systemd" / "sage-heartbeat.service.example").read_text()
    assert "TimeoutStartSec=1500" in src, "the cited bound moved; BEAT_TTL_S must follow it"
    assert activity.BEAT_TTL_S == 1500 + 90


def test_the_consolidation_unit_reports_dream_then_rest_and_cannot_fail_the_job():
    src = (Path(__file__).resolve().parent.parent / "systemd" / "sage-consolidation.service.example").read_text()
    assert "ExecStartPre=-/usr/bin/python3 -m sage.gateway.activity dream consolidation --ttl 690" in src
    assert "ExecStopPost=-/usr/bin/python3 -m sage.gateway.activity rest consolidation" in src
    assert "TimeoutStartSec=600" in src, "--ttl 690 is this plus 90"


def test_an_unknown_state_is_refused_locally_without_raising(daemon):
    assert activity.report("focus", "x") is False
    assert daemon.reports == []


def test_a_dead_daemon_neither_fails_nor_slows_a_report(monkeypatch, capsys):
    monkeypatch.setenv("SAGE_ACTIVITY_REPORT", "1")
    t = time.monotonic()
    assert activity.report("wake", "heartbeat:start", url=_closed_port_url()) is False
    assert time.monotonic() - t < 1.0
    assert "not delivered" in capsys.readouterr().err, "and it says so, once, on stderr"


def test_a_daemon_that_never_answers_costs_at_most_the_timeout(monkeypatch):
    monkeypatch.setenv("SAGE_ACTIVITY_REPORT", "1")
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)   # accepts the connection into the backlog and never answers
    try:
        t = time.monotonic()
        ok = activity.report("wake", "heartbeat:start",
                             url=f"http://127.0.0.1:{s.getsockname()[1]}/activity")
        took = time.monotonic() - t
    finally:
        s.close()
    assert ok is False
    assert took < activity.REPORT_TIMEOUT_S + 0.75, took


def test_rest_is_owed_only_after_something_else_was_reported(daemon):
    assert activity.end("heartbeat:end") is False
    assert daemon.reports == [], "a beat that never began must not overwrite another reporter's state"
    activity.report("wake", "heartbeat:start")
    assert activity.end("heartbeat:end") is True
    assert daemon.states() == [("wake", "heartbeat:start"), ("rest", "heartbeat:end")]
    assert activity.end("heartbeat:end") is False, "owed once"


def test_the_cli_always_exits_zero(monkeypatch):
    monkeypatch.setenv("SAGE_ACTIVITY_REPORT", "1")
    monkeypatch.setattr(activity, "ACTIVITY_URL", _closed_port_url())
    assert activity.main(["dream", "consolidation", "--ttl", "690"]) == 0
    assert activity.main(["not-a-state", "x"]) == 0


# --- the beat's sequence -------------------------------------------------------------------

def _fake_beat(phases, raise_at=None):
    """Stands in for heartbeat.main: reports the phases it passes through, as main does."""
    def main(argv=None):
        hb._BEAT_ID["id"] = "heartbeat-test"
        for state, phase in phases:
            if phase == raise_at:
                raise RuntimeError("the beat crashed")
            hb._phase(state, phase, "heartbeat-test")
        return 0
    return main


BEAT = [("wake", "start"), ("wake", "explore"), ("wake", "posture"), ("wake", "account"),
        ("wrap-up", "reflect"), ("wrap-up", "answer")]


def test_a_beat_reports_wake_then_wrap_up_then_rest(daemon, monkeypatch):
    monkeypatch.setattr(hb, "main", _fake_beat(BEAT))
    assert hb.run([]) == 0
    assert daemon.states() == [("wake", "heartbeat:start"), ("wake", "heartbeat:explore"),
                               ("wake", "heartbeat:posture"), ("wake", "heartbeat:account"),
                               ("wrap-up", "heartbeat:reflect"), ("wrap-up", "heartbeat:answer"),
                               ("rest", "heartbeat:end")]
    assert all(b.get("beat_id") == "heartbeat-test" for _, b in daemon.reports)
    assert all(b.get("ttl_secs") == activity.BEAT_TTL_S for _, b in daemon.reports[:-1])


def test_a_beat_that_crashes_still_reports_rest(daemon, monkeypatch):
    monkeypatch.setattr(hb, "main", _fake_beat(BEAT, raise_at="reflect"))
    with pytest.raises(RuntimeError):
        hb.run([])
    assert daemon.states()[-1] == ("rest", "heartbeat:end")


def test_a_dead_daemon_does_not_break_or_slow_a_beat(monkeypatch):
    monkeypatch.setenv("SAGE_ACTIVITY_REPORT", "1")
    monkeypatch.setattr(activity, "ACTIVITY_URL", _closed_port_url())
    monkeypatch.setattr(activity, "_reported_active", False)
    monkeypatch.setattr(hb, "main", _fake_beat(BEAT))
    t = time.monotonic()
    assert hb.run([]) == 0, "the beat's own result, untouched"
    assert time.monotonic() - t < 2.0


def test_the_real_beat_reports_each_phase_before_it_runs():
    """Structural, because the real beat needs a model: in heartbeat.main, each phase's report
    comes before that phase's model call, wake/start comes before the body block reads
    /status, and the unit's entry point is the wrapper that owes the rest."""
    src = (Path(__file__).resolve().parent.parent / "heartbeat.py").read_text()
    tree = ast.parse(src)
    main = [n for n in tree.body if getattr(n, "name", "") == "main"][0]
    reports = []
    for c in ast.walk(main):
        if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_phase":
            reports.append((c.lineno, c.args[0].value, c.args[1].value))
    reports.sort()
    assert [(s, p) for _, s, p in reports] == BEAT, reports

    line = {p: n for n, _, p in reports}
    turns = sorted(c.lineno for c in ast.walk(main) if isinstance(c, ast.Call)
                   and getattr(c.func, "id", "") == "run_ollama_tool_turn")
    account = min(c.lineno for c in ast.walk(main) if isinstance(c, ast.Call)
                  and getattr(c.func, "attr", "") == "get_chat_response")
    assert line["explore"] < turns[0] and line["posture"] < turns[1]
    assert line["account"] < account < line["reflect"] < turns[2]
    assert line["answer"] < turns[-1]
    body_reads = [c.lineno for c in ast.walk(main) if isinstance(c, ast.Call)
                  and getattr(c.func, "attr", "") == "reading"]
    assert body_reads and line["start"] < min(body_reads), \
        "the being must not read 'rest' in its own beat's body block"
    assert 'sys.exit(run())' in src, "the unit's `python -m` entry runs the wrapper that owes rest"
