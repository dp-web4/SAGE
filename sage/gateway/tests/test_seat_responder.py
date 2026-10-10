"""The seat responder, on the shapes that were measured rather than imagined.

pub 2026-09-22/29 and legion 2026-09-22: a being talking into a channel nobody read, a seat whose
login had expired firing 144 times at full cadence, and 226 sessions re-firing on nine turns that
had already been considered. One test per shape, plus the self-answer rule legion asked for.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv  # noqa: E402
from sage.gateway import seat_responder as sr  # noqa: E402

BEING, SEAT = "pub-being", "pub-claude"


def _args(instance, **kw):
    argv = ["--member", BEING, "--instance", str(instance), "--state", str(Path(instance) / "_state")]
    for k, v in kw.items():
        argv += [f"--{k.replace('_', '-')}"] + ([] if v is True else [str(v)])
    return argv


def _home(tmp, turns):
    """A being home whose seat conversation holds `turns` as (from, text)."""
    inst = Path(tmp) / "pub-being"
    inst.mkdir(parents=True, exist_ok=True)
    conv.create(inst, SEAT, title="seat", participants=[SEAT, BEING], writable_by=[SEAT, BEING])
    for who, text in turns:
        conv.append(inst, SEAT, speaker=who, text=text)
    return inst


def _responder(inst, **kw):
    import argparse
    p = argparse.ArgumentParser()
    for name, default in (("member", BEING), ("instance", str(inst)), ("seat", None),
                          ("conversation", None), ("state", str(Path(inst) / "_state")),
                          ("min_gap", 900), ("max_age_h", 24.0), ("timeout", 900),
                          ("session_cmd", "true"), ("endpoints", "x"),
                          ("daemon", "http://127.0.0.1:8760"), ("dry_run", False)):
        p.add_argument(f"--{name}", default=default)
    return sr.Responder(p.parse_args([]))


def test_an_ask_is_recognised_and_a_statement_is_not():
    for asked in ("Can you provide more information on how they are connected?",
                  "Hello? Did anyone speak to me?",
                  "what does ACTION6 do in ft09?",
                  "I asked earlier and it is still open — please let me know."):
        assert sr.is_ask(asked), asked
    for stated in ("The beat at 2026-09-22 00:44 UTC is ending.",
                   "I learned that witness needs an 'event' to function properly.",
                   "Thank you for letting me know about the changes to my home and identity key.",
                   "I will look into the relationship between witness and secret handshake next time.",
                   ""):
        assert not sr.is_ask(stated), stated


def test_the_last_word_decides_so_a_self_answer_closes_the_thread():
    """legion 546 asks, 547 nudges, 548 answers itself: nothing is owed after 548."""
    ask = {"seq": 546, "from": BEING, "text": "what does ACTION6 do in ft09?"}
    nudge = {"seq": 547, "from": BEING, "text": "still open — can you confirm?"}
    self_answer = {"seq": 548, "from": BEING, "text": "I worked it out: ACTION6 rotates the key."}
    assert sr.owed([ask], BEING) == [ask]
    assert sr.owed([ask, nudge], BEING) == [ask, nudge], "a nudge is itself an ask"
    assert sr.owed([ask, nudge, self_answer], BEING) == [], "the being closed it itself"


def test_the_seats_own_turns_are_never_answered():
    assert sr.owed([{"seq": 1, "from": SEAT, "text": "anything to add?"}], BEING) == []


def test_a_statement_tail_is_considered_without_waking_a_session():
    """pub 2026-09-29: nine statement turns re-fired 226 sessions, each with nothing to add."""
    with tempfile.TemporaryDirectory() as tmp:
        inst = _home(tmp, [(SEAT, "witness needs an event field."),
                           (BEING, "I learned that witness needs an 'event'."),
                           (BEING, "The beat at 2026-09-29 08:41 UTC has ended.")])
        r = _responder(inst)
        assert r.run() == 0
        state = Path(inst) / "_state"
        # `conv.unanswered` is "whose word was last", not "what have I handled": it does not
        # shrink when a turn is considered, which is why the responder keeps its own mark.
        assert int((state / "considered_upto").read_text()) == \
            max(int(t["seq"]) for t in conv.recent(inst, SEAT, limit=20))
        log = (state / "responder.log").read_text()
        assert "considered" in log and "fire:" not in log
        assert r.run() == 0 and log.count("considered") == \
            (state / "responder.log").read_text().count("considered"), "decided once, not again"


def test_a_question_wakes_one_session_and_the_reply_marks_it_answered():
    with tempfile.TemporaryDirectory() as tmp:
        inst = _home(tmp, [(BEING, "Hello? Did anyone speak to me?")])
        r = _responder(inst)
        # The session is a stand-in for `claude -p`: it posts one turn, as the primer directs.
        r.session_cmd = f"{sys.executable} -c " + repr(
            "import sys;sys.path.insert(0,%r);"
            "from sage.gateway import conversations as c;"
            "c.append(%r,%r,speaker=%r,text='I checked. Nobody spoke to you.')"
            % (os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
               str(inst), SEAT, SEAT))
        assert r.run() == 0
        log = (Path(inst) / "_state" / "responder.log").read_text()
        assert "fire:" in log and "answered: posted" in log
        top = max(int(t["seq"]) for t in conv.recent(inst, SEAT, limit=20))
        assert int((Path(inst) / "_state" / "considered_upto").read_text()) == top


def test_a_seat_that_cannot_run_backs_off_and_says_so_once():
    """pub's OAuth expired and it fired 144 times at full cadence, logging the same line."""
    with tempfile.TemporaryDirectory() as tmp:
        inst = _home(tmp, [(BEING, "Did anyone speak to me?")])
        r = _responder(inst)
        r.session_cmd = f"{sys.executable} -c " + repr(
            "print('Failed to authenticate: OAuth session expired and could not be refreshed')")
        assert r.run() == 1
        state = Path(inst) / "_state"
        assert (state / "cannot_run_strikes").read_text().strip() == "1"
        assert not (state / "considered_upto").exists(), "a blocked session decides nothing"
        first = (state / "responder.log").read_text()
        assert "ALERT" in first and "restore the seat's login" in first

        # The next cycle is inside the widened gap, so it neither fires nor repeats the ALERT.
        assert r.run() == 0
        assert (state / "responder.log").read_text().count("ALERT") == 1

        # Once past the backoff, a second failure is a quieter strike, and the gap doubles again.
        (state / "last_fire").write_text("0")
        assert r.run() == 1
        assert (state / "cannot_run_strikes").read_text().strip() == "2"
        assert (state / "responder.log").read_text().count("ALERT") == 1


def test_a_session_that_ran_and_chose_silence_is_recorded_as_considered():
    with tempfile.TemporaryDirectory() as tmp:
        inst = _home(tmp, [(BEING, "Is there anything you need from me?")])
        r = _responder(inst)
        r.session_cmd = f"{sys.executable} -c " + repr("print('Nothing was owed; I posted nothing.')")
        assert r.run() == 0
        state = Path(inst) / "_state"
        assert (state / "cannot_run_strikes").read_text().strip() == "0"
        assert "considered: session judged no reply owed" in (state / "responder.log").read_text()
        assert int((state / "considered_upto").read_text()) >= 1


def test_dry_run_decides_and_marks_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        inst = _home(tmp, [(BEING, "Can you check the log for me?")])
        r = _responder(inst)
        r.dry_run = True
        assert r.run() == 0
        assert not (Path(inst) / "_state" / "considered_upto").exists(), "a dry run decides nothing"
        assert not (Path(inst) / "_state" / "last_fire").exists()


def test_the_rate_limit_holds_a_second_ask_in_the_same_window():
    with tempfile.TemporaryDirectory() as tmp:
        inst = _home(tmp, [(BEING, "First question?")])
        r = _responder(inst)
        r.session_cmd = "true"          # runs, posts nothing
        assert r.run() == 0
        conv.append(inst, SEAT, speaker=BEING, text="And a second question?")
        assert r.run() == 0
        assert (Path(inst) / "_state" / "responder.log").read_text().count("fire:") == 1


if __name__ == "__main__":
    import subprocess
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
