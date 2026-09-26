"""What git EXECUTES is not a file the being writes, and the seat's git never runs hooks in its tree.

Measured on Legion 2026-09-25, reviewing SAGE #210: SAGE sets `core.hooksPath=.githooks`, a
TRACKED directory shared by every worktree; the being can write its own worktree (M1, wherever
`check` has its sandbox), and the gate and the harness both ALLOWED a write to
`<worktree>/.githooks/pre-commit`. The seat then runs `git commit` in that worktree for
`pr_open`/`pr_amend` — as the seat, outside bubblewrap. A gated write plus a seat-run commit is
ungated code execution, no rule broken. Nothing had exploited it. Two layers now: the harness
refuses the write (the layer the being can read), and every seat-run git in the worktree has
hooks off (the layer that actually executes)."""
import os
import subprocess
from pathlib import Path

import pytest

from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict
from sage.gateway.hestia_dispatch import _worktree_env
from sage.gateway.reference_f1a import ReferenceF1aDispatcher


def _repo_with_a_hook(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    g = lambda *a, **kw: subprocess.run(["git", "-C", str(wt), *a], check=True,
                                        capture_output=True, text=True, **kw)
    g("init", "-q")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    g("config", "core.hooksPath", ".githooks")
    (wt / ".githooks").mkdir()
    sentinel = tmp_path / "HOOK_RAN"
    hook = wt / ".githooks" / "pre-commit"
    hook.write_text(f"#!/bin/sh\ntouch '{sentinel}'\n")
    hook.chmod(0o755)
    (wt / "a.txt").write_text("a\n")
    g("add", "a.txt")
    return wt, sentinel


def test_the_hook_would_run_without_the_env__control(tmp_path):
    wt, sentinel = _repo_with_a_hook(tmp_path)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=wt, check=True, capture_output=True)
    assert sentinel.exists(), "fixture: a being-written hook DOES run on a plain seat commit"


def test_a_seat_commit_in_the_worktree_runs_no_hook(tmp_path):
    wt, sentinel = _repo_with_a_hook(tmp_path)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=wt, check=True, capture_output=True,
                   env=_worktree_env())
    assert not sentinel.exists(), "the seat ran a hook the being could have written"


def test_every_worktree_subprocess_in_the_dispatcher_carries_the_env():
    src = (Path(__file__).resolve().parent.parent / "hestia_dispatch.py").read_text()
    sites = [l for l in src.splitlines() if "cwd=self.worktree" in l]
    assert sites, "no worktree subprocess sites found — the test would be vacuous"
    missing = [l.strip() for l in sites if "env=_worktree_env()" not in l]
    assert not missing, f"a seat-run process in the being's worktree without hooks off: {missing}"


@pytest.mark.parametrize("rel", [".githooks/pre-commit", ".githooks/post-merge", ".git/config"])
def test_the_being_cannot_write_what_git_executes(tmp_path, rel, monkeypatch):
    home = tmp_path / "home"; home.mkdir()
    wt = tmp_path / "wt"; (wt / ".githooks").mkdir(parents=True); (wt / "sage").mkdir()
    d = ReferenceF1aDispatcher(str(home), worktree=str(wt))
    monkeypatch.setattr(d, "_worktree_writable", lambda: True)
    env = d(BeingIntent("memory_write", {"path": str(wt / rel), "content": "#!/bin/sh\n"}),
            GatewayVerdict("allow"))
    assert not env.ok and "not writable" in (env.error or ""), env
    assert not (wt / rel).exists()
    ok = d(BeingIntent("memory_write", {"path": str(wt / "sage" / "x.py"), "content": "x = 1"}),
           GatewayVerdict("allow"))
    assert ok.ok, "the rest of the worktree stays the being's to write"
