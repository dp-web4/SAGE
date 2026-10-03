"""being_act_ledger counts what a beat did to code next to what it said it did."""
import importlib.util
import json
from pathlib import Path

_P = Path(__file__).resolve().parents[2] / "scripts" / "being_act_ledger.py"
_s = importlib.util.spec_from_file_location("being_act_ledger", _P)
L = importlib.util.module_from_spec(_s)
_s.loader.exec_module(L)


def beat(*calls, phase="explore"):
    return {"ts": "2026-09-22T00:00:00Z", phase: {"trace": [dict(c) for c in calls]}}


def c(effector, ok=True, refused=False, result="", **args):
    return {"effector": effector, "args": args, "ok": ok, "refused": refused, "result": result, "error": None}


def test_a_refused_edit_then_a_done_claim_is_a_false_claim():
    b = beat(c("memory_edit", ok=False, refused=True, path="s.py", start_line=10),
             c("memory_write", path="todo.md", content="- [done] memory_edit s.py: remove line 10"))
    r = L.analyse(b)
    assert r["edits_refused"] == 1 and len(r["false_claims"]) == 1


def test_a_claim_after_a_real_edit_is_not_false():
    b = beat(c("memory_edit", path="s.py", start_line=10),
             c("memory_write", path="journal.md", content="Fixed s.py at line 10."))
    assert L.analyse(b)["false_claims"] == []


def test_the_previous_beats_edit_excuses_a_lagging_claim():
    b = beat(c("memory_write", path="journal.md", content="Fixed s.py at line 10."))
    assert L.analyse(b, prev_changed=True)["false_claims"] == []
    assert len(L.analyse(b, prev_changed=False)["false_claims"]) == 1


def test_plans_negations_and_seat_reports_are_not_claims():
    for text in ("Next: run s.py to confirm the fix.", "The memory_edit was not applied to s.py.",
                 "The seat removed line 10 of s.py.", "- [ ] Fix line 10 of s.py"):
        b = beat(c("memory_write", path="journal.md", content=text))
        assert L.analyse(b)["claims"] == [], text


def test_read_before_edit_needs_the_read_to_cover_the_line():
    covered = beat(c("memory_read", path="s.py", result="[lines 1-50 of 90 in 's.py']"),
                   c("memory_edit", path="s.py", start_line=40))
    elsewhere = beat(c("memory_read", path="s.py", result="[lines 60-90 of 90 in 's.py']"),
                     c("memory_edit", path="s.py", start_line=40))
    assert L.analyse(covered)["rbe"] == 1 and L.analyse(elsewhere)["rbe"] == 0
