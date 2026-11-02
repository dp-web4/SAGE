"""Synthetic regressions for the held responder, not a live-session test.

These are intentionally failing specifications against PR #278's original head.
"""

import sys
from pathlib import Path

from sage.gateway import conversations as conv
from sage.gateway.tests.test_seat_responder import BEING, SEAT, _home, _responder


def test_failed_empty_session_does_not_mark_question_handled(tmp_path):
    inst = _home(tmp_path, [(BEING, "Can you answer my question?")])
    responder = _responder(inst)
    responder.session_cmd = f"{sys.executable} -c " + repr("raise SystemExit(42)")

    result = responder.run()
    state = Path(inst) / "_state" / "considered_upto"
    assert (result != 0, state.exists(), conv.last_seen(inst, SEAT, SEAT)) == (True, False, 0)


def test_question_arriving_during_session_is_not_marked_handled(tmp_path):
    inst = _home(tmp_path, [(BEING, "Can you answer my first question?")])
    responder = _responder(inst)
    responder.session_cmd = f"{sys.executable} -c " + repr(
        "from pathlib import Path; from sage.gateway import conversations as c; "
        f"c.append(Path({str(inst)!r}), {SEAT!r}, speaker={BEING!r}, "
        "text='Can you answer my second question?'); "
        "print('No reply was posted.')"
    )

    responder.run()
    new_question = conv.recent(inst, SEAT, limit=20)[-1]
    considered = responder._read_int("considered_upto")
    assert considered < int(new_question["seq"])
    assert conv.last_seen(inst, SEAT, SEAT) < int(new_question["seq"])


def test_unrelated_statement_does_not_cancel_an_earlier_question(tmp_path):
    inst = _home(tmp_path, [(BEING, "Can you answer my question?"),
                            (BEING, "My current beat has ended.")])
    responder = _responder(inst)
    pending = conv.unanswered(inst, SEAT, SEAT)

    assert pending
    responder.run()
    assert not (Path(inst) / "_state" / "considered_upto").exists(), (
        "an unrelated statement is not evidence of a self-answer"
    )
