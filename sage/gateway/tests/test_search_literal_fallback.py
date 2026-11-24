"""search: a pattern git cannot parse as a regex is searched as literal text, and says so.

mcnugget-being, 2026-11-17: `search {"pattern": "drain_once("}` failed `git grep -E` with exit 128
("parentheses not balanced") 6 times in 6 hours, each receipt telling it to add a backslash; the
next beat sent the same text again. The mode is chosen when the command is composed, so the
command the law judges is the command that runs (no retry with a different command)."""
import os
import shlex
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import search_command, search_mode  # noqa: E402
from sage.gateway.hestia_dispatch import _literal_key  # noqa: E402


def _repo():
    wt = os.path.realpath(tempfile.mkdtemp(prefix="srch-"))
    subprocess.run(["git", "init", "-q", wt], check=True)
    with open(os.path.join(wt, "egress_drain.py"), "w") as f:
        f.write("def drain_once(inbox):\n    faults =** 0\n    return (a|b)\n")
    subprocess.run(["git", "-C", wt, "add", "."], check=True)
    return wt


def _run(cmd):
    return subprocess.run(shlex.split(cmd), capture_output=True, text=True)


def test_an_invalid_regex_is_searched_literally_and_finds_the_text():
    wt = _repo()
    for pattern, line in (("drain_once(", "1:def drain_once(inbox):"), ("faults =**", "2:    faults =** 0")):
        assert search_mode(pattern) == "-F", pattern
        cmd = search_command({"pattern": pattern}, {"worktree": wt})
        assert " -F " in cmd and " -E " not in cmd, cmd
        r = _run(cmd)
        assert r.returncode == 0, (pattern, r.returncode, r.stderr)
        assert any(o.endswith(line) for o in r.stdout.splitlines()), (pattern, r.stdout)
        note = _literal_key(pattern)["literal"]
        assert "literal text" in note and repr(pattern) in note, note


def test_a_valid_regex_is_unchanged():
    wt = _repo()
    for pattern in ("drain_once", r"drain_once\(", "def [a-z_]+\\(", "a|b"):
        assert search_mode(pattern) == "-E", pattern
        cmd = search_command({"pattern": pattern}, {"worktree": wt})
        assert " -E " in cmd, cmd
        assert _literal_key(pattern) == {}
    r = _run(search_command({"pattern": r"drain_once\("}, {"worktree": wt}))
    assert r.returncode == 0 and "drain_once(inbox)" in r.stdout, r


def test_without_the_fallback_git_refuses_the_same_text():
    """The defect, measured: the composed -E command exits 128 on the being's pattern."""
    wt = _repo()
    cmd = search_command({"pattern": "drain_once("}, {"worktree": wt}).replace(" -F ", " -E ")
    assert _run(cmd).returncode == 128
