"""pr_sync: a being can bring its own open PR up to date with the base it targets.

legion-being, #272 (2026-09-30..10-01): the carrier moved under an open proposal, the PR went
CONFLICTING, and the being wrote "rebase onto 35a9dc0ad" on its todo for a day. None of its
verbs merges, so only its seat could resolve a conflict in the being's own code. These tests
run real git against a bare origin: a clean merge is committed and pushed; a conflict is left
marked for the being and refused at `continue` until every marker is gone; `abort` restores.
"""
import os
import subprocess

import pytest

from sage.gateway import toolset
from sage.gateway.being_gate_client import (BeingIntent, _CONSEQUENTIAL, _REGISTRY, _TOOL_SCHEMAS,
                                            pr_sync_command)
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D

MEMBER = "legion-being"
BASE = "legion/some-integration-target"
PR = f"{MEMBER}/my-fix"


def _sh(cwd, *a):
    return subprocess.run(["git", "-C", str(cwd), *a], check=True, capture_output=True, text=True).stdout


def _setup(tmp_path):
    """origin (bare) <- seat clone that moves the base; wt = the being's worktree on its PR branch."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seat = tmp_path / "seat"
    subprocess.run(["git", "clone", "-q", str(origin), str(seat)], check=True, capture_output=True)
    for d in (seat,):
        _sh(d, "config", "user.email", "seat@test"); _sh(d, "config", "user.name", "seat")
    (seat / "code.py").write_text("a = 1\nb = 2\nc = 3\n")
    (seat / "other.py").write_text("x = 1\n")
    _sh(seat, "add", "-A"); _sh(seat, "commit", "-q", "-m", "base")
    _sh(seat, "push", "-q", "origin", f"HEAD:{BASE}")
    wt = tmp_path / "wt"
    subprocess.run(["git", "clone", "-q", str(origin), str(wt)], check=True, capture_output=True)
    _sh(wt, "config", "user.email", "being@test"); _sh(wt, "config", "user.name", "being")
    _sh(wt, "checkout", "-q", "-b", f"{MEMBER}/work", "--track", f"origin/{BASE}")
    _sh(wt, "checkout", "-q", "-b", PR)
    (wt / "code.py").write_text("a = 1\nb = 20\nc = 3\n")       # the being's change: line 2
    _sh(wt, "commit", "-qam", "the being's fix"); _sh(wt, "push", "-q", "origin", PR)
    return origin, seat, wt


def _move_base(seat, path, text, msg="base moved"):
    _sh(seat, "fetch", "-q", "origin")
    _sh(seat, "checkout", "-q", "-B", "b", f"origin/{BASE}")
    (seat / path).write_text(text)
    _sh(seat, "commit", "-qam", msg); _sh(seat, "push", "-q", "origin", f"HEAD:{BASE}")


def _disp(tmp_path, wt):
    d = D.__new__(D)
    d.worktree = str(wt); d.plugin_id = MEMBER; d.member = MEMBER
    d.being_lct = "lct:web4:test"
    d.memory_root = str(tmp_path / "home"); (tmp_path / "home").mkdir(exist_ok=True)
    d.calls = []
    d._call = lambda name, args: d.calls.append(name) or ({"actionId": "act-9"} if name == "hestia_begin_action" else {})
    return d


def _sync(d, **args):
    return d._do_pr_sync(BeingIntent(effector="pr_sync", args=args))


def _origin_has(origin, branch, sha_of):
    return subprocess.run(["git", "--git-dir", str(origin), "merge-base", "--is-ancestor",
                           sha_of, branch], capture_output=True).returncode == 0


def test_the_verb_is_registered_consequential_described_and_offered():
    assert "pr_sync" in _REGISTRY and "pr_sync" in _CONSEQUENTIAL and "pr_sync" in _TOOL_SCHEMAS
    assert "pr_sync" in toolset.canonical_toolset(), "every being is offered it"
    assert "pr_sync" in toolset.WORKTREE_VERBS, "and told it cannot work without a worktree"


def test_the_command_is_read_from_the_worktree_never_supplied(tmp_path):
    _, _, wt = _setup(tmp_path)
    ctx = {"worktree": str(wt), "member": MEMBER}
    assert pr_sync_command({}, ctx) == f"git --no-pager -C {wt} merge --no-ff --no-commit origin/{BASE}"
    assert pr_sync_command({"op": "continue"}, ctx) == f"git --no-pager -C {wt} commit -q -F -"
    assert pr_sync_command({"op": "abort"}, ctx) == f"git --no-pager -C {wt} merge --abort"
    with pytest.raises(ValueError, match="op"):
        pr_sync_command({"op": "rebase"}, ctx)
    _sh(wt, "checkout", "-q", f"{MEMBER}/work")
    with pytest.raises(ValueError, match="not one of your PR branches"):
        pr_sync_command({}, ctx)


def test_a_clean_merge_is_committed_with_trailers_and_pushed(tmp_path):
    origin, seat, wt = _setup(tmp_path)
    _move_base(seat, "other.py", "x = 2\n")
    d = _disp(tmp_path, wt)
    r = _sync(d)
    assert r.ok and r.result["state"] == "merged" and r.result["pushed"], r
    base_head = _sh(seat, "rev-parse", "HEAD").strip()
    assert _origin_has(origin, PR, base_head), "the PR branch on origin contains the base"
    assert len(_sh(wt, "log", "-1", "--format=%P").split()) == 2, "a merge commit"
    assert "act-9" in _sh(wt, "log", "-1", "--format=%B"), "carries the witness trailer"
    assert d.calls == ["hestia_begin_action", "hestia_record_outcome"]
    assert _sync(d).result["state"] == "up_to_date"


def test_a_conflict_is_left_for_the_being_and_continue_waits_for_every_marker(tmp_path):
    origin, seat, wt = _setup(tmp_path)
    _move_base(seat, "code.py", "a = 1\nb = 200\nc = 3\n")          # same line as the being
    d = _disp(tmp_path, wt)
    before = _sh(wt, "rev-parse", "HEAD").strip()
    r = _sync(d)
    assert r.ok and r.result["state"] == "conflicted", r
    assert r.result["files"][0]["path"] == "code.py" and r.result["files"][0]["marker_lines"]
    assert r.result["headline"].startswith("CONFLICTED") and "Nothing is committed" in r.result["headline"]
    assert _sh(wt, "rev-parse", "HEAD").strip() == before, "nothing committed"
    assert subprocess.run(["git", "--git-dir", str(origin), "rev-parse", PR], capture_output=True,
                          text=True).stdout.strip() == before, "nothing pushed"
    # continue while markers remain: refused, and it says where
    r2 = _sync(d, op="continue")
    assert not r2.ok and "code.py (line" in r2.error and "nothing was committed" in r2.error
    # the being resolves (what patch_apply / edit would write), then continue
    (wt / "code.py").write_text("a = 1\nb = 220\nc = 3\n")
    r3 = _sync(d, op="continue", message="kept both: 20 from me, 200 from the base")
    assert r3.ok and r3.result["state"] == "merged", r3
    head = _sh(wt, "rev-parse", "HEAD").strip()
    assert _origin_has(origin, PR, head) and len(_sh(wt, "log", "-1", "--format=%P").split()) == 2
    assert "kept both" in _sh(wt, "log", "-1", "--format=%B")


def test_abort_puts_the_branch_back(tmp_path):
    _, seat, wt = _setup(tmp_path)
    _move_base(seat, "code.py", "a = 1\nb = 200\nc = 3\n")
    d = _disp(tmp_path, wt)
    before = _sh(wt, "rev-parse", "HEAD").strip()
    assert _sync(d).result["state"] == "conflicted"
    r = _sync(d, op="abort")
    assert r.ok and r.result["state"] == "aborted"
    assert _sh(wt, "rev-parse", "HEAD").strip() == before
    assert (wt / "code.py").read_text() == "a = 1\nb = 20\nc = 3\n"
    assert not _sync(d, op="abort").ok, "nothing to abort now, and it says so"


def test_it_refuses_before_spending_a_witnessed_act(tmp_path):
    _, seat, wt = _setup(tmp_path)
    _move_base(seat, "other.py", "x = 2\n")
    d = _disp(tmp_path, wt)
    (wt / "code.py").write_text("uncommitted\n")
    r = _sync(d)
    assert not r.ok and "uncommitted changes" in r.error
    assert not _sync(d, op="continue").ok, "continue with no merge in progress"
    assert d.calls == [], "refusals spend no witnessed act"


def test_the_dispatcher_runs_only_what_the_law_judged(tmp_path):
    _, seat, wt = _setup(tmp_path)
    _move_base(seat, "other.py", "x = 2\n")
    d = _disp(tmp_path, wt)
    d._verdict = type("V", (), {"command": "git --no-pager -C /elsewhere merge origin/main"})()
    r = _sync(d)
    assert not r.ok and "the command the law judged is not the command" in r.error
