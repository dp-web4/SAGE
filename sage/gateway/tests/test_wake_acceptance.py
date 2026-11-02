"""Immediate-start evidence after event-driven waking; no live scheduler calls."""
import json
import subprocess

import pytest

from sage.gateway import arousal
from sage.gateway.tests.fake_systemd import FakeSystemd


@pytest.mark.parametrize("outcome,accepted,error", [
    (0, True, None),
    (5, None, "exit 5"),
    (-15, None, "exit -15"),
    (FileNotFoundError("systemctl"), False, "no systemctl"),
    (subprocess.TimeoutExpired("systemctl", 10), None, "TimeoutExpired"),
    (OSError("lost reply"), None, "OSError"),
])
def test_one_immediate_attempt_retains_pending_work(monkeypatch, tmp_path, outcome, accepted, error):
    calls = []

    def scheduler(args, timeout=10):
        calls.append(args)
        if "is-active" in args:
            return subprocess.CompletedProcess(args, 3, "inactive", "")
        assert args == ["systemctl", "--user", "start", "--no-block", arousal.UNIT]
        if isinstance(outcome, Exception):
            raise outcome
        return subprocess.CompletedProcess(args, outcome, "", "" if not outcome else "lost reply")

    monkeypatch.setattr(arousal, "_systemd", scheduler)
    d = json.loads(json.dumps(arousal.respond(tmp_path, "dp_turn", descriptor="new turn")))
    assert d["start_accepted"] is accepted and d["started"] is None
    assert d["wake_evidence_version"] == 2
    assert len(calls) == 2  # read-only activity query and exactly one start attempt
    assert "next" not in d  # a successor would also be a second scheduling attempt
    assert arousal.peek_pending()[0]["descriptor"] == "new turn"
    if error:
        assert error in d["wake_error"] and "awaiting" in d["fallback"]
    else:
        assert "wake_error" not in d and "fallback" not in d
        assert arousal.delivery_text(d).endswith("beat entry unconfirmed")


def test_lost_reply_after_submission_does_not_arm_an_extra_beat(monkeypatch, tmp_path):
    fake = FakeSystemd()

    def scheduler(args, timeout=10):
        result = fake(args, timeout)
        if "start" in args:
            raise subprocess.TimeoutExpired(args, timeout)
        return result

    monkeypatch.setattr(arousal, "_systemd", scheduler)
    d = arousal.respond(tmp_path, "dp_turn", descriptor="new turn")
    assert fake.running and fake.starts == 1  # submitted, but the caller lost its reply
    assert fake.arms == [] and d["start_accepted"] is None
    assert "outcome unknown" in arousal.delivery_text(d)
    assert arousal.claim_pending("fake-beat")[0]["descriptor"] == "new turn"


def test_failed_successor_never_becomes_immediate_start_evidence(monkeypatch, tmp_path):
    fake = FakeSystemd(running=True)

    def scheduler(args, timeout=10):
        if args[0] == "systemd-run":
            raise subprocess.TimeoutExpired(args, timeout)
        return fake(args, timeout)

    monkeypatch.setattr(arousal, "_systemd", scheduler)
    d = arousal.respond(tmp_path, "dp_turn", descriptor="mid-beat turn")
    assert d["queued"] is True and d["next"]["armed"] is False
    assert "start_accepted" not in d and "started" not in d
    assert arousal.delivery_text(d) == "recorded; awaiting the next beat"
    assert arousal.peek_pending()[0]["descriptor"] == "mid-beat turn"
