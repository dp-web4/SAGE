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


# ---------------------------------------------------------------------------------------------
# answered_run_wake "skip" (per-instance; recut of SAGE #154). A request the seat has ALREADY
# ANSWERED, for the same path, bytes and arguments, owes no wake even when it opens a new run.
# The answer must be bound to the request (GPT's hold on #154), never "someone spoke since".

def ran(inst, seq, digest="aaaaaaaaaaaa"):
    return say(inst, SEAT, f"[request_run] I ran notes/x.py (sha {digest}) with no arguments, "
                           f"in a sandbox. exit code 1.\n\nstderr:\nboom\n\nAnswers your request seq {seq}.")


def test_default_still_wakes_for_an_answered_repeat(inst):
    """The default is unchanged: this is what every instance without the key keeps."""
    a = request(inst, "aaaaaaaaaaaa")
    assert wake(inst) == a
    ran(inst, a)
    b = request(inst, "aaaaaaaaaaaa")
    assert conv.wake_is_owed(inst, CID, BEING) == b
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=False) == b


def test_skip_answered_owes_no_wake_for_a_repeat_the_seat_ran(inst):
    a = request(inst, "aaaaaaaaaaaa")
    assert wake(inst) == a
    ran(inst, a)
    request(inst, "aaaaaaaaaaaa")
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) is None
    # ...and a third identical ask in the same run still owes nothing
    request(inst, "aaaaaaaaaaaa")
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) is None


def test_skip_answered_counts_a_decline_as_the_answer(inst):
    a = request(inst, "aaaaaaaaaaaa")
    wake(inst)
    say(inst, SEAT, f"[request_run] I did not run notes/x.py. The sha is unchanged.\n\n"
                    f"Answers your request seq {a}.")
    request(inst, "aaaaaaaaaaaa")
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) is None


def test_an_unrelated_seat_message_is_not_the_answer(inst):
    """GPT's control on #154: request A -> unrelated seat message -> same-byte A must still
    wake. Only a turn naming A's seq, or a run/decline result for the same file, answers it."""
    a = request(inst, "aaaaaaaaaaaa")
    wake(inst)
    say(inst, SEAT, "Unrelated: the hub was restarted at 10:00Z.")
    b = request(inst, "aaaaaaaaaaaa")
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) == b
    # a result for ANOTHER file is not an answer either
    wake(inst)
    say(inst, SEAT, "[request_run] I ran notes/other.py (sha aaaaaaaaaaaa). exit code 0.")
    c = request(inst, "aaaaaaaaaaaa")
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) == c


def test_new_bytes_new_arguments_rerun_and_prose_still_wake(inst):
    a = request(inst, "aaaaaaaaaaaa")
    wake(inst)
    ran(inst, a)
    # changed bytes: new work
    b = request(inst, "bbbbbbbbbbbb")
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) == b
    wake(inst)
    ran(inst, b, "bbbbbbbbbbbb")
    # same bytes, different arguments: new work
    c = say(inst, BEING, "[request_run] notes/x.py\nwhy: check\n(10 bytes, sha256:bbbbbbbbbbbb; "
                         "the seat decides)\nargs: --epochs 3")
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) == c
    wake(inst)
    say(inst, SEAT, f"[request_run] I ran notes/x.py (sha bbbbbbbbbbbb) with --epochs 3. exit 0.\n\n"
                    f"Answers your request seq {c}.")
    # an explicit rerun always wakes
    d = say(inst, BEING, "[request_run] notes/x.py\nwhy: again\n(10 bytes, sha256:bbbbbbbbbbbb; "
                         "the seat decides)\nrerun: true")
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) == d
    wake(inst)
    say(inst, SEAT, f"[request_run] I ran notes/x.py (sha bbbbbbbbbbbb). exit 0.\n\n"
                    f"Answers your request seq {d}.")
    # a skipped repeat followed by prose in the same run: the prose is new mail
    e = request(inst, "bbbbbbbbbbbb")
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) is None
    say(inst, BEING, "Why does it still fail at line 12?")
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) == e


def test_a_result_naming_only_older_requests_does_not_answer_a_newer_one(inst):
    """seat_run_requests.pending()'s exception, kept here: a decline of an older seq as
    superseded must not close the newer request it was superseded by."""
    a = request(inst, "aaaaaaaaaaaa")
    wake(inst)
    b = request(inst, "aaaaaaaaaaaa")   # same run, same bytes
    say(inst, SEAT, f"[request_run] I did not run notes/x.py. Superseded.\n\nAnswers your request seq {a - 1}.")
    c = request(inst, "aaaaaaaaaaaa")
    # b is an identical request that was never named; but a (also identical) was asked before
    # the result and the result names only an older seq, so neither counts as answered
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) == c, (a, b, c)


def test_a_result_for_other_bytes_does_not_answer_these(inst):
    a = request(inst, "aaaaaaaaaaaa")
    wake(inst)
    say(inst, SEAT, "[request_run] I ran notes/x.py (sha cccccccccccc). exit code 0.")
    b = request(inst, "aaaaaaaaaaaa")
    assert conv.wake_is_owed(inst, CID, BEING, skip_answered=True) == b, a
