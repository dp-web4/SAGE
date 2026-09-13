

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
        if list(args)[:3] == ["systemctl", "--user", "show"]:
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
    # It STARTS the ordinary beat unit. Asserting only that IDLE_UNIT is the last argv
    # element was too weak — `systemctl --user stop --no-block sage-heartbeat.service`
    # satisfies it, and a mutation to `stop` passed the pin (caught 2026-09-13 by running
    # the mutation rather than trusting the assertion).
    tail = run[run.index("systemctl"):]
    assert tail == ["systemctl", "--user", "start", "--no-block", hb.IDLE_UNIT], tail
    # and nothing anywhere in this call path may stop or disable the persistent timer:
    # that timer is the floor under everything, and a resume wake that removed it would
    # trade "sooner" for "never".
    forbidden = {"stop", "disable", "mask", "kill"}
    for c in calls:
        assert not (forbidden & set(c)), f"resume wake must not run {c}"


def test_a_failed_resume_wake_costs_promptness_not_silence():
    """The whole reason this is additive. If it cannot arm, the ordinary interval stands."""
    import subprocess
    from sage.gateway import heartbeat as hb

    def boom(args, **kw):
        if list(args)[:3] == ["systemctl", "--user", "show"]:
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


def test_clearing_a_stale_resume_unit_touches_only_that_unit():
    """The stale-clear branch runs ONLY when the timer's SubState is not `waiting`, so a
    fake that reports `waiting` never reaches it — which is how a mutation that cleared
    the stale unit by stopping `sage-heartbeat.timer` passed twice on 2026-09-13. A pin
    that cannot reach the line it claims to guard is not a pin. This drives SubState to a
    fired state so the branch actually executes."""
    import subprocess
    from sage.gateway import heartbeat as hb

    calls = []

    def fake_run(args, **kw):
        calls.append(list(args))
        if list(args)[:3] == ["systemctl", "--user", "show"]:
            return subprocess.CompletedProcess(args, 0, "running\n", "")   # FIRED, not waiting
        return subprocess.CompletedProcess(args, 0, "", "")

    real = hb.subprocess.run
    hb.subprocess.run = fake_run
    try:
        d = hb.arm_resume_wake(180)
    finally:
        hb.subprocess.run = real

    assert d["armed"] is True
    cleared = [c for c in calls if "stop" in c or "reset-failed" in c]
    assert cleared, "a fired unit must actually be cleared before re-arming"
    for c in cleared:
        target = c[-1]
        assert target.startswith(hb.RESUME_UNIT), (
            f"the stale-clear may only touch {hb.RESUME_UNIT}; it touched {target!r} — "
            "stopping the persistent timer here would trade 'sooner' for 'never'")
