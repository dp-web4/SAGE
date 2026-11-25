"""reflect is shown what the beat's own ok acts did, beside the instruction to write the record (#716).

cbp-being: 2026-11-14 21:42Z, three runs of scratch/test-nonlinear-rule.py all exited 1 and the journal
said the script "now correctly trains"; 2026-11-17 10:37Z, a request_run and, in the same beat, a remember
of a result no run had produced; 10:44Z, a landed memory_edit recorded as pending. Each act was ok=True,
so failed_this_beat (#745) named none of them."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingIntent, ResultEnvelope  # noqa: E402
from sage.gateway.heartbeat import (RECEIPTS_SHOWN, failed_this_beat, receipts_this_beat,  # noqa: E402
                                    reflect_prompt)

KW = dict(date="D", say_line="", say_first="")
S = "scratch/test-nonlinear-rule.py"


def _run(code, script=S):
    return (BeingIntent("run", {"path": script}),
            ResultEnvelope(ok=True, result={"script": script, "exit": code, "stdout": "", "stderr": "x"}))


def _act(eff, path, ok=True, refused=False):
    return (BeingIntent(eff, {"path": path}), ResultEnvelope(ok=ok, refused=refused, error=None if ok else "no"))


def test_three_runs_that_exited_1_are_named_with_their_exits():
    explore = SimpleNamespace(trace=[_run(1), _act("memory_edit", S), _run(1), _act("memory_edit", S), _run(1)])
    assert failed_this_beat(explore, None) == [], "ok=True runs are not failures; that is the gap"
    r = receipts_this_beat(explore, None)
    assert r == [f"run {S} ran 3 times, exits 1, 1, 1", f"memory_edit {S} landed (2 times)"], r
    p = reflect_prompt(refused=False, receipts=r, **KW)
    assert "What your own acts this beat did, from their receipts" in p
    assert f"run {S} ran 3 times, exits 1, 1, 1" in p
    assert "No act of yours this beat is recorded as refused" in p


def test_a_request_run_is_said_to_have_no_result_yet():
    explore = SimpleNamespace(trace=[_act("request_run", "scratch/verify_experiment2_pure_numpy.py")])
    r = receipts_this_beat(explore, None)
    assert r == ["request_run scratch/verify_experiment2_pure_numpy.py was only asked for: the seat has not"
                 " run it, so no result of it exists yet"], r


def test_a_landed_edit_is_named_as_landed_and_failed_or_refused_acts_are_not():
    explore = SimpleNamespace(trace=[_act("memory_edit", "scratch/xor_pure_numpy.py"),
                                     _act("memory_edit", "scratch/a.py", ok=False),
                                     _act("memory_write", "scratch/b.py", ok=False, refused=True),
                                     _act("memory_read", "scratch/c.py")])
    after = SimpleNamespace(trace=[_run(0, "scratch/xor_pure_numpy.py")])
    assert receipts_this_beat(explore, after) == ["memory_edit scratch/xor_pure_numpy.py landed",
                                                  "run scratch/xor_pure_numpy.py exited 0"]


def test_failures_and_receipts_are_both_said():
    explore = SimpleNamespace(trace=[_act("memory_edit", "scratch/a.py", ok=False), _run(2)])
    p = reflect_prompt(refused=True, failed=failed_this_beat(explore, None),
                       receipts=receipts_this_beat(explore, None), **KW)
    assert "FAILED and did not do what you asked" in p and f"run {S} exited 2" in p
    assert p.index("FAILED") < p.index("from their receipts")


def test_many_receipts_are_capped_and_counted():
    explore = SimpleNamespace(trace=[_act("memory_write", f"notes/n{i}.md") for i in range(RECEIPTS_SHOWN + 3)])
    p = reflect_prompt(refused=False, receipts=receipts_this_beat(explore, None), **KW)
    assert "; and 3 more." in p and f"notes/n{RECEIPTS_SHOWN}.md" not in p


def test_nothing_to_say_leaves_the_prompt_unchanged():
    assert receipts_this_beat() == [] and receipts_this_beat(None, SimpleNamespace(trace=None)) == []
    assert reflect_prompt(refused=False, receipts=[], **KW) == reflect_prompt(refused=False, **KW)


# --- an empty receipt list is said out loud when the traces could be read -----------------------

def test_a_beat_that_read_and_failed_keeps_attempts_distinct_from_absence():
    """A failed edit may have effects; an empty receipt list does not prove no work happened."""
    from sage.gateway.heartbeat import nothing_ran_this_beat, run_write_trace_status
    explore = SimpleNamespace(trace=[_act("web_search", "q"), _act("memory_read", "scratch/check_param.py"),
                                     _act("memory_edit", "scratch/dead_relu_experiment.py", ok=False),
                                     _act("memory_read", "scratch/dead_relu_experiment.py")])
    assert receipts_this_beat(explore, None) == [] and nothing_ran_this_beat(explore, None) is False
    assert run_write_trace_status(explore, None) == "incomplete"
    p = reflect_prompt(refused=True, failed=failed_this_beat(explore, None), receipts=[],
                       nothing_ran=nothing_ran_this_beat(explore, None), unresolved_run_write=True, **KW)
    assert "outcome may be incomplete or unknown" in p and "FAILED" in p
    assert "contain no run" not in p and "no output of one exists" not in p
    assert p.index("FAILED") < p.index("run or write attempt")


def test_nothing_ran_is_false_when_anything_ran_was_asked_or_landed():
    from sage.gateway.heartbeat import nothing_ran_this_beat
    assert nothing_ran_this_beat(SimpleNamespace(trace=[_run(1)]), None) is False
    assert nothing_ran_this_beat(SimpleNamespace(trace=[_act("request_run", S)]), None) is False
    assert nothing_ran_this_beat(SimpleNamespace(trace=[_act("memory_read", S)]),
                                 SimpleNamespace(trace=[_act("memory_write", "scratch/x.py")])) is False


def test_unreadable_traces_are_not_reported_as_nothing_ran():
    from sage.gateway.heartbeat import nothing_ran_this_beat
    assert nothing_ran_this_beat() is False
    assert nothing_ran_this_beat(None, None) is False
    assert nothing_ran_this_beat(SimpleNamespace(trace=None)) is False
    assert nothing_ran_this_beat(SimpleNamespace(trace=["not a pair"])) is False


def test_receipts_win_over_nothing_ran_and_the_default_is_unchanged():
    p = reflect_prompt(refused=False, receipts=[f"run {S} exited 0"], nothing_ran=True, **KW)
    assert "recorded explore and posture traces contain no run" not in p
    assert reflect_prompt(refused=False, nothing_ran=False, **KW) == reflect_prompt(refused=False, **KW)


def test_absence_is_scoped_to_readable_recorded_calls_not_external_execution():
    from sage.gateway.heartbeat import nothing_ran_this_beat, run_write_trace_status
    turn = SimpleNamespace(trace=[_act("memory_read", S), _act("web_search", "q")])
    assert run_write_trace_status(turn) == "none" and nothing_ran_this_beat(turn)
    assert nothing_ran_this_beat(SimpleNamespace(trace=[]))
    p = reflect_prompt(nothing_ran=True, **KW)
    assert "recorded explore and posture traces contain no run" in p
    assert "A request is not a completion receipt" in p
    assert "has not happened" not in p and "no output" not in p


def test_incomplete_failed_pending_or_targetless_calls_are_never_absence():
    from sage.gateway.heartbeat import nothing_ran_this_beat, run_write_trace_status
    cases = [
        (BeingIntent("run", {"path": S}), ResultEnvelope(ok=True, result={"stdout": "partial"})),
        (BeingIntent("run", {"path": S}), ResultEnvelope(ok=False, error="failed after writing")),
        (BeingIntent("run", {"path": S}), ResultEnvelope(ok=False, pending=True)),
        (BeingIntent("memory_write", {}), ResultEnvelope(ok=True)),
        (BeingIntent("request_run", {}), ResultEnvelope(ok=True)),
    ]
    for item in cases:
        turn = SimpleNamespace(trace=[item])
        assert not nothing_ran_this_beat(turn), item
        assert run_write_trace_status(turn) == "incomplete", item


def test_unreadable_intent_does_not_establish_absence_or_an_attempt():
    from sage.gateway.heartbeat import run_write_trace_status
    assert run_write_trace_status(SimpleNamespace(trace=[(object(), ResultEnvelope(ok=True))])) == "unknown"
