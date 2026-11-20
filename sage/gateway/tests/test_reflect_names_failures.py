"""reflect names the acts that FAILED this beat, beside "no act refused" (#745).

cbp-being, 2026-11-16 20:30Z: two memory_edit calls failed (ok=False, refused=False, "that text is
not in ..."), the reflect prompt said "No act of yours this beat is recorded as refused", and reflect
recorded both edits as done. The sentence was true; read alone it said everything worked."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingIntent, ResultEnvelope  # noqa: E402
from sage.gateway.heartbeat import (FAILED_SHOWN, REFLECT, failed_this_beat, reflect_prompt,  # noqa: E402
                                    refused_this_beat)

KW = dict(date="D", say_line="", say_first="")
NOT_IN = ("that text is not in 'scratch/xor_numpy_only.py', so nothing was changed\n"
          "da1 is assigned at line 135")


def _edit(path="scratch/xor_numpy_only.py", ok=False, error=NOT_IN, refused=False):
    return (BeingIntent("memory_edit", {"path": path, "old": "a", "new": "b"}),
            ResultEnvelope(ok=ok, refused=refused, error=None if ok else error))


RUN_OK = (BeingIntent("request_run", {"path": "scratch/xor_numpy_only.py"}), ResultEnvelope(ok=True))


def test_the_745_beat_names_both_failed_edits_and_does_not_say_clean_alone():
    explore = SimpleNamespace(trace=[_edit(), _edit(), RUN_OK, RUN_OK])
    assert refused_this_beat(explore, None) is False
    failed = failed_this_beat(explore, None)
    assert failed == ["memory_edit scratch/xor_numpy_only.py: that text is not in "
                      "'scratch/xor_numpy_only.py', so nothing was changed"], failed
    p = reflect_prompt(refused=False, failed=failed, **KW)
    assert "No act of yours this beat is recorded as refused" in p
    assert "FAILED and did not do what you asked, so do not record them as done" in p
    assert "memory_edit scratch/xor_numpy_only.py: that text is not in" in p
    assert "da1 is assigned" not in p, "the first line of the error only"


def test_a_clean_beat_is_unchanged():
    clean = SimpleNamespace(trace=[RUN_OK])
    assert failed_this_beat(clean, None) == []
    assert reflect_prompt(refused=False, failed=[], **KW) == reflect_prompt(refused=False, **KW)
    assert "FAILED" not in reflect_prompt(refused=False, failed=[], **KW)


def test_a_failure_fixed_later_in_the_beat_is_not_named():
    fixed = SimpleNamespace(trace=[_edit(), _edit(ok=True)])
    assert failed_this_beat(fixed, None) == []
    # ...but a fix on another file does not hide it, and a later failure after a fix is named
    other = SimpleNamespace(trace=[_edit(), _edit(path="other.py", ok=True)])
    assert len(failed_this_beat(other, None)) == 1
    again = SimpleNamespace(trace=[_edit(), _edit(ok=True), _edit(error="again")])
    assert failed_this_beat(again, None) == ["memory_edit scratch/xor_numpy_only.py: again"]


def test_a_refusal_is_not_a_failure_and_keeps_its_question():
    denied = _edit(refused=True, error="the law refused")
    beat = SimpleNamespace(trace=[denied, _edit(path="b.py")])
    assert refused_this_beat(beat, None) is True
    failed = failed_this_beat(beat, None)
    assert failed == ["memory_edit b.py: " + NOT_IN.splitlines()[0]]
    p = reflect_prompt(refused=True, failed=failed, **KW)
    assert "what was refused and why you think so" in p and "memory_edit b.py:" in p
    # unknown refusal state keeps the question too, failures still named
    assert "memory_edit b.py:" in reflect_prompt(refused=None, failed=failed, **KW)
    assert reflect_prompt(refused=True, **KW) == REFLECT.format(**KW)


def test_failures_in_the_posture_turn_count_and_the_list_is_bounded():
    many = SimpleNamespace(trace=[_edit(path=f"f{i}.py") for i in range(FAILED_SHOWN + 3)])
    failed = failed_this_beat(None, many)
    assert len(failed) == FAILED_SHOWN + 3
    p = reflect_prompt(refused=False, failed=failed, **KW)
    assert f"f{FAILED_SHOWN - 1}.py" in p and f"f{FAILED_SHOWN}.py" not in p and "and 3 more" in p


def test_unreadable_traces_name_nothing():
    assert failed_this_beat() == [] and failed_this_beat(None, None) == []
    assert failed_this_beat(SimpleNamespace(trace=None)) == []
    assert failed_this_beat(SimpleNamespace(trace=[("truncated",)])) == []
    # an error-less ok=False is not named (nothing to say about it)
    assert failed_this_beat(SimpleNamespace(trace=[_edit(error=None)])) == []
