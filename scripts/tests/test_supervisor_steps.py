"""The supervisor cannot announce a step it did not complete (NOVA's HOLD on SAGE #513).

mcnugget_supervisor.sh ran its governance snapshots and the being's worktree sync as `$(bash … | tail -1)`
under `set -u` alone, so the `tail` succeeded whatever the script exited and any 40-hex string on the last
line became the fleet line's "fresh" commit. Each step is now a function in sage/scripts/supervisor_steps.sh
that keeps the step's own exit status and accepts only the step's own success line. These tests drive those
functions with FAKE step scripts (nothing touches a real snapshot, worktree or daemon), under the bash the
supervisor itself runs under (/bin/bash: 3.2 on macOS).

Run: python3 -m pytest scripts/tests/test_supervisor_steps.py
"""
import os
import subprocess
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = os.path.join(HERE, "..", "..", "sage", "scripts", "supervisor_steps.sh")
SUPERVISOR = os.path.join(HERE, "..", "..", "sage", "scripts", "mcnugget_supervisor.sh")
BASH = "/bin/bash" if os.path.exists("/bin/bash") else "bash"
HASH = "519ac5577bfe0b12e780ec19628d9541c220513b"


def _fake(body: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".sh")
    with os.fdopen(fd, "w") as f:
        f.write("#!/usr/bin/env bash\n" + body + "\n")
    return path


def _call(fn: str, *args: str):
    """(rc, stdout token, stderr log) of one supervisor_steps.sh function."""
    p = subprocess.run([BASH, "-c", f'. "{STEPS}"; {fn} "$@"', "steps", *args],
                       capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout.strip(), p.stderr


@pytest.mark.parametrize("label,prefix", [("hestia", "governance snapshot"), ("sage", "sage governance snapshot")])
def test_a_real_snapshot_success_is_reported_with_its_commit(label, prefix):
    for line in (f"{prefix} now at {HASH} (1170 files, read-only)", f"{prefix} already at {HASH}"):
        rc, out, log = _call("snapshot_status", label, prefix, _fake(f'echo "{line}"'))
        assert rc == 0 and out == f"{label} {HASH[:8]}", out
        assert line in log, "the full output reaches the local log"


def test_a_failing_snapshot_that_prints_a_plausible_hash_is_not_fresh():
    # the old `| tail -1` + grep -oE '[0-9a-f]{40}' would have logged this as a fresh snapshot
    script = _fake(f'echo "governance snapshot: refused: /x is not owned by me alone" >&2\n'
                   f'echo "last known {HASH}"\nexit 3')
    rc, out, log = _call("snapshot_status", "hestia", "governance snapshot", script)
    assert rc == 1 and out == "hestia FAILED (rc=3)" and HASH[:8] not in out
    assert "refused: /x is not owned" in log, "diagnostics are kept, not reduced to one line"


def test_a_zero_exit_without_the_success_line_is_not_fresh():
    rc, out, _ = _call("snapshot_status", "sage", "sage governance snapshot", _fake(f'echo "{HASH}"'))
    assert rc == 1 and out.startswith("sage FAILED (rc=0 but no") and HASH[:8] not in out
    rc, out, _ = _call("snapshot_status", "sage", "sage governance snapshot", _fake("true"))   # no data
    assert rc == 1 and "FAILED" in out


def test_a_missing_step_script_is_named_not_skipped():
    rc, out, _ = _call("snapshot_status", "hestia", "governance snapshot", "/nonexistent/governance_snapshot.sh")
    assert rc == 1 and out.startswith("hestia FAILED (script missing")


@pytest.mark.parametrize("rc_in,reason", [
    (3, "NOT SYNCED: /w has modified tracked files (the being's work). Leaving it alone."),
    (4, "NOT SYNCED: worktree is on 'mcnugget-being/pr', whose work is NOT yet in main (an open PR,"),
])
def test_a_refused_worktree_sync_is_reported_as_not_synced_with_its_reason(rc_in, reason):
    # the fake also prints a success-looking line: only the exit status and the contract decide
    script = _fake(f'echo "{reason}" >&2\necho "already at abc1234 looks fine"\nexit {rc_in}')
    rc, out, log = _call("worktree_status", script, "/w", "main", "mcnugget-being")
    assert rc == 1 and out.startswith(f"being worktree NOT SYNCED (rc={rc_in}: ")
    assert reason[12:40] in out and reason in log


def test_a_worktree_sync_success_is_reported():
    for line in ("already at 4dff52caa egress drain: ...", "synced to 4dff52caa egress drain: ..."):
        rc, out, _ = _call("worktree_status", _fake(f'echo "{line}"'), "/w", "main", "mcnugget-being")
        assert rc == 0 and out == f"being worktree {line[:60]}"


def test_the_supervisor_runs_each_step_through_these_functions_and_never_through_a_pipe():
    src = open(SUPERVISOR).read()
    assert 'snapshot_status hestia "governance snapshot"' in src
    assert 'snapshot_status sage "sage governance snapshot"' in src
    assert "worktree_status " in src
    for script in ("governance_snapshot.sh", "governance_snapshot_sage.sh", "sync_being_worktree.sh"):
        for line in src.splitlines():
            if script in line and "| tail" in line:
                pytest.fail(f"{script} is still piped through tail: {line.strip()}")
    assert "— ${REPO_LINE};" in src, "the fleet line says 'repos synced' only when every repo synced"


def test_the_success_lines_parsed_are_the_ones_the_real_scripts_print():
    # if a step script's success wording changes, the supervisor would report every run FAILED: pin both
    scripts = os.path.join(HERE, "..")
    for name, needles in (("governance_snapshot.sh", ('echo "governance snapshot already at $REV"',
                                                      'echo "governance snapshot now at $REV (')),
                          ("governance_snapshot_sage.sh", ('echo "sage governance snapshot already at $REV"',
                                                           'echo "sage governance snapshot now at $REV (')),
                          ("sync_being_worktree.sh", ('echo "already at $(git log --oneline -1)"',
                                                      'echo "synced to $(git log --oneline -1)"',
                                                      'echo "NOT SYNCED: '))):
        src = open(os.path.join(scripts, name)).read()
        for n in needles:
            assert n in src, f"{name} no longer prints {n!r}"


def test_both_files_parse_under_the_supervisors_own_bash():
    for f in (STEPS, SUPERVISOR):
        p = subprocess.run([BASH, "-n", f], capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
