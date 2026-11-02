"""git_clean: a being can delete ONE untracked file it created in its worktree, and nothing else.

legion-being, 2026-10-03: a probe test it wrote into its worktree could not be taken back out --
git_restore restores TRACKED files, retire_note works only in its home, and pr_amend stages
everything, so the probe would have been proposed with its work. dp: "yes".
"""
import os
import subprocess

import pytest

from sage.gateway import toolset
from sage.gateway.being_gate_client import (BeingIntent, _CONSEQUENTIAL, _REGISTRY, _TOOL_SCHEMAS,
                                            git_clean_command)
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D


def _repo(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    g = lambda *a: subprocess.run(["git", "-C", str(wt), *a], check=True,  # noqa: E731
                                  capture_output=True, text=True)
    g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (wt / "kept.py").write_text("x = 1\n")
    (wt / ".gitignore").write_text("*.log\n")
    g("add", "-A"); g("commit", "-q", "-m", "base")
    return wt


def _disp(tmp_path, wt):
    d = D.__new__(D)
    d.worktree = str(wt); d.plugin_id = "legion-being"; d.member = "legion-being"
    d.memory_root = str(tmp_path / "home"); (tmp_path / "home").mkdir(exist_ok=True)
    d._local = type("W", (), {"_witness": staticmethod(lambda what: f"w:{what}")})()
    return d


def _clean(d, path):
    return d._do_git_clean(BeingIntent(effector="git_clean", args={"path": path}))


def test_registered_consequential_described_and_offered():
    assert "git_clean" in _REGISTRY and "git_clean" in _CONSEQUENTIAL and "git_clean" in _TOOL_SCHEMAS
    assert "git_clean" in toolset.canonical_toolset() and "git_clean" in toolset.WORKTREE_VERBS


def test_the_command_is_git_clean_on_one_resolved_path(tmp_path):
    wt = _repo(tmp_path)
    cmd = git_clean_command({"path": "probe.py"}, {"worktree": str(wt)})
    assert cmd == f"git --no-pager -C {wt} clean -f -- {os.path.realpath(wt / 'probe.py')}"
    for bad in ("", "-x", "../out.py", "a b.py", ".githooks/pre-commit", ".GIT/config", "/etc/passwd"):
        with pytest.raises(ValueError):
            git_clean_command({"path": bad}, {"worktree": str(wt)})
    (wt / "dir").mkdir()
    with pytest.raises(ValueError, match="directory"):
        git_clean_command({"path": "dir"}, {"worktree": str(wt)})


def test_an_untracked_file_is_deleted_and_nothing_else_is_touched(tmp_path):
    wt = _repo(tmp_path)
    (wt / "probe_test.py").write_text("def test_probe(): pass\n")
    (wt / "other_new.py").write_text("y = 2\n")
    r = _clean(_disp(tmp_path, wt), "probe_test.py")
    assert r.ok and "DELETED probe_test.py" in r.result, r
    assert not (wt / "probe_test.py").exists()
    assert (wt / "other_new.py").exists() and (wt / "kept.py").read_text() == "x = 1\n"


def test_a_tracked_file_is_refused_and_left_as_it_is(tmp_path):
    wt = _repo(tmp_path)
    (wt / "kept.py").write_text("x = 99\n")          # even with uncommitted edits
    r = _clean(_disp(tmp_path, wt), "kept.py")
    assert not r.ok and "TRACKED" in r.error and "git_restore" in r.error
    assert (wt / "kept.py").read_text() == "x = 99\n"


def test_an_ignored_file_is_refused_with_why(tmp_path):
    wt = _repo(tmp_path)
    (wt / "run.log").write_text("noise\n")
    r = _clean(_disp(tmp_path, wt), "run.log")
    assert not r.ok and "IGNORED" in r.error
    assert (wt / "run.log").exists()


def test_a_missing_file_says_so(tmp_path):
    wt = _repo(tmp_path)
    r = _clean(_disp(tmp_path, wt), "never_written.py")
    assert not r.ok and "does not exist" in r.error


def test_it_runs_only_what_the_law_judged(tmp_path):
    wt = _repo(tmp_path)
    (wt / "probe.py").write_text("p\n")
    d = _disp(tmp_path, wt)
    d._verdict = type("V", (), {"command": f"git --no-pager -C {wt} clean -fdx"})()
    r = _clean(d, "probe.py")
    assert not r.ok and "the command the law judged is not the command" in r.error
    assert (wt / "probe.py").exists()
