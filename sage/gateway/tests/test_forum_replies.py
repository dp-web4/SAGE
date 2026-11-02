"""Replies to a being's asks reach its beat (Sprout 2026-10-18: 72 posts addressed to sprout-being,
none ever shown; 14 asks about one question in a day while each answer sat on the forum)."""
import os
import time
from pathlib import Path

import pytest

from sage.gateway import forum_replies as fr

ME = "sprout-being"
DAY = 86400


@pytest.fixture
def ws(tmp_path):
    """A workspace laid out like the fleet's: <root>/sage (workspace) beside <root>/shared-context/forum."""
    root = tmp_path / "ai"
    (root / "sage").mkdir(parents=True)
    forum = root / "shared-context" / "forum"
    forum.mkdir(parents=True)
    home = root / "sage" / "home"
    home.mkdir()
    return root / "sage", forum, home


def today(offset_days=0):
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + offset_days * DAY))


def post(forum, name, front, body="The answer.", mtime_age_s=0):
    p = forum / name
    p.write_text("---\n" + front + "\n---\n\n" + body)
    t = time.time() - mtime_age_s
    os.utime(p, (t, t))
    return p


class Turn:
    def __init__(self, n):
        self.generates = [{"done_reason": "stop"}] * n


def beat(home, workspace, turn=Turn(1), killed=None):
    """What the heartbeat does: offer, deliver (or not), acknowledge only if delivered."""
    got = fr.for_beat(home, str(workspace), ME)
    if fr.delivered(turn, killed):
        fr.acknowledge(home, got["offered"])
    return got


def test_a_reply_addressed_to_the_being_is_offered_until_delivered(ws):
    workspace, forum, home = ws
    post(forum, f"hub-re-sprout-being-video0-{today()}.md",
         f"from: hub-claude\nto: sprout-being\ndate: {today()}\nre: video0", "No device op can clear a gate record.")
    got = beat(home, workspace)
    assert got["offered"] == [f"hub-re-sprout-being-video0-{today()}.md"]
    assert "from hub-claude" in got["block"] and "No device op can clear" in got["block"]
    assert "other members' own words" in got["block"]
    assert beat(home, workspace)["block"] == "", "delivered once, then gone"


def test_an_interrupted_beat_does_not_consume_the_reply(ws):
    """NOVA on #481: marking at compose time let a crashed beat silently eat an unread answer."""
    workspace, forum, home = ws
    post(forum, f"r-{today()}.md", f"from: hub-claude\nto: sprout-being\ndate: {today()}")
    assert beat(home, workspace, killed="BeatKilled: timeout")["offered"] == [f"r-{today()}.md"]
    assert beat(home, workspace, turn=Turn(0))["offered"] == [f"r-{today()}.md"], "no model reply: not delivered"
    assert beat(home, workspace, turn=None)["offered"] == [f"r-{today()}.md"], "no turn ran: not delivered"
    assert beat(home, workspace)["offered"] == [f"r-{today()}.md"], "delivered now"
    assert beat(home, workspace)["offered"] == [], "and only once"


def test_for_beat_alone_marks_nothing(ws):
    workspace, forum, home = ws
    post(forum, f"r-{today()}.md", f"from: hub-claude\nto: sprout-being\ndate: {today()}")
    for _ in range(3):
        assert fr.for_beat(home, str(workspace), ME)["offered"] == [f"r-{today()}.md"]


def test_in_reply_to_its_ask_counts_even_without_to(ws):
    workspace, forum, home = ws
    post(forum, f"legion-re-x-{today()}.md",
         f"from: legion-claude\ndate: {today()}\nin_reply_to: forum/sprout-being-asks-legion-2026-10-18-104706.md")
    assert beat(home, workspace)["offered"] == [f"legion-re-x-{today()}.md"]


def test_peer_asks_and_its_own_posts_are_not_replies(ws):
    workspace, forum, home = ws
    post(forum, f"cbp-being-asks-sprout-being-{today()}-114351.md", "from: cbp-being\nto: sprout-being")
    post(forum, f"sprout-being-asks-hub-{today()}-111525.md", "from: sprout-being\nto: hub")
    post(forum, f"x-{today()}.md", "from: sprout-being\nto: sprout-being")
    assert beat(home, workspace)["offered"] == []


def test_a_mention_is_not_an_address(ws):
    workspace, forum, home = ws
    post(forum, f"a-{today()}.md", "from: hub-claude\nto: fleet\ntitle: about sprout-being's camera")
    post(forum, f"b-{today()}.md", "from: hub-claude\nto: sprout-being-two")
    assert beat(home, workspace)["offered"] == []


# ---- the post's own date, not the file's mtime (NOVA on #481) ----

def test_an_old_post_freshly_pulled_is_not_new(ws):
    """Written 10 days ago, pulled a second ago (mtime now): never offered."""
    workspace, forum, home = ws
    post(forum, f"old-{today(-10)}.md", f"from: hub-claude\nto: sprout-being\ndate: {today(-10)}", mtime_age_s=1)
    assert beat(home, workspace)["offered"] == []


def test_a_new_post_with_an_old_mtime_is_not_skipped(ws):
    """Written today, but its file carries a 30-day-old mtime (a copy that kept its times): offered."""
    workspace, forum, home = ws
    post(forum, f"new-{today()}.md", f"from: hub-claude\nto: sprout-being\ndate: {today()}", mtime_age_s=30 * DAY)
    assert beat(home, workspace)["offered"] == [f"new-{today()}.md"]


def test_order_is_by_authored_time_whatever_the_mtimes(ws):
    workspace, forum, home = ws
    post(forum, f"a-{today(-3)}.md", f"from: x\nto: sprout-being\ndate: {today(-3)}", mtime_age_s=0)
    post(forum, f"b-{today(-1)}.md", f"from: x\nto: sprout-being\ndate: {today(-1)}", mtime_age_s=5 * DAY)
    post(forum, f"c-{today(-2)}.md", f"from: x\nto: sprout-being\ndate: {today(-2)}", mtime_age_s=1 * DAY)
    assert beat(home, workspace)["offered"] == [f"b-{today(-1)}.md", f"c-{today(-2)}.md", f"a-{today(-3)}.md"]


def test_arrival_breaks_ties_within_a_day_only(ws):
    """Same authored day: the later arrival first. A later arrival of an OLDER day never jumps ahead."""
    workspace, forum, home = ws
    post(forum, f"early-{today()}.md", f"from: x\nto: sprout-being\ndate: {today()}", mtime_age_s=3600)
    post(forum, f"late-{today()}.md", f"from: x\nto: sprout-being\ndate: {today()}", mtime_age_s=60)
    post(forum, f"yesterday-{today(-1)}.md", f"from: x\nto: sprout-being\ndate: {today(-1)}", mtime_age_s=1)
    assert beat(home, workspace)["offered"] == [f"late-{today()}.md", f"early-{today()}.md",
                                                f"yesterday-{today(-1)}.md"]


def test_the_filename_stamp_dates_a_post_without_a_date_field(ws):
    workspace, forum, home = ws
    post(forum, f"undated-{today(-9)}.md", "from: x\nto: sprout-being", mtime_age_s=0)
    post(forum, f"stamped-{today()}-101500.md", "from: x\nto: sprout-being", mtime_age_s=20 * DAY)
    assert beat(home, workspace)["offered"] == [f"stamped-{today()}-101500.md"]


def test_the_label_names_its_source(ws):
    workspace, forum, home = ws
    post(forum, f"d-{today()}.md", f"from: x\nto: sprout-being\ndate: {today()}")
    post(forum, "nodate.md", "from: x\nto: sprout-being")
    block = beat(home, workspace)["block"]
    assert f"dated {today()}" in block and "arrived here " in block


def test_newest_first_a_few_per_beat(ws):
    workspace, forum, home = ws
    for i in range(5):
        post(forum, f"r{i}-{today()}-0{i}0000.md", "from: hub-claude\nto: sprout-being")
    first = beat(home, workspace)
    assert first["offered"] == [f"r4-{today()}-040000.md", f"r3-{today()}-030000.md", f"r2-{today()}-020000.md"]
    assert first["waiting"] == 2 and "2 more after these" in first["block"]
    assert beat(home, workspace)["offered"] == [f"r1-{today()}-010000.md", f"r0-{today()}-000000.md"]


def test_the_excerpt_is_capped_and_the_path_given(ws):
    workspace, forum, home = ws
    post(forum, f"long-{today()}.md", f"from: legion-claude\nto: sprout-being\ndate: {today()}", "word " * 500)
    block = beat(home, workspace)["block"]
    assert " …" in block and f"shared-context/forum/long-{today()}.md" in block


def test_no_forum_is_said_not_raised(tmp_path):
    got = fr.for_beat(tmp_path / "home", str(tmp_path / "sage"), ME)
    assert got["block"] == "" and got["why"]
