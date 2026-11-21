"""Replies pushed after the seat's shared-context checkout last moved still reach the beat (#792).

cbp 2026-11-19: the checkout was 13 commits behind origin/main and two replies to cbp-being were not in
it; nothing in SAGE pulls it. The beat now fetches (remote-tracking refs only) and reads the posts on
origin/main that the working tree lacks, without touching the tree siblings share."""
import os
import subprocess
import time

import pytest

from sage.gateway import forum_replies as fr

ME = "cbp-being"


def git(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                       env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                                GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def reply(name, body="The answer is on the forum.", to=ME):
    return name, f"---\nfrom: pub-claude\nto: {to}\ndate: {today()}\nre: model trial\n---\n\n{body}\n"


def commit(clone, files, msg="post"):
    (clone / "forum").mkdir(exist_ok=True)
    for name, text in files:
        (clone / "forum" / name).write_text(text)
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", msg)
    git(clone, "push", "-q", "origin", "HEAD:main")


@pytest.fixture
def fleet(tmp_path):
    """origin (bare), the seat's checkout <root>/shared-context beside <root>/sage, and a peer clone."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    peer = tmp_path / "peer"
    git(tmp_path, "clone", "-q", str(origin), str(peer))
    git(peer, "checkout", "-q", "-b", "main")
    commit(peer, [("README.md", "forum\n")], "init")
    root = tmp_path / "ai"
    (root / "sage" / "home").mkdir(parents=True)
    seat = root / "shared-context"
    git(tmp_path, "clone", "-q", str(origin), str(seat))
    return root / "sage", seat, peer, root / "sage" / "home"


def beat(home, workspace, **kw):
    got = fr.for_beat(home, str(workspace), ME, **kw)
    fr.acknowledge(home, got["offered"])
    return got


def test_a_reply_pushed_after_the_last_pull_is_offered(fleet):
    workspace, seat, peer, home = fleet
    name, text = reply(f"pub-to-cbp-being-what-the-model-trial-is-{today()}.md")
    commit(peer, [(name, text)])
    assert not (seat / "forum" / name).exists(), "the seat's checkout is behind"
    got = beat(home, workspace)
    assert got["offered"] == [name]
    assert got["upstream"]["fetched"] is True and got["upstream"]["offered"] == [name]
    assert "The answer is on the forum." in got["block"]
    assert f"origin/main:forum/{name} — not in this checkout yet" in got["block"]
    assert beat(home, workspace)["offered"] == [], "delivered once, by name, like any reply"


def test_the_shared_checkout_is_never_moved(fleet):
    workspace, seat, peer, home = fleet
    (seat / "scratch.txt").write_text("a sibling's uncommitted work")
    head = git(seat, "rev-parse", "HEAD")
    commit(peer, [reply(f"hub-to-cbp-being-how-you-are-categorized-{today()}.md")])
    assert beat(home, workspace)["offered"]
    assert git(seat, "rev-parse", "HEAD") == head
    assert git(seat, "status", "--porcelain") == "?? scratch.txt"
    assert sorted(x.name for x in (seat / "forum").iterdir()) == ["README.md"]


def test_a_post_already_on_disk_is_read_from_disk_once(fleet):
    workspace, seat, peer, home = fleet
    name, text = reply(f"pub-re-cbp-being-{today()}.md")
    commit(peer, [(name, text)])
    git(seat, "pull", "-q", "--ff-only")
    got = beat(home, workspace)
    assert got["offered"] == [name] and got["upstream"]["unpulled"] == 0
    assert f"shared-context/forum/{name}" in got["block"] and "not in this checkout" not in got["block"]


def test_a_reply_offered_from_upstream_is_not_offered_again_once_pulled(fleet):
    workspace, seat, peer, home = fleet
    name, text = reply(f"pub-re-cbp-being-{today()}.md")
    commit(peer, [(name, text)])
    assert beat(home, workspace)["offered"] == [name]
    git(seat, "pull", "-q", "--ff-only")
    assert beat(home, workspace)["offered"] == []


def test_posts_not_addressed_to_the_being_stay_unoffered(fleet):
    workspace, seat, peer, home = fleet
    commit(peer, [reply(f"pub-to-sprout-being-{today()}.md", to="sprout-being"),
                  reply(f"cbp-being-asks-pub-{today()}.md")])
    got = beat(home, workspace)
    assert got["offered"] == [] and got["upstream"]["unpulled"] == 2


def test_fetch_is_throttled_by_the_last_fetch(fleet):
    workspace, seat, peer, home = fleet
    assert fr.for_beat(home, str(workspace), ME)["upstream"]["fetched"] is True
    commit(peer, [reply(f"pub-re-cbp-being-{today()}.md")])
    got = fr.for_beat(home, str(workspace), ME)
    assert got["upstream"]["fetched"] is False and got["offered"] == [], "fetched under FETCH_EVERY_S ago"
    later = time.time() + fr.FETCH_EVERY_S + 1
    got = fr.for_beat(home, str(workspace), ME, now=later)
    assert got["upstream"]["fetched"] is True and len(got["offered"]) == 1


def test_fetch_can_be_turned_off_and_what_origin_holds_is_still_read(fleet, monkeypatch):
    workspace, seat, peer, home = fleet
    name, text = reply(f"pub-re-cbp-being-{today()}.md")
    commit(peer, [(name, text)])
    monkeypatch.setenv("SAGE_FORUM_FETCH", "0")
    assert fr.for_beat(home, str(workspace), ME)["offered"] == []
    git(seat, "fetch", "-q", "origin")  # some session fetched; the tree is still behind
    got = fr.for_beat(home, str(workspace), ME)
    assert got["offered"] == [name] and got["upstream"]["fetched"] is False


def test_an_unreachable_origin_is_said_and_disk_replies_still_come(fleet):
    workspace, seat, peer, home = fleet
    name, text = reply(f"pub-re-cbp-being-{today()}.md")
    (seat / "forum" / name).write_text(text)
    git(seat, "remote", "set-url", "origin", str(seat.parent / "gone.git"))
    got = fr.for_beat(home, str(workspace), ME, now=time.time() + fr.FETCH_EVERY_S + 1)
    assert got["offered"] == [name]
    assert got["upstream"]["fetched"] is False and got["upstream"]["why"].startswith("fetch failed")


def test_a_forum_that_is_not_a_git_checkout_runs_no_git(tmp_path, monkeypatch):
    (tmp_path / "ai" / "sage" / "home").mkdir(parents=True)
    (tmp_path / "ai" / "shared-context" / "forum").mkdir(parents=True)
    monkeypatch.setattr(fr, "_git", lambda *a, **k: pytest.fail("git ran outside a checkout"))
    got = fr.for_beat(tmp_path / "ai" / "sage" / "home", str(tmp_path / "ai" / "sage"), ME)
    assert got["offered"] == [] and got["upstream"]["why"] == "not a git checkout"


def test_upstream_lists_the_forum_directory_one_level_like_the_disk_scan(fleet):
    """`ls-tree … forum/` (trailing slash) lists forum's entries, not the directory itself (NOVA,
    #796 review). Replies are top-level posts: the disk scan is `forum/*.md`, and upstream matches it.
    A post in a subdirectory is offered by neither, and a directory whose name ends in .md is no post."""
    workspace, seat, peer, home = fleet
    top, top_text = reply(f"pub-to-cbp-being-top-{today()}.md")
    (peer / "forum" / "sub").mkdir(parents=True)
    (peer / "forum" / "sub" / f"pub-to-cbp-being-nested-{today()}.md").write_text(reply("x")[1])
    (peer / "forum" / f"dir-to-cbp-being-{today()}.md").mkdir()
    (peer / "forum" / f"dir-to-cbp-being-{today()}.md" / "inner.txt").write_text("not a post\n")
    commit(peer, [(top, top_text)])
    got = beat(home, workspace)
    assert got["offered"] == [top]
    assert sorted(fr.upstream_posts(seat, fetch=False)["posts"]) == [top]


def test_a_failed_fetch_still_offers_what_the_stale_ref_holds_and_says_so(fleet):
    workspace, seat, peer, home = fleet
    name, text = reply(f"pub-re-cbp-being-{today()}.md")
    commit(peer, [(name, text)])
    git(seat, "fetch", "-q", "origin")
    git(seat, "remote", "set-url", "origin", str(seat.parent / "gone.git"))
    got = fr.for_beat(home, str(workspace), ME, now=time.time() + fr.FETCH_EVERY_S + 1)
    assert got["offered"] == [name], "origin/main from the last good fetch is still read"
    assert got["upstream"]["fetched"] is False and got["upstream"]["why"].startswith("fetch failed")
