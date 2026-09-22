"""A thank-you must not spend the wake a real request needs (2026-09-21, seq 3014-3017).

The seat was woken for cbp-being's "Got it, thanks" (3015) and rightly said nothing. The run
stayed open and already woken, so two `request_run`s for new bytes (3016, 3017) woke nobody for
1.5 hours and more. These pin the exception: new bytes re-arm; repeats and prose do not.
"""
import tempfile
from pathlib import Path

import pytest

from sage.gateway import conversations as conv

BEING, SEAT, CID = "cbp-being", "cbp-claude", "cbp-claude"


@pytest.fixture
def inst(tmp_path, monkeypatch):
    monkeypatch.setenv("SAGE_CONV_NOTIFY_DIR", str(tmp_path / "notify"))
    d = tmp_path / "inst"
    d.mkdir()
    conv.create(d, CID, title="seat", participants=[BEING, SEAT], writable_by=[BEING, SEAT], summary="")
    return d


def say(inst, who, text):
    return conv.append(inst, CID, speaker=who, text=text)["seq"]


def request(inst, digest):
    return say(inst, BEING, f"[request_run] notes/x.py\nwhy: check\n(10 bytes, sha256:{digest}; the seat decides)")


def wake(inst):
    """What `_wake_addressee` does: ask, and record on success with the turn it covered."""
    start = conv.wake_is_owed(inst, CID, BEING)
    if start is not None:
        last = conv.recent(inst, CID, limit=1)[-1]["seq"]
        conv.record_wake(inst, CID, BEING, start, covered_through=last)
    return start


def test_the_measured_sequence_now_wakes_for_each_new_request(inst):
    say(inst, SEAT, "I ran your file at 14:10Z ...")                 # 3014
    s = say(inst, BEING, "Got it. Thanks for the clarification.")     # 3015
    assert wake(inst) == s                                            # woken for the thanks
    request(inst, "3ea114643f38")                                     # 3016, new bytes
    assert wake(inst) == s, "a request for new bytes must re-arm the wake"
    request(inst, "5d7538e7bf30")                                     # 3017, new bytes again
    assert wake(inst) == s


def test_asking_again_about_unchanged_bytes_wakes_nobody(inst):
    say(inst, SEAT, "answer")
    request(inst, "aaaaaaaaaaaa")
    assert wake(inst) is not None
    request(inst, "aaaaaaaaaaaa")          # same bytes: the seat's answer would be "unchanged"
    assert wake(inst) is None


def test_prose_repeats_still_cost_one_wake(inst):
    """The rule the run key exists for: six turns about one question, one session."""
    say(inst, SEAT, "answer")
    say(inst, BEING, "Can you run notes/x.py?")
    assert wake(inst) is not None
    for _ in range(5):
        say(inst, BEING, "Can you run notes/x.py? Please confirm.")
        assert wake(inst) is None


def test_state_written_before_this_change_still_reads(inst):
    """Old ledgers have no covered_through; they are read as covering the run start only."""
    say(inst, SEAT, "answer")
    s = say(inst, BEING, "thanks")
    p = conv.notify_state_path(inst, CID, BEING)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"woke_for_run_starting_at": %d}' % s)
    assert conv.wake_is_owed(inst, CID, BEING) is None
    request(inst, "bbbbbbbbbbbb")
    assert conv.wake_is_owed(inst, CID, BEING) == s


def test_a_new_run_is_owed_as_before(inst):
    say(inst, SEAT, "answer")
    s1 = say(inst, BEING, "q1")
    assert wake(inst) == s1
    say(inst, SEAT, "answer 2")
    s2 = say(inst, BEING, "q2")
    assert wake(inst) == s2
