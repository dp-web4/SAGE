#!/usr/bin/env python3
"""daemon_verdict / upstream_newest: the four states the first cut collapsed into two.

Each case below is a review finding from another seat, kept as the fixture that would have
caught it:

  HUB, 2026-09-18     no sage-daemon has ever existed on HUB; the check said one was DOWN,
                      on every run, with no way for HUB to clear it.
  Sprout, 2026-09-18  `newest` was read from the HEAD of whatever checkout ran the script,
                      never fetched -- a seat one sage-rs commit behind got `ok` about a
                      stale binary. The check failed OPEN in the direction it exists to close.

Run: python3 sage/tools/test_fleet_fact_check.py   (or pytest; plain asserts, both fail alike)
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fleet_fact_check as F  # noqa: E402

BUILD = "0.1.0+abc1234de@2026-09-19T20:47Z"
UP = dict(reachable=True, why_unreachable="", port=8760, presence=[], build=BUILD,
          newest="abc1234", ref="origin/main", caveat="", built_resolvable=True,
          is_current=True, behind="0")
DOWN = dict(UP, reachable=False, why_unreachable="URLError", build="", newest="", ref="")


def test_no_daemon_on_this_seat_is_ok_and_says_what_it_looked_for():
    status, detail = F.daemon_verdict(**DOWN)
    assert status == F.OK, (status, detail)
    assert "runs no sage-rs daemon" in detail and "absence was looked for" in detail


def test_a_daemon_that_should_be_up_and_is_not_is_a_divergence_naming_the_evidence():
    status, detail = F.daemon_verdict(**dict(DOWN, presence=["unit /x/com.web4.sage-daemon.plist"]))
    assert status == F.DIVERGE, (status, detail)
    assert "DOWN" in detail and "com.web4.sage-daemon.plist" in detail


def test_current_and_comparable_is_ok():
    assert F.daemon_verdict(**UP)[0] == F.OK


def test_stale_is_a_divergence_with_the_count():
    status, detail = F.daemon_verdict(**dict(UP, is_current=False, behind="14"))
    assert status == F.DIVERGE and "14 sage-rs commit(s) behind" in detail


def test_current_against_a_ref_i_could_not_refresh_is_never_ok():
    # Sprout's case. "Current against what I can see" + "I could not see" != ok.
    status, detail = F.daemon_verdict(**dict(UP, caveat="origin/main is last fetched 90h ago"))
    assert status == F.UNDETERMINED, (status, detail)
    assert "90h" in detail and "cannot say" in detail


def test_stale_against_a_stale_ref_is_still_stale():
    # The caveat must not soften a finding that is already decided.
    status, detail = F.daemon_verdict(**dict(UP, is_current=False, behind="2", caveat="could not fetch"))
    assert status == F.DIVERGE and "could not fetch" in detail


def test_dirty_build_no_sha_and_unresolvable_commit():
    assert F.daemon_verdict(**dict(UP, build=BUILD.replace("@", "-dirty@")))[0] == F.DIVERGE
    assert F.daemon_verdict(**dict(UP, build="0.1.0"))[0] == F.UNDETERMINED
    assert F.daemon_verdict(**dict(UP, built_resolvable=False, is_current=False))[0] == F.UNDETERMINED
    assert F.daemon_verdict(**dict(UP, newest="", caveat="no origin/main"))[0] == F.UNDETERMINED


def _repo_pair(tmp: Path):
    """An origin with two sage-rs commits and a clone that has only fetched the first."""
    def g(cwd, *a):
        return subprocess.run(["git", "-C", str(cwd), "-c", "user.email=t@t", "-c", "user.name=t", *a],
                              capture_output=True, text=True, check=True).stdout.strip()
    origin, clone = tmp / "origin", tmp / "clone"
    (origin / "sage-rs").mkdir(parents=True)
    g(origin, "init", "-q", "-b", "main")
    (origin / "sage-rs" / "a").write_text("1"); g(origin, "add", "-A"); g(origin, "commit", "-qm", "one")
    g(tmp, "clone", "-q", str(origin), str(clone))
    (origin / "sage-rs" / "a").write_text("2"); g(origin, "add", "-A"); g(origin, "commit", "-qm", "two")
    return origin, clone, g(origin, "log", "-1", "--format=%h")


def test_upstream_newest_sees_a_commit_the_checkout_has_not_pulled():
    with tempfile.TemporaryDirectory() as d:
        origin, clone, second = _repo_pair(Path(d))
        def git(*a, timeout=20):
            return subprocess.run(["git", "-C", str(clone), *a], capture_output=True, text=True, timeout=timeout)
        old_repo, F.REPO = F.REPO, clone
        try:
            local_head = git("log", "-1", "--format=%h", "--", "sage-rs/").stdout.strip()
            assert local_head != second                      # the checkout IS behind: the old basis
            newest, ref, caveat = F.upstream_newest(git, fetch=True)
            assert (newest, ref, caveat) == (second, "origin/main", ""), (newest, ref, caveat)

            # No fetch, and the last one is old: the answer comes back WITH a caveat.
            fh = clone / ".git" / "FETCH_HEAD"
            old = time.time() - 90 * 3600
            os.utime(fh, (old, old))
            _, _, caveat = F.upstream_newest(git, fetch=False)
            assert "90h" in caveat, caveat
            # ...but a recent fetch by anyone is as good as ours.
            os.utime(fh, None)
            assert F.upstream_newest(git, fetch=False)[2] == ""

            # Fetch asked for and impossible: say so.
            git("remote", "set-url", "origin", str(Path(d) / "gone"))
            os.utime(fh, (old, old))
            _, _, caveat = F.upstream_newest(git, fetch=True)
            assert "could not fetch" in caveat, caveat
        finally:
            F.REPO = old_repo


def test_presence_finds_a_binary_and_nothing_in_an_empty_home():
    with tempfile.TemporaryDirectory() as d:
        repo, home = Path(d) / "repo", Path(d) / "home"
        home.mkdir()
        ev = [e for e in F.daemon_presence(repo, home) if not e.startswith(("process", "unit /etc", "unit /Library"))]
        assert ev == [], ev
        b = home / ".sage-deploy" / "bin"; b.mkdir(parents=True); (b / "sage-daemon").write_text("")
        assert any(e.startswith("binary") for e in F.daemon_presence(repo, home))


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(e).__name__}: {e}")
    print(f"{'FAILED' if fails else 'ok'}: {fails} failure(s)")
    sys.exit(1 if fails else 0)
