"""dp, 2026-10-03: "no cap on beat duration, if the being wants to keep going it should".

`--explore-budget-s 0` means no deadline. The trap it closes: the deadline was `t0 + budget`, so a
0 meant to lift the cap would have ended explore before its first step.
"""
import inspect

from sage.gateway import heartbeat as hb
from sage.gateway.being_tool_loop import run_tool_turn


def test_zero_or_less_is_no_deadline_and_a_positive_budget_still_is_one():
    assert hb.explore_deadline_for(1000.0, 0) is None
    assert hb.explore_deadline_for(1000.0, -1) is None
    assert hb.explore_deadline_for(1000.0, None) is None
    assert hb.explore_deadline_for(1000.0, 7200) == 8200.0


def test_main_takes_the_deadline_from_the_helper():
    src = inspect.getsource(hb.main)
    assert "explore_deadline = explore_deadline_for(t0, args.explore_budget_s)" in src
    assert "t0 + args.explore_budget_s" not in src


def test_the_loop_has_no_deadline_unless_one_is_given():
    """The tool loop's own default is no deadline; the beat passes the helper's None through."""
    assert inspect.signature(run_tool_turn).parameters["deadline"].default is None
