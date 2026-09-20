"""The fleet ruling on being records, as a check that fails when it stops being true.

dp, 2026-09-19: existing public being records are retained as-is; going forward a being's home is
`sage/instances/<machine>-being/`, gitignored in public SAGE and mirrored to private-context.

Why a test and not a comment: on the day of the ruling two seats each declared their being's
conversations private, and both were wrong — one inferred it from `main`, one "knew" — because the
declaration had a falsifier nobody ran. Legion's were on a pushed branch; HUB's were published by a
script every six hours. `git add <instance dir>` and `git add -A` are how every one of them got there.
"""
import os
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)


pytestmark = pytest.mark.skipif(_git("rev-parse", "--git-dir").returncode != 0,
                                reason="not a git checkout (sdist / vendored copy)")


@pytest.mark.parametrize("machine", ["cbp", "legion", "sprout", "hub", "a-machine-not-yet-built"])
def test_a_beings_home_is_ignored_on_every_machine(machine):
    for leaf in ("conversations/dp.jsonl", "journal.md", "notes/x.md", "todo.md", "identity.sealed"):
        path = f"sage/instances/{machine}-being/{leaf}"
        assert _git("check-ignore", "-q", path).returncode == 0, f"{path} would be committed by `git add -A`"


def test_the_public_historical_record_is_not_swallowed_by_the_rule():
    """CONTROL. The ruling retains what is already public. A rule broad enough to hide the
    model-named directories would make `git status` silent about them, which is not retention."""
    for kept in ("sage/instances/cbp-qwen3.8-distill-4b/conversations/dp.jsonl",
                 "sage/instances/_seed/identity.json"):
        assert _git("check-ignore", "-q", kept).returncode != 0, kept


def test_no_beings_home_is_tracked():
    """An ignore rule does not untrack, and `git add -f` walks straight past it."""
    tracked = _git("ls-files", "sage/instances/*-being/*").stdout.split()
    assert tracked == [], f"being records tracked in public SAGE: {tracked[:5]}"
