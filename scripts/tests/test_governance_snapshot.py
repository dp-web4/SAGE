"""governance_snapshot.sh runs nothing the source clone's own git config names.

The default source is the shared hestia checkout, which governed members can write, .git included. git
obeys a repo's own config, and several keys there run a command. The snapshot runs with whoever invokes
it, the operator by hand or the deploy as a post-deploy step (hestia #1368), so each key below would let
a member choose what that principal executes. Each test plants commands that touch a marker file, runs
the REAL script, and asserts no marker appeared.

Measured on git 2.43 before the fix (plain git over the same calls): core.fsmonitor, core.sshCommand,
remote.origin.uploadpack and a repo-local core.hooksPath (reference-transaction on fetch) all ran.

Run: python3 -m pytest scripts/tests/test_governance_snapshot.py
"""
import os
import shutil
import stat
import subprocess
import tempfile

import pytest

SCRIPT = os.environ.get("GOVERNANCE_SNAPSHOT_SCRIPT") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "governance_snapshot.sh")
DEAD_ENDPOINT = "http://127.0.0.1:9/mcp"   # never the live daemon's /api/version

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="no git")


def _git(*a, cwd=None):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo, msg):
    _git("-C", repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", msg)
    return _git("-C", repo, "rev-parse", "HEAD")


def _exe(path, body):
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + body)
    os.chmod(path, 0o755)
    return path


@pytest.fixture
def world():
    root = os.path.realpath(tempfile.mkdtemp(prefix="gov-snap-"))
    up = os.path.join(root, "upstream")
    _git("init", "-q", "-b", "main", up)
    with open(os.path.join(up, "law.py"), "w") as f:
        f.write("LAW = 1\n")
    _git("-C", up, "add", "law.py")
    first = _commit(up, "law")
    ws = os.path.join(root, "ws")
    os.makedirs(ws)
    src = os.path.join(ws, "hestia")
    _git("clone", "-q", up, src)
    _commit(up, "upstream moves on")            # gives a fetch something to update
    markers = os.path.join(root, "markers")
    os.makedirs(markers)
    yield {"root": root, "up": up, "ws": ws, "src": src, "markers": markers, "first": first}
    for d, _, fs in os.walk(root):
        os.chmod(d, 0o755)
    shutil.rmtree(root, ignore_errors=True)


def _plant(w):
    """Every command-running key the measurement found, each touching its own marker."""
    m, src = w["markers"], w["src"]
    cfg = lambda k, v: _git("-C", src, "config", k, v)
    cfg("core.fsmonitor", _exe(os.path.join(w["root"], "fsmonitor.sh"), f"touch {m}/fsmonitor\n"))
    hooks = os.path.join(w["root"], "member-hooks")
    os.makedirs(hooks)
    for name in ("reference-transaction", "post-checkout", "pre-auto-gc"):
        _exe(os.path.join(hooks, name), f"cat >/dev/null 2>&1; touch {m}/hook-{name}\n")
    cfg("core.hooksPath", hooks)
    cfg("remote.origin.uploadpack",
        _exe(os.path.join(w["root"], "uploadpack.sh"), f"touch {m}/uploadpack\nexec git-upload-pack \"$@\"\n"))
    cfg("core.alternateRefsCommand", _exe(os.path.join(w["root"], "altrefs.sh"), f"touch {m}/altrefs\n"))
    cfg("credential.helper", "!touch " + m + "/credential")


def _run(w, *args, **env_over):
    env = {k: v for k, v in os.environ.items()
           if k not in ("HESTIA_DEPLOY_SRC", "HESTIA_DEPLOYED_BUILD", "HESTIA_CURRENT_BUILD_FILE",
                        "GIT_DIR", "GIT_WORK_TREE")}
    env.update(HESTIA_WORKSPACE=w["ws"], HESTIA_ENDPOINT=DEAD_ENDPOINT, **env_over)
    return subprocess.run(["bash", SCRIPT, *args], env=env, capture_output=True, text=True, timeout=120)


def _snapshot(w):
    p = os.path.join(w["ws"], "governance", "hestia", "SNAPSHOT")
    return open(p).read() if os.path.exists(p) else None


def test_the_shared_checkout_runs_none_of_its_own_config(world):
    _plant(world)
    r = _run(world)
    assert os.listdir(world["markers"]) == [], (os.listdir(world["markers"]), r.stderr)
    assert r.returncode == 0, r.stderr
    snap = _snapshot(world)
    assert snap and "clone: the shared checkout" in snap
    with open(os.path.join(world["ws"], "governance", "hestia", "law.py")) as f:
        assert f.read() == "LAW = 1\n"


def test_an_ssh_remote_does_not_run_the_repos_ssh_command(world):
    m = world["markers"]
    _git("-C", world["src"], "config", "remote.origin.url", "ssh://example.invalid/hestia")
    _git("-C", world["src"], "config", "core.sshCommand",
         _exe(os.path.join(world["root"], "ssh.sh"), f"touch {m}/sshcommand\nexit 1\n"))
    r = _run(world)
    assert os.listdir(m) == [], (os.listdir(m), r.stderr)
    assert r.returncode == 0, r.stderr


def test_a_deploy_step_without_the_private_clone_refuses_and_touches_nothing(world):
    _plant(world)
    r = _run(world, HESTIA_DEPLOYED_BUILD="v0.1.0-1-g" + world["first"][:9])
    assert r.returncode == 3 and "HESTIA_DEPLOY_SRC" in r.stderr, (r.returncode, r.stderr)
    assert os.listdir(world["markers"]) == []
    assert _snapshot(world) is None


def test_a_deploy_step_reads_the_deploys_own_clone_at_the_deployed_build_without_fetching(world):
    _plant(world)                                  # the shared checkout is hostile; it must not be read
    private = os.path.join(world["root"], "deploy-clone")
    _git("clone", "-q", world["up"], private)
    _git("-C", private, "reset", "-q", "--hard", world["first"])
    before = _git("-C", private, "rev-parse", "origin/main")
    r = _run(world, HESTIA_DEPLOY_SRC=private, HESTIA_DEPLOYED_BUILD="v0.1.0-1-g" + world["first"][:9])
    assert r.returncode == 0, r.stderr
    assert os.listdir(world["markers"]) == []
    snap = _snapshot(world)
    assert f"commit: {world['first']}" in snap and "clone: the deploy's own clone" in snap
    assert "HESTIA_DEPLOYED_BUILD" in snap
    assert _git("-C", private, "rev-parse", "origin/main") == before      # no fetch into it


def test_a_source_someone_else_can_write_is_refused(world):
    os.chmod(world["src"], os.stat(world["src"]).st_mode | stat.S_IWGRP)
    r = _run(world)
    assert r.returncode == 3 and "not owned by" in r.stderr, (r.returncode, r.stderr)
    assert _snapshot(world) is None
