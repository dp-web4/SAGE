"""The next wake is armed — opt-in wake-after-quiet (#56 slice 4)."""


def test_a_running_beat_does_not_read_as_an_unarmed_timer():
    """2026-09-09T15:07Z: the end-of-beat check read `monotonic=infinity` and wrote
    "NOTHING WILL WAKE THE BEING" into the record of a beat whose timer armed correctly
    seconds later. An OnUnitInactiveSec timer CANNOT have a next elapse while the unit it
    watches is running — and this check runs from inside that unit."""
    from sage.gateway.heartbeat import interpret_timer_state

    running = ("NextElapseUSecRealtime=\n"
               "NextElapseUSecMonotonic=infinity\n"
               "LoadState=loaded\nActiveState=active\n")
    armed, why = interpret_timer_state(running)
    assert armed is True, why
    assert "correct while this beat is still running" in why

    scheduled = ("NextElapseUSecRealtime=Wed 2026-09-09 09:03:39 PDT\n"
                 "NextElapseUSecMonotonic=infinity\nLoadState=loaded\nActiveState=active\n")
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

def _fake_systemd(monkeypatch, show_out, calls):
    import subprocess as _sp
    from sage.gateway import heartbeat as H
    def fake_run(argv, **kw):
        calls.append(list(argv))
        if argv[:3] == ["systemctl", "--user", "show"]:
            return _sp.CompletedProcess(argv, 0, show_out, "")
        return _sp.CompletedProcess(argv, 0, "", "")
    monkeypatch.setattr(H.subprocess, "run", fake_run)


def test_a_healthy_idle_timer_arms_nothing_extra(monkeypatch):
    from sage.gateway import heartbeat as H
    calls = []
    _fake_systemd(monkeypatch, "NextElapseUSecRealtime=Wed 2026-09-09 09:03:39 PDT\n"
                  "NextElapseUSecMonotonic=infinity\nLoadState=loaded\nActiveState=active\n", calls)
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
