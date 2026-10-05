"""The reflect record states what follows from acts that produced nothing (SAGE#132; recut of
#133 as a per-instance experiment: instance.json `no_result_line: "on"`, cbp-being only).

The fixture is cbp-being's beat 2026-09-20T22:51:39Z, shape for shape: `python3` refused 3 times
in explore and 3 in posture, 0 successes, and all 6 `-> REFUSED` lines in the reflect context.
The being reproduced every one correctly and then wrote "After appeal, the script ran
successfully and passed all tests". Today's commoner shape is request_run returning ok with
`ran: false` (review of #133, 2026-09-28), which an ok-only reading counts as a success.
"""
import inspect
import json
from pathlib import Path


class I:
    def __init__(self, effector, args): self.effector, self.args = effector, args


class E:
    def __init__(self, ok, refused=False, result=None):
        self.ok, self.refused, self.error, self.result = ok, refused, "registry.unbounded", result


class T:
    def __init__(self, trace): self.trace = trace


PY = (I("python3", {"command": "python3 mechanism-test-runner.py"}), E(False, True))
OK = (I("memory_write", {"path": "journal.md"}), E(True))
ASKED = {"requested": "notes/t.py", "asked": "cbp-claude", "ran": False,
         "note": "The seat has been asked and woken. NOTHING HAS RUN YET and this is not a result."}
RR = (I("request_run", {"path": "notes/t.py", "why": "verify the fix"}), E(True, result=ASKED))
RR_UNCHANGED = (I("request_run", {"path": "notes/t.py"}),
                E(True, result={**ASKED, "unchanged": "This file is byte-for-byte ... which was:\nexit 1"}))


def test_off_by_default_the_record_is_unchanged():
    """Every instance without the key gets byte-for-byte the old record, even on the measured
    beat's shape."""
    from sage.gateway.heartbeat import _beat_record_text
    explore = T([PY, (I("request_scope", {"path": "/x"}), E(True)), PY, PY, RR])
    text = _beat_record_text(explore, T([PY, PY, PY]))
    assert "Nothing you tried" not in text
    assert text == _beat_record_text(explore, T([PY, PY, PY]), no_result=False)
    assert text.startswith("Record of what you did this beat:\n- python3")


def test_an_effector_that_only_ever_refused_is_stated_as_having_no_result():
    from sage.gateway.heartbeat import _beat_record_text
    explore = T([PY, (I("request_scope", {"path": "/x"}), E(True)), PY, PY])
    posture = T([PY, (I("appeal", {}), E(True)), PY, PY])
    text = _beat_record_text(explore, posture, no_result=True)
    tail = text.split("Nothing you tried")[1]
    assert "python3 (6 refusals)" in tail, text
    assert "You have no result from them" in tail
    assert "request_scope" not in tail and "appeal" not in tail       # those succeeded
    # failed and then SUCCEEDED: the being does have a result
    assert "Nothing you tried" not in _beat_record_text(T([PY, (I("python3", {}), E(True))]), no_result=True)
    # singular reads as English; a clean beat adds nothing
    assert "python3 (1 refusal)." in _beat_record_text(T([PY, OK]), no_result=True)
    assert _beat_record_text(T([OK]), no_result=True) == \
        'Record of what you did this beat:\n- memory_write {"path": "journal.md"} -> ok'


def test_a_request_run_that_returned_ran_false_is_not_a_result():
    """Today's shape. On main this line keyed on refusals only, so a beat whose only "run" was
    request_run's ok-with-ran:false produced no line at all. Fails without the fix."""
    from sage.gateway.heartbeat import _beat_record_text
    text = _beat_record_text(T([RR, OK, RR]), no_result=True)
    assert "Nothing you tried with these ran this beat" in text, text
    assert "request_run (2 calls that returned ran: false)" in text, text
    assert "memory_write" not in text.split("Nothing you tried")[1]
    # mixed with refusals of the same effector, both counts are named
    text = _beat_record_text(T([RR, (I("request_run", {}), E(False, True))]), no_result=True)
    assert "request_run (1 refusal, 1 call that returned ran: false)" in text, text


def test_a_carried_earlier_answer_is_named_as_the_result_for_unchanged_bytes():
    """A request_run that carried the seat's earlier answer still ran nothing THIS beat, but the
    being is not without a result: the earlier run of the same bytes is it. The line must not
    call that unknown."""
    from sage.gateway.heartbeat import _beat_record_text
    text = _beat_record_text(T([RR_UNCHANGED]), no_result=True)
    assert "request_run (1 call that returned ran: false)" in text, text
    assert "returned the seat's EARLIER answer" in text and "still the result" in text, text


def test_an_ok_result_without_ran_false_counts_as_a_result():
    """Only the structured `ran: false` field marks a non-result; any other ok is a result."""
    from sage.gateway.heartbeat import _beat_record_text
    ran = (I("request_run", {}), E(True, result={"ran": True}))
    assert "Nothing you tried" not in _beat_record_text(T([ran]), no_result=True)
    # a ran:false call followed by one that did produce a result: not listed
    assert "Nothing you tried" not in _beat_record_text(T([RR, ran]), no_result=True)


def test_reader_and_beat_record():
    from sage.gateway import heartbeat
    from sage.gateway.heartbeat import no_result_line_for
    assert no_result_line_for(None) is None
    assert no_result_line_for({}) is None
    assert no_result_line_for({"no_result_line": True}) is None
    assert no_result_line_for({"no_result_line": "nonsense"}) is None
    assert no_result_line_for({"no_result_line": "on"}) == "on"
    src = inspect.getsource(heartbeat)
    assert '"no_result_line": no_result_line_for(instance_config(instance))' in src
    # only the reflect turn reads it; the answer turn's records are unchanged
    assert src.count("no_result=bool(no_result_line_for(instance_config(instance)))") == 1


def test_cbp_being_is_the_only_instance_that_opted_in():
    """The measured being carries the opt-in; no other checked-in instance.json does."""
    from sage.gateway.heartbeat import no_result_line_for
    repo = Path(__file__).resolve().parents[3]
    on = []
    for cfg_path in sorted((repo / "sage/instances").glob("*/instance.json")):
        try:
            cfg = json.loads(cfg_path.read_text())
        except Exception:
            continue
        if no_result_line_for(cfg):
            on.append(cfg_path.parent.name)
    assert on == ["cbp-qwen3.8-distill-4b"]
