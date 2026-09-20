

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


def test_dirty_is_about_the_harness_not_about_the_beings_diary(tmp_path):
    """`dirty` must answer "is the code constituting me modified", and nothing else.

    The instance directory is TRACKED in the checkout the beat runs from, and the running
    beat writes journal, todo, conversations and account into it continuously. So a plain
    `status --porcelain` is non-empty whenever the being has written a line about its day,
    and the flag was permanently True for a reason that is not code.

    Measured 2026-09-14: legion-being ran a three-way drift check, found its own worktree
    clean, and had to write "the header's 'uncommitted edits present' did not hold for my
    tree" — reasoning correctly AROUND the flag rather than with it. A warning that is
    always on is a background colour; the cost is that a real one reads the same.
    """
    import subprocess
    from sage.gateway.heartbeat import harness_revision

    wt = tmp_path / "repo"
    (wt / "sage" / "gateway").mkdir(parents=True)
    (wt / "sage" / "instances" / "b").mkdir(parents=True)
    (wt / "sage" / "gateway" / "heartbeat.py").write_text("x = 1\n")
    (wt / "sage" / "instances" / "b" / "journal.md").write_text("day one\n")
    git = lambda *a: subprocess.run(["git", "-C", str(wt), *a], check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@t"); git("config", "user.name", "t")
    git("add", "-A"); git("commit", "-qm", "base")

    assert harness_revision(str(wt))["dirty"] is False, "a clean tree is clean"

    # the being writes its diary — that is not a harness edit
    (wt / "sage" / "instances" / "b" / "journal.md").write_text("day one\nday two\n")
    r = harness_revision(str(wt))
    assert r["dirty"] is False, f"the being's own state must not flag the harness: {r}"
    assert r["dirty_paths"] is None

    # a real harness edit must still flag, and must NAME itself
    (wt / "sage" / "gateway" / "heartbeat.py").write_text("x = 2\n")
    r = harness_revision(str(wt))
    assert r["dirty"] is True, f"a real source edit must flag: {r}"
    # THE WHOLE PATH. `_git` returns stdout.strip(), which eats porcelain's leading space on
    # the FIRST line only, so a fixed ln[3:] offset loses one character from one path and
    # none of the others — it read 'age/gateway/heartbeat.py' the first time it ran.
    assert r["dirty_paths"] == ["sage/gateway/heartbeat.py"], r["dirty_paths"]


def test_the_seed_names_the_model_not_just_the_home():
    """legion-being's home is `legion-gemma3-12b`; its model is qwen38-heretic:q3km-vl. The
    seed printed the home every beat and never the model, so its self-correction from source
    evaporated within two beats and it kept attributing findings to the wrong body. The
    harness holds args.model and must say it where the being reads."""
    import dis
    from pathlib import Path
    from sage.gateway import heartbeat as H
    line = H.body_line("qwen38-heretic:q3km-vl", Path("/x/sage/instances/legion-gemma3-12b"))
    assert "qwen38-heretic:q3km-vl" in line
    assert "legion-gemma3-12b" in line and "older name" in line, "say WHY the two differ"
    assert "YOURS" in line, "the old name was read as ANOTHER being's dir (2026-09-19)"
    assert "24576" not in line
    assert "24576 tokens" in H.body_line("m", Path("/x/legion-gemma3-12b"), 24576), "measured window"
    moved = H.body_line("m", Path("/x/legion-being"), 24576,
                        [{"path": "/x/legion-gemma3-12b", "moved": "2026-09-19"}])
    assert "/x/legion-gemma3-12b" in moved and "FROZEN" in moved and "older name" not in moved, \
        "after the rename the 'older name' sentence is false; say where it moved FROM instead"
    names = set()
    def walk(code):
        for ins in dis.get_instructions(code):
            if ins.opname in ("LOAD_GLOBAL", "LOAD_NAME", "LOAD_DEREF") and ins.argval:
                names.add(ins.argval)
        for c in code.co_consts:
            if hasattr(c, "co_consts"): walk(c)
    walk(H.main.__code__)
    assert "body_line" in names, "main() must put the body line into the seed"
