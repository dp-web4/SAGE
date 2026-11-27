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


X = "scratch/xor-visualization-final.py"
BROKEN = (": replaced 1 occurrence, on line 85; the file went from 147 to 147 lines. This changed the file on"
          " disk — it is not an append. Python cannot parse xor-visualization-final.py now: IndentationError"
          " at line 94: unindent does not match any outer indentation level. It cannot run until that line"
          " is fixed.")
FINE = ": replaced 1 occurrence. Python can parse xor-visualization-final.py now. That is not the same as running it."


def _landed(path, result, eff="memory_edit"):
    return (BeingIntent(eff, {"path": path}), ResultEnvelope(ok=True, result=result))


def test_a_landed_py_edit_carries_its_parse_verdict():
    """cbp-being 2026-11-27 08:05Z: told only "landed", reflect journaled "The file now parses and runs"."""
    explore = SimpleNamespace(trace=[_landed(X, BROKEN), _act("memory_edit", X, ok=False)])
    r = receipts_this_beat(explore, None)
    assert r == [f"memory_edit {X} landed, and after your last write to it its receipt said: Python cannot"
                 " parse xor-visualization-final.py now: IndentationError at line 94"], r
    assert "cannot parse" in reflect_prompt(refused=False, receipts=r, **KW)


def test_the_last_verdict_on_a_file_is_the_one_said():
    explore = SimpleNamespace(trace=[_landed(X, BROKEN), _landed(X, FINE)])
    assert receipts_this_beat(explore, None) == [
        f"memory_edit {X} landed (2 times), and after your last write to it its receipt said:"
        " Python can parse xor-visualization-final.py now"]
    explore = SimpleNamespace(trace=[_landed(X, FINE), _landed(X, BROKEN, eff="memory_write")])
    r = receipts_this_beat(explore, None)
    assert r[0] == f"memory_edit {X} landed, and after your last write to it its receipt said: Python cannot" \
                   " parse xor-visualization-final.py now: IndentationError at line 94", r
    assert r[1] == f"memory_write {X} landed", "the verdict is said once per file"


def test_a_receipt_without_a_verdict_stays_landed():
    explore = SimpleNamespace(trace=[_landed("notes/a.md", "appended 3 lines"), _landed(X, {"not": "text"})])
    assert receipts_this_beat(explore, None) == ["memory_edit notes/a.md landed", f"memory_edit {X} landed"]


def test_nothing_to_say_leaves_the_prompt_unchanged():
    assert receipts_this_beat() == [] and receipts_this_beat(None, SimpleNamespace(trace=None)) == []
    assert reflect_prompt(refused=False, receipts=[], **KW) == reflect_prompt(refused=False, **KW)
