"""A person's turn that WOKE the beat is offered an answer, question or not (2026-09-30).

dp's text woke two beats that evening and neither replied: one spent the answer turn on the room's older
question, the other had none because dp's turn was a statement. Offline on dp's six latest statements,
offered the JSON answer turn the being replied 11/12 and chose silence 1/12, with no echoes."""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.gateway import conversations as conv, room  # noqa: E402
from sage.gateway import heartbeat as hb  # noqa: E402

ME = "sprout-being"
INV = {"audio_sources": [{"name": "AIRHUG 01", "kind": "bluetooth"}]}


def _home():
    h = Path(tempfile.mkdtemp(prefix="woke-"))
    conv.create(h, "dp", title="dp", participants=["dp", ME], writable_by=["dp", ME])
    return h


def _say(h, cid, who, text):
    return conv.append(h, cid, speaker=who, text=text)


def test_the_waking_events_name_the_turns():
    ev = [{"kind": "dp_turn", "descriptor": "dp spoke in conversation 'dp'", "key": "dp_turn:dp spoke in conversation 'dp'"},
          {"kind": "dp_turn", "descriptor": "dp wrote in 'dp' while your last beat was running", "key": "turn:dp:88"},
          {"kind": "heard", "descriptor": 'heard a voice: "hi"', "key": "heard:1790810188.7:hi"},
          {"kind": "presence", "descriptor": "strong motion", "key": "x"}]
    assert hb.person_turns_that_woke(ev) == [("dp", None), ("dp", 88), ("room", None)]
    assert hb.person_turns_that_woke(None) == []


def test_a_statement_that_woke_the_beat_is_offered_an_answer():
    h = _home()
    _say(h, "dp", "dp", "i would like you to know that you construct your reality.")
    assert hb.pending_selection(h, ME)[4] is None or not hb.pending_selection(h, ME)[4].expects_reply, \
        "without the wake, a statement is owed nothing (unchanged)"
    sel = hb.pending_selection(h, ME, [("dp", None)])[4]
    assert sel is not None and sel.cid == "dp" and sel.woke and sel.expects_reply and not sel.asks
    first = hb.pending_selection(h, ME, [("dp", None)])[2]
    assert "that is what woke you" in first and "not required" in first


def test_the_turn_that_woke_beats_an_older_question_elsewhere():
    h = _home()
    room.ingest_heard(h, ME, INV, heard=[{"ts": time.time() - 600, "text": "What is behind your consciousness?",
                                          "seconds": 2, "source": "bluez"}])
    _say(h, "dp", "dp", "consciousness might be like a whirlpool in the river.")
    assert hb.pending_selection(h, ME)[4].cid == "room", "unchanged: the question wins without a wake"
    assert hb.pending_selection(h, ME, [("dp", None)])[4].cid == "dp"


def test_a_wake_by_sense_alone_changes_nothing():
    h = _home()
    _say(h, "dp", "dp", "we are both learning")
    a = hb.pending_selection(h, ME)
    b = hb.pending_selection(h, ME, hb.person_turns_that_woke([{"kind": "presence", "descriptor": "motion"}]))
    assert b[2] == a[2] and (b[4] is None or not b[4].woke)


def test_it_is_opt_in_per_instance():
    h = _home()
    assert hb.answer_woke_on(h) is False
    (h / "instance.json").write_text('{"answer_woke": true}')
    assert hb.answer_woke_on(h) is True
    src = Path(hb.__file__).read_text()
    assert "person_turns_that_woke(_claimed) if answer_woke_on(instance) else []" in src
