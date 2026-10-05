"""pr_read: a being can READ any fleet pull request (2026-09-29, dp: "give it pr_read, to any pr").

legion-being on its own #259: told "check gpt's comments on the pr, it's close", it answered that
it had no way to see them, and would not pretend it had. It could open, revise and review a PR,
and not read one.
"""
import json
import os
import types

import pytest

from sage.gateway.being_gate_client import (_CONSEQUENTIAL, _REGISTRY, _TOOL_SCHEMAS, BeingIntent,
                                            pr_read_command)
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher as D, render_pr, PR_READ_TOTAL_CHARS
from sage.gateway.heartbeat import EXPLORE_TOOLS


def test_the_composer_reads_any_fleet_pr_and_nothing_else():
    assert pr_read_command({"number": 259}, {}).startswith("gh pr view 259 --repo dp-web4/SAGE --json ")
    assert " --repo dp-web4/hestia " in pr_read_command({"number": "#1143", "repo": "dp-web4/hestia"}, {})
    for bad, why in (({"number": "abc"}, "PR number"), ({}, "PR number"),
                     ({"number": 1, "repo": "someone/else"}, "dp-web4/<name>"),
                     ({"number": 1, "repo": "dp-web4/x; rm -rf ~"}, "dp-web4/<name>"),
                     ({"number": 1, "last": 0}, "between 1 and"), ({"number": 1, "last": "x"}, "whole number")):
        with pytest.raises(ValueError, match=why):
            pr_read_command(bad, {})


def test_every_being_is_offered_it_and_the_law_judges_it():
    assert _REGISTRY["pr_read"]["compose"] is pr_read_command
    assert "pr_read" in _CONSEQUENTIAL, "it runs a seat-side subprocess, judged under mrh.command"
    assert "pr_read" in _TOOL_SCHEMAS
    assert "pr_read" in EXPLORE_TOOLS, "fleet-wide: in the base offer, not behind a worktree"


PR = {"number": 259, "title": "memory_read: name a worktree file", "state": "OPEN", "isDraft": False,
      "author": {"login": "dp-web4"}, "headRefName": "legion-being/x", "baseRefName": "main",
      "mergeable": "MERGEABLE", "reviewDecision": "", "url": "https://github.com/dp-web4/SAGE/pull/259",
      "body": "what changed",
      "comments": [{"author": {"login": "gpt"}, "createdAt": "2026-09-29T02:00:00Z", "body": "second"},
                   {"author": {"login": "sprout"}, "createdAt": "2026-09-29T01:00:00Z", "body": "first"}],
      "reviews": [{"author": {"login": "cbp"}, "submittedAt": "2026-09-29T03:00:00Z",
                   "state": "CHANGES_REQUESTED", "body": "third"}]}


def _disp(tmp_path, monkeypatch, payload, rc=0):
    bindir = tmp_path / "bin"; bindir.mkdir()
    (tmp_path / "pr.json").write_text(json.dumps(payload))
    (bindir / "gh").write_text(f"#!/bin/sh\necho \"$@\" > {tmp_path}/gh.args\n"
                               f"cat {tmp_path}/pr.json\nexit {rc}\n")
    os.chmod(bindir / "gh", 0o755)
    monkeypatch.setenv("PATH", f"{bindir}:{os.getenv('PATH')}")
    d = D.__new__(D)
    d.plugin_id = d.member = "legion-being"; d.worktree = None; d.memory_root = str(tmp_path)
    calls = []
    d._call = lambda name, args: calls.append((name, args)) or {"actionId": "w1"}
    return d, calls


def test_the_dispatcher_reads_renders_and_witnesses(tmp_path, monkeypatch):
    d, calls = _disp(tmp_path, monkeypatch, PR)
    env = d._do_pr_read(BeingIntent("pr_read", {"number": 259}))
    assert env.ok, env.error
    assert env.witness_id == "w1" and calls[0] == ("hestia_begin_action",
                                                    {"tool_name": "pr_read", "target": "dp-web4/SAGE#259"})
    out = env.result
    assert "memory_read: name a worktree file" in out and "what changed" in out
    # merged in TIME order, newest last, each attributed
    assert out.index("first") < out.index("second") < out.index("third")
    assert "comment by sprout" in out and "review by cbp (CHANGES_REQUESTED)" in out
    assert "view 259 --repo dp-web4/SAGE --json" in (tmp_path / "gh.args").read_text()


def test_a_judged_command_that_differs_is_refused_and_nothing_runs(tmp_path, monkeypatch):
    d, calls = _disp(tmp_path, monkeypatch, PR)
    d._verdict = types.SimpleNamespace(command="gh pr view 1 --repo dp-web4/other --json x")
    env = d._do_pr_read(BeingIntent("pr_read", {"number": 259}))
    assert not env.ok and "not the command this dispatcher would execute" in env.error
    assert not (tmp_path / "gh.args").exists() and not calls


def test_a_failed_read_says_so(tmp_path, monkeypatch):
    d, calls = _disp(tmp_path, monkeypatch, {"x": 1}, rc=1)
    env = d._do_pr_read(BeingIntent("pr_read", {"number": 999}))
    assert not env.ok and "could not read dp-web4/SAGE#999" in env.error
    assert calls[-1][1]["success"] is False


def test_a_long_thread_is_bounded_and_the_cut_is_said():
    many = dict(PR, body="b" * 5000,
                comments=[{"author": {"login": f"p{i}"}, "createdAt": f"2026-09-29T{i:02d}:00:00Z",
                           "body": "c" * 3000} for i in range(20)], reviews=[])
    out = render_pr(many, "dp-web4/SAGE#1", last=12)
    assert len(out) <= PR_READ_TOTAL_CHARS + 200
    # 12 were asked for; at 3000 chars each only the newest few fit, and the header says how many
    assert "20 in all, the last " in out and " shown, newest last" in out
    assert "more chars]" in out, "a trimmed body or comment must say it was trimmed"
    assert "p19" in out and "p0 " not in out, "the NEWEST are the ones kept"
    assert "(none yet)" in render_pr(dict(PR, comments=[], reviews=[]), "dp-web4/SAGE#2")


def test_the_newest_item_gets_the_leftover_budget():
    # two items, both long: the older is cut at the flat 1200, the newest gets the room the
    # 5000-char total cap leaves over, and the whole answer stays bounded
    pr = dict(PR, body="b" * 100,
              comments=[{"author": {"login": "old"}, "createdAt": "2026-10-04T00:00:00Z", "body": "o" * 3000},
                        {"author": {"login": "new"}, "createdAt": "2026-10-05T00:00:00Z", "body": "n" * 3000}],
              reviews=[])
    out = render_pr(pr, "dp-web4/SAGE#1", last=2)
    assert len(out) <= PR_READ_TOTAL_CHARS + 200
    assert "n" * 3000 in out, "the newest item is kept whole when the cap has room"
    assert "o" * 1200 in out and "o" * 1201 not in out, "the older item stays at the flat cut"
    assert "more chars]" in out, "the older cut is still said"


def test_the_live_shape_keeps_the_newest_whole():
    # the shape of #360's live payload: an 800-char description, two older items at 1200+
    # each, and a 2111-char newest. The newest must come out whole, not cut at 1200.
    pr = dict(PR, body="b" * 800,
              comments=[{"author": {"login": "old2"}, "createdAt": "2026-10-03T00:00:00Z", "body": "a" * 1500},
                        {"author": {"login": "old1"}, "createdAt": "2026-10-04T00:00:00Z", "body": "b" * 1500},
                        {"author": {"login": "new"}, "createdAt": "2026-10-05T00:00:00Z", "body": "n" * 2111}],
              reviews=[])
    out = render_pr(pr, "dp-web4/SAGE#1", last=3)
    assert len(out) <= PR_READ_TOTAL_CHARS + 200
    assert "n" * 2111 in out, "the newest 2111-char item is kept whole"
    # desc 800 + newest 2111 + two older at 1200 each = 5311 > 5000, so one older item is
    # DROPPED rather than the newest cut: the newer older item (b) stays at the flat cut,
    # the older one (a) is the one that goes
    assert "b" * 1200 in out, "the newer older item stays at the flat cut"
    assert "a" * 1200 not in out, "the older item is dropped, not the newest cut"
    assert out.count("--- ") == 2, "newest + one older item shown"
    assert "more chars]" in out, "every cut is still said"


def test_a_newest_longer_than_the_room_stays_bounded_and_says_so():
    # a newest item longer than the room the cap leaves: it is cut to the room, the answer
    # stays under the total cap, and the item's own cut marker survives (the regression the
    # seat named: the old code's tail trim dropped the marker, leaving 5032 chars).
    pr = dict(PR, body="b" * 800,
              comments=[{"author": {"login": "new"}, "createdAt": "2026-10-05T00:00:00Z", "body": "n" * 20000}],
              reviews=[])
    out = render_pr(pr, "dp-web4/SAGE#1", last=1)
    assert len(out) <= PR_READ_TOTAL_CHARS + 200
    assert "more chars]" in out, "the newest item's own cut marker survives the over-cap path"
    assert "n" * 20000 not in out
