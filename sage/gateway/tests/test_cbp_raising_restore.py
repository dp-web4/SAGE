"""cbp_raising.sh: a failed restore of the being's stashed state means NO raising.

Step 1 of the script stashes the being's uncommitted live state, rebases onto origin/main, and
pops the stash back. 2026-10-08 14:00Z a conflicted rebase was left in place, the pop could not
run, and the being ran ~2h on committed (old) files while its live state sat in the stash. #395
aborts the failed rebase; GPT's HOLD at d1a32c808: a pop that fails must also stop the run, not
print ERROR and raise anyway. Invariant pinned here: failed restore => no raising, stash intact.

These drive the REAL script (its own `set -e`, and again under `-u`) against a throwaway origin
and clone, with curl/lsof/python3 stubbed on PATH. python3 is first called by the raising
session itself, so "the stub was never called" is "no raising and no beat started".
"""
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "cbp_raising.sh"
SHELLS = [["bash"], ["bash", "-u"]]


def _git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          env=_ENV, check=check).stdout.strip()


_ENV = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t"}


def _commit(repo, path, text, msg):
    (Path(repo) / path).write_text(text)
    _git(repo, "add", path)
    _git(repo, "commit", "-qm", msg)


@pytest.fixture
def world(tmp_path):
    origin, seed, sage = tmp_path / "origin.git", tmp_path / "seed", tmp_path / "SAGE"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "init", "-q", "-b", "main", str(seed))
    _commit(seed, "a.txt", "a1\n", "a")
    _commit(seed, "b.txt", "b1\n", "b")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "main")
    _git(tmp_path, "clone", "-q", str(origin), str(sage))
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    marker = tmp_path / "python3-calls"
    (stubs / "python3").write_text(f'#!/bin/bash\necho "$*" >> "{marker}"\nexit 0\n')
    (stubs / "curl").write_text("#!/bin/bash\nexit 0\n")
    (stubs / "lsof").write_text("#!/bin/bash\necho 4242\n")
    for f in stubs.iterdir():
        f.chmod(0o755)
    env = {**_ENV, "PATH": f"{stubs}:{os.environ['PATH']}", "SAGE_DIR": str(sage),
           "CBP_RAISING_LOG_DIR": str(tmp_path / "logs")}
    return dict(seed=seed, sage=sage, marker=marker, env=env)


def _run(world, shell):
    return subprocess.run([*shell, str(SCRIPT)], env=world["env"], capture_output=True,
                          text=True, timeout=120)


def _raised(world):
    m = world["marker"]
    return m.exists() and "ollama_raising_session" in m.read_text()


@pytest.mark.parametrize("shell", SHELLS, ids=lambda s: " ".join(s))
def test_a_failed_rebase_is_aborted_the_pop_succeeds_and_raising_proceeds(world, shell):
    seed, sage = world["seed"], world["sage"]
    _commit(seed, "a.txt", "upstream\n", "upstream a")
    _git(seed, "push", "-q", "origin", "main")
    _commit(sage, "a.txt", "local\n", "local a")             # diverged AND conflicting
    head = _git(sage, "rev-parse", "HEAD")
    (sage / "b.txt").write_text("being live state\n")         # uncommitted: what gets stashed
    p = _run(world, shell)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "WARNING: git pull failed" in p.stdout, p.stdout
    git_dir = Path(_git(sage, "rev-parse", "--absolute-git-dir"))
    assert not (git_dir / "rebase-merge").exists() and not (git_dir / "rebase-apply").exists()
    assert _git(sage, "rev-parse", "HEAD") == head            # back on its own commit
    assert (sage / "b.txt").read_text() == "being live state\n"
    assert _git(sage, "stash", "list") == ""
    assert _raised(world), p.stdout


@pytest.mark.parametrize("shell", SHELLS, ids=lambda s: " ".join(s))
def test_a_conflicted_pop_exits_non_zero_before_raising_and_keeps_the_stash(world, shell):
    seed, sage = world["seed"], world["sage"]
    _commit(seed, "b.txt", "upstream b\n", "upstream b")
    _git(seed, "push", "-q", "origin", "main")
    _commit(sage, "c.txt", "local c\n", "local c")           # diverged, rebases cleanly
    (sage / "b.txt").write_text("being live state\n")         # ...but the pop conflicts here
    p = _run(world, shell)
    out = p.stdout + p.stderr
    assert p.returncode != 0, out
    assert not _raised(world), "raising ran after a failed restore"
    stashes = _git(sage, "stash", "list").splitlines()
    assert len(stashes) == 1, stashes                         # preserved, never dropped
    sha = _git(sage, "rev-parse", "stash@{0}")
    assert _git(sage, "show", f"{sha}:b.txt") == "being live state"
    assert "FAILED RESTORE" in out and "NOT raising" in out, out
    assert sha in out and f"git stash apply {sha}" in out, out  # names the ref and the recovery
    assert list((Path(world["env"]["CBP_RAISING_LOG_DIR"])).glob("raising-*.log"))

    # and the NEXT firing refuses too, while the tree still holds the conflicted restore
    p2 = _run(world, shell)
    assert p2.returncode != 0, p2.stdout + p2.stderr
    assert "NOT raising" in p2.stdout + p2.stderr
    assert not _raised(world)
    assert _git(sage, "rev-parse", "stash@{0}") == sha


@pytest.mark.parametrize("shell", SHELLS, ids=lambda s: " ".join(s))
def test_a_pull_that_fails_before_rebasing_still_restores_and_raises(world, shell):
    """No rebase in progress (origin unreachable): nothing to abort, and a bare `git rebase
    --abort` would fail and end the run under `set -e` with the state still stashed."""
    sage = world["sage"]
    _commit(sage, "c.txt", "local c\n", "local c")
    (sage / "b.txt").write_text("being live state\n")
    _git(sage, "remote", "set-url", "origin", str(sage.parent / "no-such-origin.git"))
    p = _run(world, shell)
    assert p.returncode == 0, p.stdout + p.stderr
    assert (sage / "b.txt").read_text() == "being live state\n"
    assert _git(sage, "stash", "list") == ""
    assert _raised(world), p.stdout
