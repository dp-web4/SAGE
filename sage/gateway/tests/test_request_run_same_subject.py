"""request_run: the receipt says what was asked before on the same subject, how it was answered, and what the
being settled about it (dp, 2026-10-27: "so it can learn conclusively and not perseverate"). Measured on
sprout-being 10-14..27: 612 of 1,010 requests were about one device, across 86 different files."""
import importlib.util
from pathlib import Path

from sage.gateway import being_settled as st
from sage.gateway import conversations as conv
from sage.gateway import relevance as rv
from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_hestia_dispatch import _ALLOW, _disp

_spec = importlib.util.spec_from_file_location(
    "seat_run_requests", Path(__file__).resolve().parents[2] / "scripts" / "seat_run_requests.py")
srr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srr)


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
    assert "2 answered by 2 seat replies: ran 1, declined 1" in said, said
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
    # the seat's answers are counted once each: one decline covers the request and its repeat
    assert "2 answered by 1 seat reply: declined 1; 1 not answered" in said, said


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


def test_a_repeat_already_answered_is_not_rebound_to_a_later_run_of_other_bytes():
    # legion's review of #666, item 3: seq 1 (bytes A), declined at 2, seq 3 (A again), seq 4 (bytes B), the seat
    # runs B at 5 naming seq 4. The forward binding ignored bytes and reported A's repeat as "I ran ... (sha B)".
    a = "[request_run] notes/x.py\nwhy: /dev/gadget7\n(10 bytes, sha256:aaaaaaaaaaaa; the seat decides)"
    b = a.replace("aaaaaaaaaaaa", "bbbbbbbbbbbb")
    turns = [{"seq": 1, "from": "b", "text": a},
             {"seq": 2, "from": "seat", "text": "[request_run] I did not run notes/x.py. No.\n\nAnswers your request seq 1."},
             {"seq": 3, "from": "b", "text": a},
             {"seq": 4, "from": "b", "text": b},
             {"seq": 5, "from": "seat", "text": "[request_run] I ran notes/x.py (sha bbbbbbbbbbbb). exit code 0.\n\nAnswers your request seq 4."}]
    by = {f["seq"]: f for f in rv.earlier_requests(turns, "b", "notes/y.py /dev/gadget7")}
    assert by[3]["answer_seq"] == 2 and by[3].get("repeat_of") == 1, by[3]
    assert by[4]["answer_seq"] == 5
    said = rv.earlier_requests_said(list(by.values()))
    assert "3 answered by 2 seat replies: ran 1, declined 1" in said, said


def test_a_keyed_request_is_not_credited_with_a_rerun_of_other_bytes():
    # a hub-fired session on #666: bytes A at seq 1, a rerun of bytes B at seq 2 (no key), the seat runs B naming 2
    a = "[request_run] notes/x.py\nwhy: /dev/gadget7\n(10 bytes, sha256:aaaaaaaaaaaa; the seat decides)"
    b = "[request_run] notes/x.py\nwhy: /dev/gadget7 again\n(10 bytes, sha256:bbbbbbbbbbbb; the seat decides)\nrerun: true"
    turns = [{"seq": 1, "from": "b", "text": a}, {"seq": 2, "from": "b", "text": b},
             {"seq": 3, "from": "seat", "text": "[request_run] I ran notes/x.py (sha bbbbbbbbbbbb). exit code 0.\n\nAnswers your request seq 2."}]
    by = {f["seq"]: f for f in rv.earlier_requests(turns, "b", "notes/y.py /dev/gadget7")}
    assert by[1]["answer_seq"] is None, by[1]
    assert by[2]["answer_seq"] == 3


_A = "[request_run] notes/x.py\nwhy: /dev/gadget7\n(10 bytes, sha256:aaaaaaaaaaaa; the seat decides)"
_B = _A.replace("aaaaaaaaaaaa", "bbbbbbbbbbbb")


def _ran(sha, seq, where=""):
    """The receipt seat_run_requests writes, GPU clause and all."""
    where = f", {where}" if where else ""
    return (f"[request_run] I ran notes/x.py (sha {sha}) with no arguments (the script's defaults){where}. "
            f"exit code 0.\n\nAnswers your request seq {seq}.")


def _bound(*seqs):
    turns = [{"seq": i, "from": who, "text": text} for i, (who, text) in enumerate(seqs, 1)]
    return {f["seq"]: f for f in rv.earlier_requests(turns, "b", "notes/y.py /dev/gadget7")}


def test_a_run_of_these_bytes_binds_however_long_its_receipt():
    # McNugget's review of #667: the receipt was matched cut to 200 characters, so the GPU clause alone left this
    # arm dead on every receipt carrying it. The seat names seq 2 and runs seq 1's bytes.
    assert len(_ran("a" * 12, 2, srr.WHERE_HIDDEN).split("\n", 1)[0]) > 200, "the case needs a long receipt"
    for where in ("", srr.WHERE_HIDDEN):
        by = _bound(("b", _A), ("b", _B), ("seat", _ran("a" * 12, 2, where)))
        assert by[1]["answer_seq"] == 3, (where, by[1])
    assert len(by[1]["answer"]) == 200, "what the receipt shows stays cut"


def test_equal_keys_do_not_credit_a_copy_with_a_run_of_other_bytes():
    # pub's review of #667: the seat names seq 2 and runs B. Seq 2 was named, so it keeps the answer it was given;
    # its copies, before and after, were not run.
    by = _bound(("b", _A), ("b", _A), ("b", _B), ("seat", _ran("b" * 12, 2)), ("b", _A))
    assert by[1]["answer_seq"] is None, by[1]
    assert by[5]["answer_seq"] is None and "repeat_of" not in by[5], by[5]
    assert by[2]["answer_seq"] == 4 and by[3]["answer_seq"] == 4


def test_equal_keys_still_bind_a_run_of_these_bytes_and_a_decline():
    # the other direction: a receipt that agrees, or says nothing about bytes, contradicts nothing
    by = _bound(("b", _A), ("b", _A), ("seat", _ran("a" * 12, 2, srr.WHERE_HIDDEN)), ("b", _A))
    assert by[1]["answer_seq"] == 3 and by[4]["answer_seq"] == 3 and by[4]["repeat_of"] == 2, by
    no = "[request_run] I did not run notes/x.py. No.\n\nAnswers your request seq 2."
    by = _bound(("b", _A), ("b", _A), ("seat", no), ("b", _A))
    assert by[1]["answer_seq"] == 3 and by[4]["answer_seq"] == 3, by


def test_the_tally_adds_up_when_an_answer_has_no_seq():
    # McNugget's review of #667: counted in neither "answered by N" nor "not answered"
    said = rv.earlier_requests_said([
        {"seq": 1, "ts": "", "file": "notes/x.py", "answer_seq": None, "answer": "[request_run] I ran notes/x.py"},
        {"seq": 2, "ts": "", "file": "notes/x.py", "answer_seq": 3, "answer": "[request_run] I did not run it"}])
    assert "1 answered by 1 seat reply: declined 1; 1 not answered" in said, said


def test_the_newest_answer_to_the_same_work_stands_on_either_side():
    # legion's review of #667: decline, repeats, then a run of those bytes naming a repeat. The last repeat read
    # "declined" under a receipt that quoted the run.
    no = "[request_run] I did not run notes/x.py. No.\n\nAnswers your request seq 1."
    by = _bound(("b", _A), ("seat", no), ("b", _A), ("b", _A), ("seat", _ran("a" * 12, 3)))
    assert by[4]["answer_seq"] == 5 and "repeat_of" not in by[4], by[4]
    # the seat changes its mind and names the original: the run was missing from the tally altogether
    by = _bound(("b", _A), ("seat", no), ("b", _A), ("seat", _ran("a" * 12, 1)))
    assert by[3]["answer_seq"] == 4, by[3]
    said = rv.earlier_requests_said(list(by.values()))
    assert "ran 1, declined 1" in said, said
    # and the other way: a decline after a run is the newest answer, as `unchanged` reports it
    later_no = no.replace("seq 1.", "seq 3.")
    by = _bound(("b", _A), ("seat", _ran("a" * 12, 1)), ("b", _A), ("seat", later_no), ("b", _A))
    assert by[5]["answer_seq"] == 4 and by[5]["repeat_of"] == 3, by[5]


def test_a_run_of_these_bytes_answers_a_repeat_filed_after_it():
    # legion's and cbp's reviews of #667: the receipt names another request and runs these bytes. It is not "the
    # same bytes as" the request it named, so no repeat_of.
    by = _bound(("b", _A), ("b", _B), ("seat", _ran("a" * 12, 2, srr.WHERE_HIDDEN)), ("b", _A))
    assert by[4]["answer_seq"] == 3 and "repeat_of" not in by[4], by[4]


def test_no_answer_does_not_promise_one():
    # legion's review of #667: a same-file result closes the older request in pending(), so "yet" would not come
    by = _bound(("b", _A), ("b", _B), ("seat", _ran("b" * 12, 2)))
    assert by[1]["answer_seq"] is None
    said = rv.earlier_requests_said(list(by.values()))
    assert "seq 1 (notes/x.py): (no answer to these bytes)" in said and "yet" not in said, said
