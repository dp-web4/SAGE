"""intent_follow_through: the seat-side intention→act measure (see its docstring for the judge and its limits)."""
import json

from sage.tools import intent_follow_through as ift


def _beat(ts, said=None, acts=()):
    rec = {"ts": ts, "explore": {"reply": "", "trace": [{"effector": e, "ok": ok} for e, ok in acts]}}
    if said is not None:
        rec["next_beat"] = {"stay_awake": said}
    return rec


def test_named_kinds_reads_the_beings_own_phrasing():
    assert ift.named_kinds("next beat I use the run tool to size the grid, then act on the board to finish level 2") \
        == ["game", "run"]
    assert ift.named_kinds("fire 4 ACTION6 clicks, then report the win to dp") == ["game", "say"]
    assert ift.named_kinds("read the level block and write a handoff") == []


def test_a_failed_act_is_not_done_and_a_harness_sentence_is_not_a_step():
    beats = [_beat("2026-11-10T01:00Z", "click the red cell to finish level 2"),
             _beat("2026-11-10T01:20Z", "harness: the window reached its floor", [("game", False)]),
             _beat("2026-11-10T01:40Z", None, [("game", True)])]
    ps = ift.pairs(beats)
    assert len(ps) == 1, "only the being's sentence is a stated step"
    assert ps[0]["next"]["game"] is False, "a failed game call is not a game act"
    assert ps[0]["within2"]["game"] is True


def test_rates_by_kind_and_month():
    beats = [_beat("2026-10-01T00:00Z", "LOOK the board"), _beat("2026-10-01T01:00Z", "LOOK again", [("game", True)]),
             _beat("2026-11-01T00:00Z", "click to win", [("game", True)]), _beat("2026-11-01T01:00Z", None,
                                                                                [("memory_write", True)])]
    r = ift.rates(ift.pairs(beats))
    assert r["by_kind"]["game"] == {"named": 3, "next": 2, "within2": 2}
    assert r["by_month"]["2026-10"]["game_next"] == 2 and r["by_month"]["2026-11"]["game_next"] == 0
    json.dumps(r)
