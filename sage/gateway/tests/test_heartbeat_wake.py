"""The next wake is armed — opt-in wake-after-quiet (#56 slice 4)."""

import pytest


def _timer(*, active="active", target=None, real="", mono="infinity", directive=""):
    from sage.gateway import heartbeat as H
    return (f"LoadState=loaded\nActiveState={active}\n"
            f"Triggers={H.IDLE_UNIT if target is None else target}\n"
            f"NextElapseUSecRealtime={real}\nNextElapseUSecMonotonic={mono}\n"
            f"TimersMonotonic={{ {directive} ; next_elapse=infinity }}\n")


@pytest.mark.parametrize("directive", ["", "OnUnitActiveUSec=30min", "OnBootUSec=10min",
                                        "OnUnitInactiveUSec=0", "OnUnitInactiveUSec=infinity"])
def test_loaded_active_is_not_proof_of_an_inactivity_wake(directive):
    from sage.gateway.heartbeat import interpret_timer_state
    assert not interpret_timer_state(_timer(directive=directive), unit_state="activating")[0]


@pytest.mark.parametrize("state", ["", "inactive", "failed", "deactivating"])
def test_inactivity_timer_needs_observed_running_target_when_no_deadline(state):
    from sage.gateway.heartbeat import interpret_timer_state
    assert not interpret_timer_state(_timer(directive="OnUnitInactiveUSec=30min"),
                                     unit_state=state)[0]


@pytest.mark.parametrize("sentinel", ["", "0", "infinity", "n/a", "[not set]"])
def test_absent_deadline_sentinels_are_not_schedules(sentinel):
    from sage.gateway.heartbeat import interpret_timer_state
    assert not interpret_timer_state(_timer(real=sentinel, mono=sentinel))[0]


@pytest.mark.parametrize("active,target", [("inactive", None), ("failed", None),
                                           ("active", "another.service"), ("active", "")])
def test_deadline_does_not_override_unhealthy_timer_or_wrong_target(active, target):
    from sage.gateway.heartbeat import interpret_timer_state
    assert not interpret_timer_state(_timer(active=active, target=target, mono="1h 30min"))[0]


def test_all_monotonic_directives_are_checked_and_custom_unit_is_honored(monkeypatch):
    from sage.gateway import heartbeat as H
    monkeypatch.setattr(H, "IDLE_UNIT", "custom-beat.service")
    out = _timer(directive="OnUnitInactiveUSec=30min")
    out += "TimersMonotonic={ OnBootUSec=10min ; next_elapse=0 }\n"
    assert H.interpret_timer_state(out, unit_state="active")[0]


def test_nonzero_timer_query_is_not_evidence_even_with_plausible_stdout(monkeypatch):
    from sage.gateway import heartbeat as H
    calls = []
    _fake_systemd(monkeypatch, _timer(mono="1h 30min"), calls, timer_rc=1)
    armed, detail = H.next_wake_is_armed()
    assert not armed and "exit 1" in detail


def test_failed_unit_query_cannot_establish_pending_inactivity_wake(monkeypatch):
    from sage.gateway import heartbeat as H
    calls = []
    _fake_systemd(monkeypatch, _timer(directive="OnUnitInactiveUSec=30min"),
                  calls, unit_rc=1)
    assert not H.next_wake_is_armed()[0]


def test_concrete_schedule_needs_no_second_property_query(monkeypatch):
    from sage.gateway import heartbeat as H
    calls = []
    _fake_systemd(monkeypatch, _timer(mono="1h 30min"), calls, unit_rc=1)
    assert H.next_wake_is_armed()[0]
    assert len(calls) == 1


def test_verified_pending_inactivity_wake_does_not_arm_fallback(monkeypatch):
    from sage.gateway import heartbeat as H
    calls = []
    _fake_systemd(monkeypatch, _timer(directive="OnUnitInactiveUSec=30min"), calls)
    assert H.arm_next_wake(600)["by"] == H.IDLE_TIMER
    assert not any(c[0] == "systemd-run" for c in calls)
    timer_query = next(c for c in calls if H.IDLE_TIMER in c)
    assert "TimersMonotonic" in timer_query and "Triggers" in timer_query


def test_unverified_pending_wake_uses_existing_opt_in_fallback(monkeypatch):
    from sage.gateway import heartbeat as H
    calls = []
    _fake_systemd(monkeypatch, _timer(directive="OnUnitActiveUSec=30min"), calls)
    assert H.arm_next_wake(600)["by"] == "systemd-run fallback"
    assert any(c[0] == "systemd-run" for c in calls)


def test_failed_inspection_and_fallback_do_not_claim_all_wake_sources_are_absent(monkeypatch):
    from sage.gateway import heartbeat as H
    monkeypatch.setattr(H, "next_wake_is_armed", lambda: (False, "query unavailable"))
    def unavailable(*args, **kwargs):
        raise FileNotFoundError("systemd-run")
    monkeypatch.setattr(H.subprocess, "run", unavailable)
    result = H.arm_next_wake(600)
    assert not result["armed"] and "other wake sources may still fire" in result["why"]


def test_example_measures_quiet_after_completion():
    from pathlib import Path
    example = (Path(__file__).resolve().parent.parent / "systemd" /
               "sage-heartbeat.timer.example").read_text()
    assert "OnUnitInactiveSec=30min" in example
    assert "OnUnitActiveSec=" not in example


def test_a_running_beat_does_not_read_as_an_unarmed_timer():
    """2026-09-09T15:07Z: the end-of-beat check read `monotonic=infinity` and wrote
    "NOTHING WILL WAKE THE BEING" into the record of a beat whose timer armed correctly
    seconds later. An OnUnitInactiveSec timer CANNOT have a next elapse while the unit it
    watches is running — and this check runs from inside that unit."""
    from sage.gateway.heartbeat import interpret_timer_state, IDLE_UNIT

    running = ("NextElapseUSecRealtime=\n"
               "NextElapseUSecMonotonic=infinity\n"
               "LoadState=loaded\nActiveState=active\n"
               f"Triggers={IDLE_UNIT}\n"
               "TimersMonotonic={ OnUnitInactiveUSec=30min ; next_elapse=infinity }\n")
    armed, why = interpret_timer_state(running, unit_state="activating")
    assert armed is True, why
    assert "verified OnUnitInactiveSec" in why

    scheduled = ("NextElapseUSecRealtime=Wed 2026-09-09 09:03:39 PDT\n"
                 "NextElapseUSecMonotonic=infinity\nLoadState=loaded\nActiveState=active\n"
                 f"Triggers={IDLE_UNIT}\n")
    armed, why = interpret_timer_state(scheduled)
    assert armed is True and why.startswith("scheduled:")

    # the real failure this exists for: the timer is gone or dead, not merely unscheduled
    for bad in ("NextElapseUSecRealtime=\nNextElapseUSecMonotonic=infinity\n"
                "LoadState=not-found\nActiveState=inactive\n",
                "NextElapseUSecRealtime=\nNextElapseUSecMonotonic=infinity\n"
                "LoadState=loaded\nActiveState=failed\n",
                "NextElapseUSecRealtime=\nNextElapseUSecMonotonic=infinity\n"
                "LoadState=loaded\nActiveState=inactive\n"):
        armed, why = interpret_timer_state(bad)
        assert armed is False, why
        assert "not healthy" in why

def _fake_systemd(monkeypatch, show_out, calls, *, unit_state="activating", timer_rc=0, unit_rc=0):
    import subprocess as _sp
    from sage.gateway import heartbeat as H
    def fake_run(argv, **kw):
        calls.append(list(argv))
        if argv[:3] == ["systemctl", "--user", "show"]:
            if argv[3] == H.IDLE_UNIT:
                return _sp.CompletedProcess(argv, unit_rc, unit_state, "")
            return _sp.CompletedProcess(argv, timer_rc, show_out, "")
        return _sp.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(H.subprocess, "run", fake_run)


def test_a_healthy_idle_timer_arms_nothing_extra(monkeypatch):
    from sage.gateway import heartbeat as H
    calls = []
    _fake_systemd(monkeypatch, "NextElapseUSecRealtime=Wed 2026-09-09 09:03:39 PDT\n"
                  "NextElapseUSecMonotonic=infinity\nLoadState=loaded\nActiveState=active\n"
                  f"Triggers={H.IDLE_UNIT}\n", calls)
    r = H.arm_next_wake(600)
    assert r["armed"] and r["by"] == H.IDLE_TIMER
    assert not any(c[0] == "systemd-run" for c in calls), "the timer is fine; no fallback"


def test_a_dead_idle_timer_gets_a_fallback_wake_so_silence_is_never_the_failure(monkeypatch):
    from sage.gateway import heartbeat as H
    calls = []
    _fake_systemd(monkeypatch, "NextElapseUSecRealtime=\nNextElapseUSecMonotonic=infinity\n"
                  "LoadState=loaded\nActiveState=failed\n", calls)
    r = H.arm_next_wake(600)
    runs = [c for c in calls if c[0] == "systemd-run"]
    assert runs and any("--on-active=600s" in " ".join(c) for c in runs), runs
    assert r["armed"] and "fallback" in r["by"]


def test_the_wake_machinery_is_opt_in_and_off_by_default():
    import ast
    from pathlib import Path
    from sage.gateway import heartbeat as H
    src = Path(H.__file__).read_text()
    assert '"--idle-wake-s", type=int, default=0' in src and '"--resume-wake-s", type=int, default=0' in src
    main = [n for n in ast.parse(src).body if getattr(n, "name", "") == "main"][0]
    seg = ast.get_source_segment(src, main)
    assert "if args.idle_wake_s > 0 or args.resume_wake_s > 0:" in seg, "a machine that did not ask gets no change"


def test_a_rest_with_no_reason_is_still_a_rest():
    """sprout on #216: `rested` is Optional[str] and a reasonless rest is "". bool("") is False,
    so the being that rested without explaining itself was handed the resume wake it declined."""
    from types import SimpleNamespace as NS
    from sage.gateway.heartbeat import beat_rested
    assert beat_rested(NS(rested=""), None), "a rest with no reason is a rest"
    assert beat_rested(NS(rested="done for now"), None)
    assert not beat_rested(NS(rested=None), None)
    assert not beat_rested(None, None), "a beat killed before any turn did not rest"
    assert beat_rested(NS(rested=None), NS(rested="")), "the posture turn's rest counts too"


def test_the_resume_wake_is_not_armed_after_a_reasonless_rest():
    """The decision as main() makes it: the arm call is guarded by beat_rested, not bool()."""
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "heartbeat.py").read_text()
    main = [n for n in ast.parse(src).body if getattr(n, "name", "") == "main"][0]
    body = ast.unparse(main)
    assert "_rested = beat_rested(explore, after)" in body
    assert "if not _rested and args.resume_wake_s > 0" in body
