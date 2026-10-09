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
    # The item's own marker is "…[N more chars]" (cut()); the whole-answer marker
    # ("…[answer trimmed at") is only added by the final fallback, which this fixture does
    # not reach (head + description are under the cap, so the newest budget keeps the
    # total at or under the cap).
    pr = dict(PR, body="b" * 800,
              comments=[{"author": {"login": "new"}, "createdAt": "2026-10-05T00:00:00Z", "body": "n" * 20000}],
              reviews=[])
    out = render_pr(pr, "dp-web4/SAGE#1", last=1)
    assert len(out) <= PR_READ_TOTAL_CHARS, "the newest budget keeps the total at or under the cap"
    assert "more chars]" in out, "the newest item's own cut marker survives the cut"
    assert "n" * 20000 not in out


def test_a_short_older_item_that_fits_is_admitted_at_its_real_size():
    # The seat's seq 645 point 2: an older item is admitted by the size it will actually
    # render (header + cut body, marker included), not by the flat PR_READ_ITEM_CHARS.
    # A 300-char older item that fits after the cut is kept; the old flat-cap check
    # (base + 1 + header + 1200 > cap) dropped it even though it fit.
    pr = dict(PR,
        body="x" * 900,
        comments=[
            {"author": {"login": "gpt"}, "createdAt": "2026-10-05T10:00:00Z", "body": "y" * 300},
            {"author": {"login": "dp"}, "createdAt": "2026-10-05T11:00:00Z", "body": "z" * 5000},
        ],
    )
    out = render_pr(pr, "main")
    assert "y" * 300 in out, "the 300-char older item fits and must be admitted"
    # All 3 items (cbp review, y*300, z*1200) fit, so the count line is
    # "3 in all, newest last" (no "the last N shown" clause when total == rendered).
    assert "3 in all, newest last" in out, "the count line reports what was actually rendered"
    assert len(out) <= PR_READ_TOTAL_CHARS


def test_over_cap_answer_is_bounded_at_the_cap_with_its_marker():
    # The seat's seq 645 point 1: the final whole-answer trim must land at the cap,
    # marker included. A TITLE long enough that head + description alone exceed the cap
    # (the only case the final trim can fire: the newest budget already keeps a long
    # description or item at or under the cap); the trim keeps len(out) <= cap and adds
    # the "…[answer trimmed at" marker.
    pr = dict(PR, title="t" * 6000,
              comments=[
                  {"author": {"login": "gpt"}, "createdAt": "2026-10-05T10:00:00Z", "body": "y" * 3800},
              ],
    )
    out = render_pr(pr, "main")
    assert len(out) <= PR_READ_TOTAL_CHARS, "the final trim is bounded with its marker included"
    assert "…[answer trimmed at" in out
    assert "y" * 3800 not in out


def test_combined_over_cap_regression():
    # The seat's seq 645 point 4, one combined regression: a description near its cap,
    # a newest item long enough to be cut, at least one older item also cut, strict
    # len(out) <= cap, and both cut markers present. Red at 8cbf9e6d4 (the older item
    # was admitted at the flat 1200 cap and the count line said 8 when 2 were shown);
    # green after the real-rendered-size admission and the rendered count line.
    #
    # RULE (locked 2026-10-08, dp's #360 policy): the NEWEST item is never cut if it
    # fits the room left over the header and description; it is cut to
    # PR_READ_ITEM_CHARS (1200) only when it alone exceeds that room -- then the room
    # it frees admits OLDER items newest-to-oldest at their REAL rendered size (header
    # + cut body + marker), cut when longer, dropped when the room runs out. An OLDER
    # item is dropped rather than the newest cut. The newest here is 5000 (> the ~3900
    # room), so it is cut to 1200 and the room it frees admits the older items
    # newest-to-oldest at their real rendered size: the shared fixture's cbp review
    # (5 chars) and both 3000-char comments (cut to 1200 each). All 4 items are
    # rendered, so the count line is "4 in all, newest last".
    pr = dict(PR,
        body="x" * 900,
        comments=[
            {"author": {"login": "gpt"}, "createdAt": "2026-10-05T09:00:00Z", "body": "a" * 3000},
            {"author": {"login": "sprout"}, "createdAt": "2026-10-05T10:00:00Z", "body": "b" * 3000},
            {"author": {"login": "dp"}, "createdAt": "2026-10-05T11:00:00Z", "body": "c" * 5000},
        ],
    )
    out = render_pr(pr, "main")
    assert len(out) <= PR_READ_TOTAL_CHARS, "strict: the whole answer never exceeds the cap"
    assert "a" * 1200 in out, "the older item is cut to its real rendered size"
    assert "c" * 1200 in out, "the newest item is cut to its real rendered size"
    assert "more chars]" in out, "both cut markers are present"
    assert "4 in all, newest last" in out, "the count line reports what was actually rendered"


def test_the_newest_item_is_sized_to_the_leftover_room():
    # RULE (locked 2026-10-09, the leftover-to-the-newest follow-up to dp's #360
    # policy, confirmed by the seat): when the newest item is long enough to be cut,
    # it is cut to the room left over the header + description + the older items
    # actually rendered (marker included) -- NOT to the flat PR_READ_ITEM_CHARS (1200)
    # cap. The older items are admitted newest-to-oldest at their REAL rendered size
    # (header + cut body + marker), and pass 1 reserves 1200 for the newest so the
    # room it frees when it is cut is never spent on older items. So the newest's
    # rendered size is min(PR_READ_ITEM_CHARS, room), and when the leftover room is
    # clearly above 1200 the newest comes out cut ABOVE the flat 1200 cap.
    #
    # Fixture: the exact live shape of #360 -- an 800-char description, two 3000-char
    # older comments (each cut to 1200), and a 2111-char newest comment. The room
    # left over the header, the description, and the two older items' real rendered
    # sizes is ~1580, so the newest is cut to ~1580 -- above the flat 1200 cap it
    # would have been cut to before this fix. Red against the merged head
    # d133f7aa9 (newest_budget cut it to a flat 1200); green after the leftover fix.
    pr = dict(PR,
        body="x" * 800,
        comments=[
            {"author": {"login": "gpt"}, "createdAt": "2026-10-05T09:00:00Z", "body": "a" * 3000},
            {"author": {"login": "cbp"}, "createdAt": "2026-10-05T10:00:00Z", "body": "b" * 3000},
            {"author": {"login": "dp"}, "createdAt": "2026-10-05T11:00:00Z", "body": "z" * 5000},
        ],
    )
    out = render_pr(pr, "main")
    assert len(out) <= PR_READ_TOTAL_CHARS, "strict: the whole answer never exceeds the cap"
    assert "a" * 1200 in out, "the older item is cut to its real rendered size"
    assert "b" * 1200 in out, "the second older item is cut to its real rendered size"
    assert "z" * 5000 not in out, "the newest is cut (5000 > the leftover room), not whole"
    # The newest's rendered body is cut ABOVE the flat 1200 cap: the leftover room
    # over the header + description + the two older items is ~1580, so the newest's
    # cut body is ~1580, not 1200.
    assert "z" * 1300 in out, "the newest is cut to the leftover room (~1580), above the flat 1200 cap"
    assert "4 in all, newest last" in out, "the count line reports what was actually rendered"
