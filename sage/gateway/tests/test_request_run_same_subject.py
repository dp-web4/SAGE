"""request_run: the receipt says what was asked before on the same subject, how it was answered, and what the
being settled about it (dp, 2026-10-27: "so it can learn conclusively and not perseverate"). Measured on
sprout-being 10-14..27: 612 of 1,010 requests were about one device, across 86 different files."""
from pathlib import Path

from sage.gateway import being_settled as st
from sage.gateway import conversations as conv
from sage.gateway import relevance as rv
from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_hestia_dispatch import _ALLOW, _disp


def _seat_home():
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    (home / "notes").mkdir(exist_ok=True)
    return d, home


def _ask(d, home, name, why, body="print('a')\n"):
    (home / "notes" / name).write_text(body)
    return d(BeingIntent("request_run", {"path": f"notes/{name}", "why": why}), _ALLOW)


def _answer(home, text):
    asked = conv.recent(home, "seat", limit=1)[-1]["seq"]
    conv.append(home, "seat", speaker="seat", via="seat", text=f"{text}\n\nAnswers your request seq {asked}.")


def test_a_new_file_on_an_old_subject_is_told_the_history_and_its_answers():
    d, home = _seat_home()
    r = _ask(d, home, "probe_a.py", "check whether the test gadget at /dev/gadget7 answers")
    assert r.ok and "earlier_on_this" not in r.result
    _answer(home, "[request_run] I ran notes/probe_a.py (sha x) with no arguments. exit code 1.")
    _ask(d, home, "probe_b.py", "see if /dev/gadget7 responds now")
    _answer(home, "[request_run] I did not run notes/probe_b.py (sha y).")
    r = _ask(d, home, "probe_c.py", "a third way to reach it", body="open('/dev/gadget7')\n")
    said = r.result["earlier_on_this"]
    assert "2 times before" in said and "2 different files" in said, said
    assert "the seat ran 1" in said and "declined 1" in said
    assert "probe_a.py" in said and "exit code 1" in said


def test_an_unrelated_request_hears_nothing_about_other_subjects():
    d, home = _seat_home()
    _ask(d, home, "probe_a.py", "check whether the test gadget at /dev/gadget7 answers")
    r = _ask(d, home, "plot.py", "draw a chart of yesterday's temperature readings")
    assert "earlier_on_this" not in r.result and "you_settled" not in r.result


def test_what_the_being_settled_on_the_subject_comes_back_with_the_receipt():
    d, home = _seat_home()
    st.settle(home, {"question": "can I reach /dev/gadget7 directly?", "answer": "a test answer"})
    st.settle(home, {"question": "what colour is the test sky?", "answer": "unrelated"})
    r = _ask(d, home, "probe_a.py", "open /dev/gadget7 one more time")
    assert "a test answer" in r.result["you_settled"] and "unrelated" not in r.result["you_settled"]


def test_a_long_history_with_nothing_settled_names_settle_once():
    d, home = _seat_home()
    for i in range(5):
        _ask(d, home, f"probe_{i}.py", "check the test gadget at /dev/gadget7")
    r = _ask(d, home, "probe_5.py", "check the test gadget at /dev/gadget7")
    assert r.result["earlier_on_this"].count("settle keeps it") == 1


def test_one_answer_covers_the_copies_of_a_repeated_request():
    # the seat answers a repeated request once, naming one seq; the earlier copies are not "unanswered"
    turns = [{"seq": 1, "from": "b", "text": "[request_run] notes/x.py\nwhy: /dev/gadget7"},
             {"seq": 2, "from": "b", "text": "[request_run] notes/x.py\nwhy: /dev/gadget7"},
             {"seq": 3, "from": "seat", "text": "[request_run] I ran notes/x.py. exit code 0.\n\nAnswers your request seq 2."}]
    found = rv.earlier_requests(turns, "b", "notes/y.py /dev/gadget7")
    assert [f["answer_seq"] for f in found] == [3, 3]
    assert "not answered" not in rv.earlier_requests_said(found)


def test_dev_null_is_plumbing_not_a_subject():
    """legion's repro on #574: two unrelated scripts that both silence errors scored 1.0 as one subject."""
    assert rv.ids("2>/dev/null; cat /dev/urandom > /dev/stdout; ls /dev/shm") == set()
    assert rv.ids("ffmpeg -i /dev/video0 2>/dev/null") == {"/dev/video0"}
    score, shared = rv.Ranker(["[request_run] scripts/plot.py\nwhy: draw my temperature log, "
                               "silence errors to /dev/null"]).score(
        "[request_run] scripts/cam.py\nwhy: test camera\n/dev/null /dev/video0", 0)
    assert "/dev/null" not in shared and score < 1.0
