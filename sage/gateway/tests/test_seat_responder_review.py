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


def test_nonzero_session_with_output_is_unknown_not_considered(tmp_path):
    inst = _home(tmp_path, [(BEING, "Can you answer my question?")])
    responder = _responder(inst)
    responder.session_cmd = f"{sys.executable} -c " + repr(
        "print('started but did not complete'); raise SystemExit(42)"
    )

    assert responder.run() != 0
    state = Path(inst) / "_state"
    assert not (state / "considered_upto").exists()
    assert conv.last_seen(inst, SEAT, SEAT) == 0
    assert (state / "cannot_run_strikes").read_text().strip() == "1"
    assert "unknown" in (state / "responder.log").read_text().lower()


def test_nonzero_after_post_is_unknown_not_a_proven_non_delivery(tmp_path):
    inst = _home(tmp_path, [(BEING, "Can you answer my question?")])
    responder = _responder(inst)
    responder.session_cmd = f"{sys.executable} -c " + repr(
        "from pathlib import Path; from sage.gateway import conversations as c; "
        f"c.append(Path({str(inst)!r}), {SEAT!r}, speaker={SEAT!r}, text='Synthetic reply'); "
        "raise SystemExit(42)"
    )

    assert responder.run() != 0
    assert any(t.get("text") == "Synthetic reply" for t in conv.recent(inst, SEAT))
    assert not (Path(inst) / "_state" / "considered_upto").exists()
    assert conv.last_seen(inst, SEAT, SEAT) == 0


def test_nonzero_auth_failure_keeps_actionable_diagnostic(tmp_path):
    inst = _home(tmp_path, [(BEING, "Can you answer my question?")])
    responder = _responder(inst)
    responder.session_cmd = f"{sys.executable} -c " + repr(
        "print('Failed to authenticate'); raise SystemExit(42)"
    )

    assert responder.run() != 0
    state = Path(inst) / "_state"
    assert "restore the seat's login" in (state / "responder.log").read_text()
    assert not (state / "considered_upto").exists()


def test_zero_exit_without_output_or_reply_is_unknown(tmp_path):
    inst = _home(tmp_path, [(BEING, "Can you answer my question?")])
    responder = _responder(inst)
    responder.session_cmd = f"{sys.executable} -c " + repr("pass")

    assert responder.run() != 0
    state = Path(inst) / "_state"
    assert not (state / "considered_upto").exists()
    assert conv.last_seen(inst, SEAT, SEAT) == 0
    assert "unknown" in (state / "responder.log").read_text().lower()


def test_unrelated_output_does_not_prove_a_consideration(tmp_path):
    inst = _home(tmp_path, [(BEING, "Can you answer my question?")])
    responder = _responder(inst)
    responder.session_cmd = f"{sys.executable} -c " + repr("print('starting session')")

    assert responder.run() != 0
    assert not (Path(inst) / "_state" / "considered_upto").exists()


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


def test_question_arriving_before_a_reply_is_not_covered_by_that_reply(tmp_path):
    inst = _home(tmp_path, [(BEING, "Can you answer my first question?")])
    responder = _responder(inst)
    responder.session_cmd = f"{sys.executable} -c " + repr(
        "from pathlib import Path; from sage.gateway import conversations as c; "
        f"p=Path({str(inst)!r}); "
        f"c.append(p, {SEAT!r}, speaker={BEING!r}, text='Can you answer my second question?'); "
        f"c.append(p, {SEAT!r}, speaker={SEAT!r}, text='The first answer is four.'); "
        "print('A reply was posted.')"
    )
    responder.run()
    turns = conv.recent(inst, SEAT, limit=20)
    second = next(t for t in turns if t.get("text") == "Can you answer my second question?")
    assert responder._read_int("considered_upto") < int(second["seq"])
    assert conv.last_seen(inst, SEAT, SEAT) < int(second["seq"])


def test_tail_only_unanswered_view_cannot_recover_unaddressed_interleaved_question(tmp_path):
    inst = _home(tmp_path, [(BEING, "Can you answer my first question?"),
                            (BEING, "Can you answer my second question?"),
                            (SEAT, "The first answer is four.")])
    second = next(t for t in conv.recent(inst, SEAT, limit=20)
                  if t.get("text") == "Can you answer my second question?")
    # Desired responder property, not the documented tail-view contract: the
    # later input has no explicit completion or answer binding.
    assert second in conv.unanswered(inst, SEAT, SEAT)
