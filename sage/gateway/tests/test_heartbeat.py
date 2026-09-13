

def test_the_resume_wake_is_additive_and_can_only_make_the_next_beat_sooner():
    """dp, 2026-09-13: "give it as much active time as we can, without forcing
    unnecessarily." A beat that `rest`ed said it was finished; a beat the window CUT had
    more to do. The short wake is armed only for the second case, ON TOP of the persistent
    timer — which is never stopped or reprogrammed, so a failure here costs promptness and
    never silence."""
    import subprocess
    from sage.gateway import heartbeat as hb

    calls = []

    def fake_run(args, **kw):
        calls.append(list(args))
        if args[:3] == ["systemctl", "--user", "show"]:
            return subprocess.CompletedProcess(args, 0, "waiting\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    real = hb.subprocess.run
    hb.subprocess.run = fake_run
    try:
        d = hb.arm_resume_wake(180)
    finally:
        hb.subprocess.run = real

    assert d["armed"] is True and d["in_s"] == 180
    run = [c for c in calls if c and c[0] == "systemd-run"][0]
    assert "--on-active=180s" in run
    assert f"--unit={hb.RESUME_UNIT}" in run
    # it STARTS the ordinary beat unit; it does not touch the persistent timer
    assert run[-1] == hb.IDLE_UNIT and "--no-block" in run
    assert not any("stop" in c and "sage-heartbeat.timer" in c for c in calls), \
        "the persistent timer must never be stopped: that is the floor under everything"


def test_a_failed_resume_wake_costs_promptness_not_silence():
    """The whole reason this is additive. If it cannot arm, the ordinary interval stands."""
    import subprocess
    from sage.gateway import heartbeat as hb

    def boom(args, **kw):
        if args[:3] == ["systemctl", "--user", "show"]:
            return subprocess.CompletedProcess(args, 0, "waiting\n", "")
        raise subprocess.CalledProcessError(1, args, stderr="nope")

    real = hb.subprocess.run
    hb.subprocess.run = boom
    try:
        d = hb.arm_resume_wake(180)
    finally:
        hb.subprocess.run = real

    assert d["armed"] is False
    assert "idle interval still stands" in d["why"]
