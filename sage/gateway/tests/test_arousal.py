"""Every event wakes the being (SAGE #295).

dp, 2026-09-30: "events wake the being, and wake state continues for as long as it has something
to do. the rest timer is a watchdog that wakes it if nothing else has. but a message from me, you,
mesh watcher, words detected on audio, motion on video or imu - all should wake it." And: "there
should not be artificial cap on beats".

Until #295 this file pinned the opposite: a GRADED policy (digest 0.1 and unknown kinds 0.2 never
woke the being), REFRACTORY (8 min), a "beat already due" hold-back and an hourly cap. What stays
from it: every decision says why, the daemon's CLI answers in JSON, and `started` is observed,
never assumed (GPT review of SAGE#81).

Every test here runs against a FAKE systemd (`FakeSystemd`): the conftest makes arousal's real
systemd door refuse, and the pending set lives in a temp dir.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sage.gateway import arousal
from sage.gateway.tests.fake_systemd import FakeSystemd


@pytest.fixture
def sysd(monkeypatch):
    f = FakeSystemd()
    monkeypatch.setattr(arousal, "_systemd", f)
    return f


def _pending():
    return {e["key"]: e for e in arousal.peek_pending()}


def test_the_test_suite_cannot_reach_real_systemd():
    """The conftest isolation itself: arousal's one systemd door refuses in every test."""
    with pytest.raises(FileNotFoundError):
        arousal._systemd(["systemctl", "--user", "is-active", arousal.UNIT])
    with pytest.raises(FileNotFoundError):
        subprocess.run(["systemctl", "--user", "start", "--no-block", arousal.UNIT])
    assert "pending" in arousal.PENDING_PATH and ".sprout" not in arousal.PENDING_PATH


def test_every_kind_wakes_the_being_including_those_below_the_old_bar(sysd, tmp_path):
    """digest was 0.1 and an unknown kind 0.2, both below ENGAGE_AT 0.6: they never woke the
    being. Now each starts a beat, and its salience is recorded, not read."""
    for kind in list(arousal.SALIENCE) + ["mesh_notice", "something-new"]:
        sysd.running = False
        d = arousal.respond(tmp_path, kind, descriptor=f"a {kind}")
        assert d["engage"] is True and d["started"] is True, (kind, d)
        assert d["reason"], kind
        assert d["salience"] == arousal.SALIENCE.get(kind, arousal.DEFAULT_SALIENCE)
    assert sysd.starts == len(arousal.SALIENCE) + 2
    assert _pending()["digest:a digest"]["salience"] == 0.1


def test_the_bars_and_caps_are_gone_from_the_code():
    src = Path(arousal.__file__).read_text()
    for name in ("ENGAGE_AT", "REFRACTORY_S", "CONVERSING_REFRACTORY_S", "IMMINENT_S",
                 "MAX_BEATS_PER_HOUR", "beats_last_hour", "refractory_s(", "_arm_deferred_wake",
                 "seconds_to_next_beat"):
        assert name not in src, name


def test_no_refractory_an_event_right_after_a_beat_starts_the_next(sysd, tmp_path):
    (tmp_path / "heartbeats.jsonl").write_text(json.dumps({"t0": 0, "elapsed_s": 1}) + "\n")
    d = arousal.respond(tmp_path, "seat_turn", descriptor="seat wrote 2 s after the beat ended")
    assert d["engage"] is True and d["started"] is True and "refractory" not in json.dumps(d)


def test_an_event_mid_beat_is_queued_not_dropped_and_starts_the_next_beat(sysd, tmp_path):
    sysd.running = True
    d = arousal.respond(tmp_path, "dp_turn", descriptor="dp spoke mid-beat")
    # Legion carrier: a dp turn ALSO reaches the running beat between steps (the interject hook);
    # it is queued as well, so the next beat starts either way.
    assert d["engage"] is False and d["queued"] is True and d["delivered_in_flight"] is True
    assert "starts as soon as" in d["reason"]
    assert d["next"]["armed"] is True
    arm = sysd.arms[0]
    assert "--no-block" in arm and f"After={arousal.UNIT}" in arm and arm[-1] == arousal.UNIT
    assert "dp_turn:dp spoke mid-beat" in _pending()
    sysd.beat_ends()
    assert sysd.starts == 1 and sysd.running, "the next beat started the moment the running one ended"



def test_only_a_conversation_turn_is_delivered_into_a_running_beat(sysd, tmp_path):
    """The interject hook drains conversation turns and nothing else: a sense event or a digest is
    queued for the next beat and must not claim in-flight delivery (GPT review of SAGE#81)."""
    sysd.running = True
    for kind, inflight in (("dp_turn", True), ("seat_turn", True), ("sense", False),
                           ("digest", False), ("peer_turn", False)):
        d = arousal.respond(tmp_path, kind, descriptor=f"{kind} mid-beat")
        assert d["queued"] is True and d["delivered_in_flight"] is inflight, (kind, d)
        assert "starts as soon as" in d["reason"]


def test_no_hourly_cap_n_events_are_n_beats(sysd, tmp_path):
    """Twenty distinct events, each arriving between beats: twenty beats. The old cap was 8/h."""
    for i in range(20):
        arousal.respond(tmp_path, "seat_turn", descriptor=f"turn {i}")
        claimed = arousal.claim_pending(f"beat-{i}")
        assert [e["descriptor"] for e in claimed] == [f"turn {i}"]
        arousal.release_claim(f"beat-{i}")
        sysd.beat_ends()                      # nothing armed: the being rests until the next event
    assert sysd.starts == 20


def test_events_during_one_beat_coalesce_identical_descriptors_and_keep_distinct_ones(sysd, tmp_path):
    sysd.running = True
    for _ in range(50):
        arousal.request_beat("sense", "strong motion to the left", salience=0.3)
    for i in range(3):
        arousal.request_beat("heard", f'heard a voice: "part {i}"')
    p = _pending()
    assert len(p) == 4 and p["sense:strong motion to the left"]["count"] == 50
    assert len(sysd.arms) == 1, "one successor, the rest coalesced into it"
    assert all(c[0] != "systemd-run" or c in sysd.arms for c in sysd.calls)
    sysd.beat_ends()
    assert sysd.starts == 1 and {e["kind"] for e in arousal.claim_pending("b2")} == {"sense", "heard"}


def test_a_second_request_while_a_successor_waits_rides_it(sysd):
    sysd.running = True
    assert arousal.arm_next() == {"armed": True, "by": arousal.NEXT_UNIT}
    d = arousal.arm_next()
    assert d["armed"] is True and d["already_armed"] is True and len(sysd.arms) == 1


def test_a_fired_successor_is_not_mistaken_for_a_waiting_one(sysd, monkeypatch):
    """The name is fixed, so a successor that has fired but is not yet collected collides like a
    waiting one. Only a queued Job is believed; otherwise wait for it to go and arm anew."""
    monkeypatch.setattr(arousal.time, "sleep", lambda s: None)
    sysd.running = True
    sysd.next_loaded_fired = True
    d = arousal.arm_next()
    assert d["armed"] is True and d.get("after_a_fired_successor") is True and "already_armed" not in d
    assert len(sysd.arms) == 1


def test_a_failed_start_keeps_the_event_pending(sysd, tmp_path):
    sysd.start_rc = 5
    d = arousal.respond(tmp_path, "dp_turn", descriptor="dp spoke")
    assert d["engage"] is True and d["started"] is False and "exit 5" in d["wake_error"]
    assert "dp_turn:dp spoke" in _pending(), "a failed start loses nothing"


def test_no_systemctl_at_all_keeps_the_event_pending(tmp_path):
    """The conftest's refusing door stands in for a host with no systemctl (McNugget: launchd)."""
    d = arousal.respond(tmp_path, "dp_turn", descriptor="dp spoke")
    assert d["started"] is False and "no systemctl" in d["wake_error"]
    assert d["next"]["armed"] is False and "dp_turn:dp spoke" in _pending()


def test_a_claim_moves_the_set_and_a_dead_beats_claim_is_absorbed(sysd):
    arousal.add_pending("dp_turn", "one")
    first = arousal.claim_pending("beat-a")
    assert [e["descriptor"] for e in first] == ["one"] and arousal.peek_pending() == []
    arousal.add_pending("seat_turn", "two")          # arrived after beat-a's claim
    # beat-a died without releasing its claim: beat-b takes both
    second = arousal.claim_pending("beat-b")
    assert sorted(e["descriptor"] for e in second) == ["one", "two"]
    arousal.release_claim("beat-b")
    assert list(Path(arousal.PENDING_PATH).parent.glob("*.claimed.*")) == []


def test_after_beat_continues_while_there_is_work_and_rests_when_none(sysd):
    sysd.running = True
    assert arousal.after_beat()["continuing"] is False and sysd.arms == []
    arousal.add_pending("peer_turn", "a peer wrote during the beat")
    d = arousal.after_beat()
    assert d["continuing"] is True and d["pending"] == 1 and len(sysd.arms) == 1
    sysd.beat_ends()
    assert sysd.starts == 1


def test_the_beings_stay_awake_starts_the_next_beat(sysd):
    sysd.running = True
    d = arousal.after_beat(stay_awake="I want to finish reading the file")
    assert d["continuing"] is True and d["stay_awake"] == "I want to finish reading the file"
    assert "asked to stay awake" in d["why"]
    sysd.beat_ends()
    assert sysd.starts == 1


def test_touch_counts_a_persisting_event_only_while_it_is_pending():
    arousal.add_pending("sense", "motion", key="k")
    assert arousal.touch_pending("k") is True and _pending()["k"]["count"] == 2
    arousal.claim_pending("b")
    assert arousal.touch_pending("k") is False and arousal.peek_pending() == []


def test_the_cli_is_what_the_daemon_calls_and_it_answers_in_json(tmp_path):
    """GPT review of SAGE#81: sage-rs conversations::arouse runs
    `python3 -m sage.gateway.arousal --instance --kind --descriptor` and parses stdout as JSON.
    Runs the module exactly as the daemon does, --dry-run so nothing is pending or started; the
    subprocess inherits SAGE_NO_SYSTEMD from the conftest."""
    repo = Path(__file__).resolve().parents[3]
    for kind in ("dp_turn", "digest", "never-heard-of-it"):
        p = subprocess.run([sys.executable, "-m", "sage.gateway.arousal", "--instance", str(tmp_path),
                            "--kind", kind, "--descriptor", "dp spoke in conversation 'dp'",
                            "--dry-run"], cwd=str(repo), capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        d = json.loads(p.stdout)
        assert d["kind"] == kind and d["engage"] is True and d["reason"] and d["dry_run"] is True
    assert arousal.peek_pending() == []
