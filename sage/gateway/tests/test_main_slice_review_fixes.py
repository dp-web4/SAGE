"""Review findings on the #56 slices to main (SAGE #213, #216, #217, #218), carried back.

Each defect the NOT-SAME reviewers found in a slice was first a defect HERE, on the carrier
the slice was cut from. The slices were fixed on their PRs; these are the same fixes on the
branch legion-being actually runs, with the same tests.
"""
import base64
import os
import subprocess
import tempfile
from types import SimpleNamespace as NS

import pytest

from sage.gateway.being_gate_client import BeingIntent, game_command, git_restore_command, pr_amend_command
from sage.gateway.heartbeat import beat_rested
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D


def _repo(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    wt = tmp_path / "wt"
    subprocess.run(["git", "clone", "-q", str(origin), str(wt)], check=True, capture_output=True)
    g = lambda *a: subprocess.run(["git", "-C", str(wt), *a], check=True,  # noqa: E731
                                  capture_output=True, text=True)
    g("config", "user.email", "seat@test"); g("config", "user.name", "seat")
    (wt / "README").write_text("base\n"); g("add", "-A"); g("commit", "-q", "-m", "base")
    g("checkout", "-q", "-b", "legion-being/work")
    return origin, wt, g


def _disp(tmp_path, wt):
    d = D.__new__(D)
    d.worktree = str(wt); d.plugin_id = "legion-being"; d.member = "legion-being"
    d.being_lct = None; d.memory_root = str(tmp_path)
    d._local = NS(_witness=lambda what: f"w:{what}")
    return d


# -- #216: a rest with no reason is still a rest ------------------------------------------

def test_a_rest_with_no_reason_is_still_a_rest():
    assert beat_rested(NS(rested=""), None)
    assert beat_rested(NS(rested=None), NS(rested="")), "the posture turn's rest counts"
    assert not beat_rested(NS(rested=None), None) and not beat_rested(None, None)


# -- #217: pr_amend never pushes to a branch that is not its own ------------------------

@pytest.mark.parametrize("branch", ["seat-branch", "legion/seat-work", "legion-being/work", "main"])
def test_a_bodyless_amend_on_a_branch_not_its_own_is_refused_and_pushes_nothing(tmp_path, branch):
    origin, wt, g = _repo(tmp_path)
    g("checkout", "-q", "-B", branch)
    (wt / "README").write_text("the being's change\n")
    args = {"title": "a title long enough", "message": "why"}
    with pytest.raises(ValueError, match="not one of your PR branches"):
        pr_amend_command(args, {"worktree": str(wt)})
    d = _disp(tmp_path, wt)
    calls = []
    d._call = lambda name, a: calls.append(name) or {"actionId": "x"}
    env = d._do_pr_amend(BeingIntent("pr_amend", args))
    assert not env.ok and "not one of your PR branches" in env.error
    assert not calls
    assert branch not in subprocess.run(["git", "-C", str(origin), "branch"],
                                        capture_output=True, text=True).stdout.split()


def test_the_dispatcher_refuses_a_foreign_branch_even_if_the_composer_regresses(tmp_path, monkeypatch):
    import sage.gateway.being_gate_client as bgc
    origin, wt, g = _repo(tmp_path)
    g("checkout", "-q", "-b", "seat-branch")
    (wt / "README").write_text("the being's change\n")
    monkeypatch.setattr(bgc, "pr_amend_command", lambda args, ctx=None: "true")
    d = _disp(tmp_path, wt)
    d._call = lambda name, a: {"actionId": "x"}
    env = d._do_pr_amend(BeingIntent("pr_amend", {"title": "a title long enough", "message": "why"}))
    assert not env.ok and "not one of your PR branches" in env.error


def test_a_bodyless_amend_on_its_own_proposal_still_composes():
    wt = tempfile.mkdtemp(prefix="amend-own-")
    git = lambda *a: subprocess.run(["git", *a], cwd=wt, capture_output=True, text=True)  # noqa: E731
    git("init", "-q"); git("config", "user.email", "t@t"); git("config", "user.name", "t")
    open(os.path.join(wt, "f"), "w").write("x"); git("add", "-A"); git("commit", "-qm", "c")
    git("checkout", "-qb", "legion-being/a-proposal")
    assert pr_amend_command({"title": "a proper title here", "message": "why"}, {"worktree": wt}) == "true"


# -- #217: git_restore is one file, and never what git executes --------------------------

def test_git_restore_puts_back_one_file_never_a_directory(tmp_path):
    _, wt, g = _repo(tmp_path)
    (wt / "d").mkdir(); (wt / "d" / "a").write_text("a\n"); (wt / "d" / "b").write_text("b\n")
    g("add", "-A"); g("commit", "-q", "-m", "d")
    (wt / "d" / "a").write_text("edited\n")
    with pytest.raises(ValueError, match="is a directory"):
        git_restore_command({"rev": "HEAD", "path": "d"}, {"worktree": str(wt)})
    d = _disp(tmp_path, wt)
    g("rm", "-q", "-r", "--cached", "d")
    import shutil; shutil.rmtree(wt / "d")
    env = d._do_git_restore(BeingIntent("git_restore", {"rev": "HEAD", "path": "d"}))
    assert not env.ok and "a directory" in env.error
    env = d._do_git_restore(BeingIntent("git_restore", {"rev": "HEAD", "path": "README"}))
    assert env.ok, env.error


@pytest.mark.parametrize("path", [".githooks/pre-commit", ".git/config", "./.githooks/post-merge"])
def test_git_restore_cannot_put_back_what_git_executes(path):
    with pytest.raises(ValueError, match="what git EXECUTES"):
        git_restore_command({"rev": "HEAD", "path": path}, {"worktree": "/tmp/wt"})


# -- #218: the game grammar says what is wrong; one bad window costs one picture ----------

_GCTX = {"game_stepper": "/seat/stepper.py", "memory_root": "/home/being"}


def test_the_game_grammar_says_what_is_wrong():
    for bad in ({"action": "ACTION6", "x": 1}, {"probes": [{"action": "ACTION6", "x": 1}]}):
        with pytest.raises(ValueError, match="needs exactly"):
            game_command(bad, _GCTX)
    with pytest.raises(ValueError, match="not true/false"):
        game_command({"probes": [["ACTION6", True, False]]}, _GCTX)
    for g in (None, ""):
        assert " --batch ft09 " in game_command({"game": g, "probes": [["ACTION1"]]}, _GCTX)


def test_one_malformed_window_costs_one_picture_not_all():
    home = tempfile.mkdtemp(prefix="gw-")
    wdir = os.path.join(home, "scratch", "game", "windows"); os.makedirs(wdir)
    for n in ("a.jpg", "b.jpg"):
        open(os.path.join(wdir, n), "wb").write(b"IMG" + n.encode())
    d = D.__new__(D); d.memory_root = home
    good = {"file": "scratch/game/windows/b.jpg", "x": [0, 3], "y": [0, 3]}
    imgs, caps = d._game_windows({"windows": [{"file": "scratch/game/windows/a.jpg"}, good]})
    assert imgs == (base64.b64encode(b"IMGb.jpg").decode(),) and len(caps) == 1
