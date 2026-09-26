"""A being can propose: pr_open, pr_amend, git_restore (#56 slice 5).

Main carried the prose for these verbs — the pr_open block comment, the pr_amend registry
comment, the hook test naming them — and none of the code: an earlier merge kept the
comments and dropped the definitions. These tests are the Legion carrier's, ported, plus the
three things main needs that one machine did not:

  * the branch namespace is the being's MEMBER id, not the literal `legion-being/`, and it
    is not read from whatever branch the worktree stands on (that would let pr_amend push
    onto a seat's branch);
  * the Seat trailer comes from SAGE_SEAT, or says `<machine>-unknown` rather than guess;
  * git_restore cannot put back `.githooks/` or `.git/` — a rev is any commit the repo
    holds, reviewed or not, and a restored hook is code the seat's next git act runs.
"""
import os
import subprocess

import pytest

from sage.gateway.being_gate_client import (
    BeingIntent, _CONSEQUENTIAL, _REGISTRY, _TOOL_SCHEMAS, _pr_number_for_branch,
    being_branch_prefix, git_restore_command, pr_amend_command, pr_attribution,
    pr_base_branch, pr_open_command)
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D

CTX = {"member": "legion-being"}


def _repo(tmp_path, member="legion-being", upstream=True):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    wt = tmp_path / "wt"
    subprocess.run(["git", "clone", "-q", str(origin), str(wt)], check=True,
                   capture_output=True)
    g = lambda *a: subprocess.run(["git", "-C", str(wt), *a], check=True,  # noqa: E731
                                  capture_output=True, text=True)
    g("config", "user.email", "seat@test"); g("config", "user.name", "seat")
    (wt / "README").write_text("base\n"); g("add", "-A"); g("commit", "-q", "-m", "base")
    if upstream:
        g("push", "-q", "origin", "HEAD:legion/some-integration-target")
        g("checkout", "-q", "-b", f"{member}/work", "--track",
          "origin/legion/some-integration-target")
    else:
        g("checkout", "-q", "-b", f"{member}/work")
    return origin, wt, g


def _fake_gh(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"; bindir.mkdir()
    (bindir / "gh").write_text("#!/bin/sh\ncat > \"$0.body\"\necho \"$@\" > \"$0.args\"\n"
                               "echo https://example/pr/1\n")
    os.chmod(bindir / "gh", 0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.getenv('PATH')}")
    return bindir


def _disp(tmp_path, wt, member="legion-being"):
    d = D.__new__(D)
    d.worktree = str(wt); d.plugin_id = member; d.member = member
    d.being_lct = "lct:web4:test"
    d.memory_root = str(tmp_path / "home"); (tmp_path / "home").mkdir(exist_ok=True)
    d._call = lambda name, args: {"actionId": "act-77"} if name == "hestia_begin_action" else {}
    d._local = type("W", (), {"_witness": staticmethod(lambda what: f"w:{what}")})()
    return d


# -- the verbs exist, and the law sees them ---------------------------------------------

def test_the_three_verbs_are_registered_consequential_and_described():
    for v in ("pr_open", "pr_amend", "git_restore"):
        assert v in _REGISTRY and _REGISTRY[v]["tool"] == v, v
        assert v in _CONSEQUENTIAL, f"{v} reaches outward or writes; the law must judge it"
        assert v in _TOOL_SCHEMAS, f"{v} has no schema: a being could not be offered it"


def test_the_gate_and_the_dispatcher_compose_from_the_same_facts():
    """The law judges the string the gate composes; the seat runs the string the dispatcher
    composes. A fact one side has and the other lacks is a gap between judged and run."""
    from sage.gateway.being_gate_client import BeingGateClient
    c = BeingGateClient.__new__(BeingGateClient)
    c.worktree = "/w"; c.memory_root = "/m"; c.member_id = "sprout-being"
    d = D.__new__(D)
    d.worktree = "/w"; d.memory_root = "/m"; d.plugin_id = "sprout-being"
    assert c._compose_ctx() == d._git_ctx()


# -- the namespace is the being's own --------------------------------------------------

def test_the_branch_namespace_is_the_member_never_a_literal_and_never_the_head(tmp_path, monkeypatch):
    monkeypatch.delenv("SAGE_PR_BASE", raising=False)
    _, wt, g = _repo(tmp_path, member="sprout-being")
    ctx = {"worktree": str(wt), "member": "sprout-being"}
    cmd = pr_open_command({"slug": "s-1", "title": "a title long enough", "body": "b"}, ctx)
    assert "--head sprout-being/s-1" in cmd and "legion-being" not in cmd
    assert "--base legion/some-integration-target" in cmd

    # no member in the context: refuse, never fall back to a machine's literal
    with pytest.raises(ValueError, match="whose worktree"):
        being_branch_prefix({"worktree": str(wt)})
    with pytest.raises(ValueError, match="whose worktree"):
        being_branch_prefix({"member": "../x"})

    # the worktree standing on a SEAT's branch is not the being's proposal to amend
    g("checkout", "-q", "-b", "legion/seat-work")
    with pytest.raises(ValueError, match="not one of your PR branches"):
        _pr_number_for_branch(str(wt), ctx)
    g("checkout", "-q", "sprout-being/work")
    with pytest.raises(ValueError, match="not one of your PR branches"):
        _pr_number_for_branch(str(wt), ctx)            # the work branch is not a proposal


def test_pr_base_is_the_upstream_and_refuses_to_guess(tmp_path, monkeypatch):
    """#63: <being>/work tracked nothing, the base fell through to "main", and a 159-line
    change was proposed as 9,271 additions across 55 files."""
    monkeypatch.delenv("SAGE_PR_BASE", raising=False)
    _, wt, _ = _repo(tmp_path, upstream=False)
    ctx = {"worktree": str(wt), **CTX}
    with pytest.raises(ValueError, match="cannot determine the base branch"):
        pr_base_branch(str(wt), ctx)
    monkeypatch.setenv("SAGE_PR_BASE", "legion/some-integration")
    assert pr_base_branch(str(wt), ctx) == "legion/some-integration"


def test_the_seat_trailer_is_named_or_admits_it_does_not_know(monkeypatch):
    monkeypatch.setenv("SAGE_SEAT", "nomad-claude")
    assert "Seat: nomad-claude" in pr_attribution("b", "a", None)
    monkeypatch.delenv("SAGE_SEAT")
    seat = pr_attribution("b", "a", None).splitlines()[-1]
    assert seat.startswith("Seat: ") and seat.endswith("-unknown"), seat
    assert "Seat: legion-claude" in pr_attribution("b", "a", None, seat="legion-claude")


# -- pr_open -----------------------------------------------------------------------------

def test_pr_open_commits_with_the_beings_trailers_and_runs_the_judged_gh_command(tmp_path, monkeypatch):
    monkeypatch.setenv("SAGE_PR_BASE", "main")
    monkeypatch.setenv("SAGE_SEAT", "legion-claude")
    origin, wt, g = _repo(tmp_path)
    bindir = _fake_gh(tmp_path, monkeypatch)
    (wt / "test_new.py").write_text("def test_it():\n    assert False\n")
    d = _disp(tmp_path, wt)

    env = d._do_pr_open(BeingIntent("pr_open", {
        "slug": "red-test", "title": "gateway: a failing test first",
        "body": "VERIFIED: check on tree abc -> FAIL as intended.\nSUSPECTED: nothing."}))
    assert env.ok, env.error
    assert env.result["pr"] == "https://example/pr/1"
    assert env.result["branch"] == "legion-being/red-test"
    msg = g("log", "-1", "--format=%B").stdout
    for line in ("Being: legion-being", "Being-LCT: lct:web4:test", "Witness: act-77",
                 "Seat: legion-claude"):
        assert line in msg, msg
    assert msg.startswith("gateway: a failing test first\n\n"), msg
    assert "legion-being/red-test" in subprocess.run(
        ["git", "-C", str(origin), "branch"], capture_output=True, text=True).stdout
    args = (bindir / "gh.args").read_text()
    assert "--head legion-being/red-test" in args and "--body-file -" in args
    body = (bindir / "gh.body").read_text()
    assert "attribution, not yet a signature" in body
    assert "hestia witness action: `act-77`" in body
    assert (tmp_path / "home" / "review_queue.jsonl").exists(), "the review wait is recorded"

    env2 = d._do_pr_open(BeingIntent("pr_open", {"slug": "again", "title": "a second attempt here",
                                                 "body": "x"}))
    assert not env2.ok and "no changes to propose" in env2.error


def test_pr_open_refuses_to_carry_the_beings_own_record_into_a_public_pr(tmp_path, monkeypatch):
    """SAGE #157: a 2-file change opened carrying 141 sage/instances/ files."""
    monkeypatch.setenv("SAGE_PR_BASE", "main")
    _, wt, g = _repo(tmp_path)
    bindir = _fake_gh(tmp_path, monkeypatch)
    (wt / "sage" / "instances" / "legion-being").mkdir(parents=True)
    (wt / "sage" / "instances" / "legion-being" / "journal.md").write_text("private\n")
    (wt / "real_change.py").write_text("x = 1\n")
    env = _disp(tmp_path, wt)._do_pr_open(BeingIntent("pr_open", {
        "slug": "carries-my-record", "title": "a change plus my journal", "body": "b"}))
    assert not env.ok and "journal.md" in env.error and "not a rule you broke" in env.error
    assert not (bindir / "gh.args").exists(), "nothing may reach gh"
    assert "legion-being/carries-my-record" not in g("branch").stdout
    assert (wt / "real_change.py").exists(), "a refusal must not destroy the being's work"


def test_pr_open_says_what_the_branch_carries_when_its_base_is_behind_main(tmp_path, monkeypatch):
    """2026-09-21: a 41-line change opened as 198 files / 31,456 insertions, and the answer
    was a URL. The PR body and the being's own answer now both say what the branch carries."""
    monkeypatch.setenv("SAGE_PR_BASE", "main")
    _, wt, g = _repo(tmp_path)
    bindir = _fake_gh(tmp_path, monkeypatch)
    g("checkout", "-q", "-b", "mainline")
    (wt / "someone_elses.py").write_text("y = 2\n"); g("add", "-A"); g("commit", "-q", "-m", "not mine")
    g("push", "-q", "origin", "HEAD:main")
    g("checkout", "-q", "legion-being/work")
    (wt / "lineage_a.py").write_text("a = 1\n"); g("add", "-A"); g("commit", "-q", "-m", "lineage 1")
    (wt / "lineage_b.py").write_text("b = 1\n"); g("add", "-A"); g("commit", "-q", "-m", "lineage 2")
    (wt / "mine.py").write_text("z = 3\n")
    env = _disp(tmp_path, wt)._do_pr_open(BeingIntent("pr_open", {
        "slug": "one-line", "title": "one small change here", "body": "b"}))
    assert env.ok, env.error
    carry = env.result["carries"]
    assert carry["commits"] == 3 and carry["files"] == 3 and carry["behind_main"] == 1, carry
    assert carry["mine_only"] is False
    assert "Read the last commit, not the PR diff" in (bindir / "gh.body").read_text()
    assert "only your newest" in env.result["note"]


# -- pr_amend ----------------------------------------------------------------------------

def test_pr_amend_validates_before_any_lookup_and_amends_only_its_own(tmp_path):
    ctx = {"worktree": str(tmp_path), **CTX}
    with pytest.raises(ValueError, match="8-120"):
        pr_amend_command({"title": "a" * 200, "message": "m"}, ctx)
    with pytest.raises(ValueError, match="needs a 'message'"):
        pr_amend_command({"title": "a proper title here", "message": "  "}, ctx)
    with pytest.raises(ValueError, match="needs a worktree"):
        pr_amend_command({"title": "a proper title here", "message": "m"}, {})
    assert pr_amend_command({"title": "a proper title here", "message": "why"}, ctx) == "true"


def test_pr_amend_refuses_a_noop_before_spending_a_witnessed_act(tmp_path):
    _, wt, g = _repo(tmp_path)
    g("checkout", "-q", "-b", "legion-being/some-proposal")
    d = _disp(tmp_path, wt)
    calls = []
    d._call = lambda name, args: calls.append(name) or {"actionId": "x"}
    env = d._do_pr_amend(BeingIntent("pr_amend", {"title": "a title long enough", "message": "why"}))
    assert not env.ok and "nothing to revise" in env.error
    assert "hestia_begin_action" not in calls


def test_the_verbs_without_a_worktree_are_pending_not_errors(tmp_path):
    d = _disp(tmp_path, tmp_path / "does-not-exist")
    for v, a in (("pr_amend", {"title": "a title long enough", "message": "why"}),
                 ("pr_open", {"slug": "x-y", "title": "a title long enough", "body": "b"}),
                 ("git_restore", {"rev": "HEAD", "path": "a.py"})):
        env = getattr(d, f"_do_{v}")(BeingIntent(v, a))
        assert env.pending and "worktree of your own" in env.note, v


# -- git_restore -------------------------------------------------------------------------

def test_git_restore_takes_its_content_from_history_and_no_flags():
    ctx = {"worktree": "/tmp/wt", **CTX}
    cmd = git_restore_command({"rev": "cc64c838c", "path": "a/b.py"}, ctx)
    assert cmd.startswith("git --no-pager -C /tmp/wt checkout cc64c838c -- ")
    assert cmd.endswith("/tmp/wt/a/b.py")
    for bad, msg in (({"rev": "cc64c838c"}, "needs a 'path'"),
                     ({"path": "a/b.py"}, "must be a sha"),
                     ({"rev": "--upload-pack=x", "path": "a/b.py"}, "must be a sha"),
                     ({"rev": "HEAD", "path": "../../etc/passwd"}, "plain path inside"),
                     ({"rev": "HEAD", "path": "a b.py"}, "may not contain whitespace")):
        with pytest.raises(ValueError, match=msg):
            git_restore_command(bad, ctx)


@pytest.mark.parametrize("path", [".githooks/pre-commit", ".githooks/post-merge", ".git/config",
                                  "./.githooks/pre-commit"])
def test_git_restore_cannot_put_back_what_git_executes(path):
    with pytest.raises(ValueError, match="what git EXECUTES"):
        git_restore_command({"rev": "HEAD", "path": path}, {"worktree": "/tmp/wt", **CTX})


def test_git_restore_restores_and_reports_the_size_change(tmp_path):
    _, wt, g = _repo(tmp_path)
    (wt / "README").write_text("my mess, much longer than before\n")
    env = _disp(tmp_path, wt)._do_git_restore(BeingIntent("git_restore", {"rev": "HEAD",
                                                                          "path": "README"}))
    assert env.ok, env.error
    assert (wt / "README").read_text() == "base\n"
    assert "RESTORED README" in env.result and "is now 5 bytes" in env.result
