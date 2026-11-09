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


def test_the_request_framing_is_not_a_subject():
    """pub's repro on #574: with one earlier request and a short why, the words every request carries
    ([request_run], why, the directory and extension) made 'check the sky colour' the same subject as
    'test the camera'; and in a bigger record, one shared common word did."""
    turns = [{"seq": 1, "from": "b", "text": "[request_run] sandbox/cam_test.py\nwhy: test the camera\n(size 10)"}]
    assert rv.earlier_requests(turns, "b", "[request_run] sandbox/sky.py\nwhy: check the sky colour") == []
    turns = [{"seq": i, "from": "b", "text": f"[request_run] sandbox/x{i}.py\nwhy: {w}"}
             for i, w in enumerate(["check disk usage of home", "list my notes folder", "test the camera",
                                    "count journal lines", "read the law hash", "plot temperature"])]
    assert rv.earlier_requests(turns, "b", "[request_run] sandbox/sky.py\nwhy: check the sky colour") == []
    found = rv.earlier_requests(turns, "b", "[request_run] sandbox/cam2.py\nwhy: test the camera again")
    assert [f["seq"] for f in found] == [2]


def test_one_sandbox_file_reused_for_everything_is_not_one_subject():
    turns = [{"seq": 1, "from": "b", "text": "[request_run] sandbox/probe_all.py\nwhy: plot temperature"}]
    assert rv.earlier_requests(turns, "b", "[request_run] sandbox/probe_all.py\nwhy: list my notes") == []


def test_a_file_asked_about_under_many_roots_is_one_subject():
    """cbp's review of #574: cbp-being asked about one file 21 times, spelling its root four or five ways,
    each time with a new scope id. The basename is the subject."""
    roots = ["/w/hestia/governance/", "/w/governance/hestia/", "/w/hestia/hestia/governance/",
             "/h/hestia/governance/", "/w/w/hestia/governance/"]
    turns = [{"seq": i + 1, "from": "b", "text": f"[request_run] sandbox/read{i}.py\nwhy: read "
              f"{r}hestia_gate_core.py to see why it is pending"} for i, r in enumerate(roots)]
    turns += [{"seq": 10 + i, "from": "b", "text": f"[request_run] sandbox/x{i}.py\nwhy: {w}"}
              for i, w in enumerate(["check the hestia law hash", "list hestia governance files",
                                     "how many hestia scope requests today", "test the camera frame"])]
    found = rv.earlier_requests(turns, "b", "[request_run] sandbox/r6.py\nwhy: open "
                                           "/z/hestia/governance/hestia_gate_core.py")
    assert [f["seq"] for f in found] == [1, 2, 3, 4, 5]
    assert rv.ids("os.path.join(x); self.run(); v1.2.3; hestia_gate_core.py") == {"hestia_gate_core.py"}


def test_a_repeat_of_answered_bytes_filed_after_the_answer_is_answered_by_it():
    # cbp's review of #665: the seat declined these bytes at seq 2677; the repeats after it were "(not answered
    # yet)" here while the same receipt quoted the decline
    line = "[request_run] notes/x.py\nwhy: /dev/gadget7\n(10 bytes, sha256:48684f53f84a; the seat decides)"
    turns = [{"seq": 1, "from": "b", "text": line},
             {"seq": 2, "from": "seat", "text": "[request_run] I did not run notes/x.py. No.\n\nAnswers your request seq 1."},
             {"seq": 3, "from": "b", "text": line},
             {"seq": 4, "from": "b", "text": line.replace("48684f53f84a", "0123456789ab")}]
    found = rv.earlier_requests(turns, "b", "notes/y.py /dev/gadget7")
    by = {f["seq"]: f for f in found}
    assert by[3]["answer_seq"] == 2 and by[3]["repeat_of"] == 1, by[3]
    assert by[4]["answer_seq"] is None, "changed bytes are not answered by the old answer"
    said = rv.earlier_requests_said(found)
    assert "seq 3 (notes/x.py): the same bytes as seq 1, answered at seq 2: [request_run] I did not run" in said, said
    assert "declined 2" in said and "1 not answered" in said, said


def _after_a_decline_of(line, *later):
    """`line` at seq 1, declined at seq 2, then `later` from seq 3: {seq: found}."""
    turns = [{"seq": 1, "from": "b", "text": line},
             {"seq": 2, "from": "seat", "text": "[request_run] I did not run notes/x.py. No.\n\nAnswers your request seq 1."}]
    turns += [{"seq": n, "from": "b", "text": t} for n, t in enumerate(later, 3)]
    return {f["seq"]: f for f in rv.earlier_requests(turns, "b", "notes/y.py /dev/gadget7")}


_DECLINED = "[request_run] notes/x.py\nwhy: /dev/gadget7\n(10 bytes, sha256:48684f53f84a; the seat decides)"


def test_a_digest_quoted_in_why_is_not_the_requests_bytes():
    # pub's review of #666: changed bytes whose `why` cites the old digest were told "the same bytes as seq 1"
    changed = ("[request_run] notes/x.py\nwhy: /dev/gadget7 fixed since sha256:48684f53f84a\n"
               "(10 bytes, sha256:0123456789ab; the seat decides)")
    by = _after_a_decline_of(_DECLINED, changed)
    assert by[3]["answer_seq"] is None and "repeat_of" not in by[3], by[3]


def test_different_arguments_or_a_rerun_are_not_a_repeat_of_the_answered_request():
    # pub's review of #666: what ran is (path, bytes, arguments), and a rerun asks again on purpose
    by = _after_a_decline_of(_DECLINED, _DECLINED + "\nargs: --dry-run", _DECLINED + "\nrerun: true")
    assert by[3]["answer_seq"] is None and "repeat_of" not in by[3], by[3]
    assert by[4]["answer_seq"] is None and "repeat_of" not in by[4], by[4]


def test_a_rerun_answered_once_does_not_answer_the_next_rerun():
    # no key on either side: None == None must not read as the same work
    rerun = _DECLINED + "\nrerun: true"
    by = _after_a_decline_of(rerun, rerun)
    assert by[3]["answer_seq"] is None and "repeat_of" not in by[3], by[3]


def test_a_later_remark_about_the_seq_does_not_displace_its_answer():
    # cbp's review of #666: an aside naming the seq is not the answer, and must not be quoted as one
    turns = [{"seq": 1, "from": "b", "text": _DECLINED},
             {"seq": 2, "from": "seat", "text": "[request_run] I ran notes/x.py.\n\nAnswers your request seq 1."},
             {"seq": 3, "from": "seat", "text": "A note about seq 1: odd that it took so long."},
             {"seq": 4, "from": "b", "text": _DECLINED}]
    by = {f["seq"]: f for f in rv.earlier_requests(turns, "b", "notes/y.py /dev/gadget7")}
    assert by[4]["answer_seq"] == 2 and by[4]["repeat_of"] == 1, by[4]


def test_the_dispatchers_own_annotation_does_not_make_a_repeat_different_work():
    # the other direction: the line the dispatcher adds to a real repeat is not the being's argument
    by = _after_a_decline_of(_DECLINED, _DECLINED + "\nUNCHANGED since the request at seq 1; the seat answered at seq 2.")
    assert by[3]["answer_seq"] == 2 and by[3]["repeat_of"] == 1, by[3]
