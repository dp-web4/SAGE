"""A run request is closed by an answer that NAMES it, not by whatever the seat says next.

GPT's review of the request_run tools: `pending()` closed every earlier request as soon as any
seat turn followed it, and `run`/`decline` were bound to a path, not to a request. On
cbp-being's real channel (10 requests, 2026-09-21) every first seat turn after a request
happened to be its answer, so nothing had gone wrong yet — the rule held only because the
seat answered promptly. These pin the rule that does not depend on that.
"""
import importlib.util
import tempfile
from pathlib import Path

import pytest

from sage.gateway import conversations as conv

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seat_run_requests.py"
_spec = importlib.util.spec_from_file_location("seat_run_requests_ident", _SCRIPT)
srr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srr)

BEING, SEAT, CID = "cbp-being", "cbp-claude", "cbp-claude"


@pytest.fixture
def inst(monkeypatch):
    monkeypatch.setenv("SEAT_ID", SEAT)
    d = Path(tempfile.mkdtemp(prefix="rr-"))
    (d / "notes").mkdir()
    (d / "notes" / "a.py").write_text("print('a')\n")
    (d / "notes" / "b.py").write_text("print('b')\n")
    conv.create(d, CID, title="seat", participants=[BEING, SEAT], writable_by=[BEING, SEAT], summary="")
    return d


def ask(inst, path):
    return conv.append(inst, CID, speaker=BEING, text=f"[request_run] {path}\nwhy: check it")["seq"]


def seat(inst, text):
    conv.append(inst, CID, speaker=SEAT, text=text)


def pending_seqs(inst):
    return [int(t["seq"]) for t in srr.pending(inst, CID)]


def test_an_unrelated_seat_message_closes_nothing(inst):
    """GPT's case. Under the old rule this request was retired by the seat saying hello."""
    s = ask(inst, "notes/a.py")
    seat(inst, "Morning. Unrelated: the posture file changed overnight.")
    assert pending_seqs(inst) == [s]


def test_a_named_answer_closes_exactly_what_it_names(inst):
    s1, s2 = ask(inst, "notes/a.py"), ask(inst, "notes/b.py")
    seat(inst, "I looked at a.py. " + srr.answers_line([s1]))
    assert pending_seqs(inst) == [s2]


def test_the_hand_written_answer_form_still_closes(inst):
    """How seat answers were written before the marker existed; the history must not re-open."""
    s1, s2 = ask(inst, "notes/a.py"), ask(inst, "notes/a.py")
    seat(inst, f"From the seat, answering your seq {s1} and {s2}. I ran it.")
    assert pending_seqs(inst) == []


def test_a_result_closes_earlier_requests_for_that_file_only(inst):
    s1, s2 = ask(inst, "notes/a.py"), ask(inst, "notes/b.py")
    seat(inst, "[request_run] I ran notes/a.py with the GPU hidden from it. exit code 0.")
    s3 = ask(inst, "notes/a.py")          # asked again AFTER the result: still open
    assert pending_seqs(inst) == [s2, s3]


def test_a_decline_sentence_period_is_not_part_of_the_path(inst):
    s = ask(inst, "notes/a.py")
    seat(inst, "[request_run] I did not run notes/a.py. It deletes files outside notes/.")
    assert pending_seqs(inst) == []


def test_two_spellings_of_one_file_are_one_file(inst):
    s = ask(inst, "notes/../notes/a.py")
    seat(inst, "[request_run] I ran notes/a.py with the GPU hidden from it. exit code 1.")
    assert pending_seqs(inst) == []


def test_run_binds_every_pending_request_for_the_file_by_default(inst):
    s1, s2, s3 = ask(inst, "notes/a.py"), ask(inst, "notes/b.py"), ask(inst, "notes/a.py")
    assert srr.bind(inst, CID, "notes/a.py", None) == [s1, s3]


def test_an_explicit_seq_must_name_a_pending_request(inst):
    s = ask(inst, "notes/a.py")
    assert srr.bind(inst, CID, "notes/a.py", [s]) == [s]
    with pytest.raises(SystemExit):
        srr.bind(inst, CID, "notes/a.py", [s + 99])


def test_an_unasked_run_says_it_answers_nothing(inst):
    assert srr.bind(inst, CID, "notes/b.py", None) == []
    assert "answers none" in srr._answers([])


def test_an_explicit_seq_for_a_different_file_is_refused(inst):
    """GPT on #149: seq 11 asked for b.py; `run a.py --seq 11` must not claim to answer it."""
    sa, sb = ask(inst, "notes/a.py"), ask(inst, "notes/b.py")
    with pytest.raises(SystemExit) as e:
        srr.bind(inst, CID, "notes/a.py", [sb])
    assert "asked for 'notes/b.py'" in str(e.value)
    assert srr.bind(inst, CID, "notes/a.py", [sa]) == [sa]


def test_the_answer_names_the_version_it_ran():
    """seq 3364/3365: the file changed 38 s after the request; the answer did not say so."""
    line = srr.version_line(b"x = 1\ny = 2\n", {7: ""})
    assert line.startswith("The file I ran is sha256:") and "2 lines" in line
    assert "not the version" not in line


def test_a_request_for_an_older_version_is_told_it_got_the_newer_one():
    data = b"x = 1\n"
    import hashlib
    same = hashlib.sha256(data).hexdigest()[:12]
    line = srr.version_line(data, {5: same, 6: "2f8fa7424641"})
    assert "seq 6 named sha256:2f8fa7424641" in line and "seq 5" not in line
