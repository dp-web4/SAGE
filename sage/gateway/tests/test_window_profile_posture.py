"""Hermetic tests for step 1b of the window profile: the posture on a schedule, and the compacted framing.

What must hold:
- dp's posture is never altered: a beat sends it whole or sends one pointer line instead, never part of it;
- whole every beat when it fits its share; otherwise whole on the first beat of each UTC day and whenever it
  changes, and "read whole today" is recorded only once a prompt carrying it reached the model;
- the pointer names a harness-kept copy that holds the same text, and the being cannot write that copy;
- framing loses only the two bullets the beat says elsewhere;
- absent the profile, nothing here runs and compose is called exactly as before."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import window_profile as wp  # noqa: E402
from sage.gateway.tests.test_window_profile import beat, _spec  # noqa: E402,F401  (the through-main fixture)

POSTURE = "# Being posture\n\nA heartbeat is not a question.\n\n" + "dp's words. " * 600     # over any 8k share
DAY1 = 1_795_000_000.0                       # a fixed instant; DAY1 + 86400 is the next UTC day
B8K = 20_054                                 # the 8k window budget (8192 ctx, 1500 reserve, 3.245 chars/token)


# ---------------------------------------------------------------- the schedule

def test_a_posture_that_fits_its_share_is_whole_every_beat_and_unscheduled(tmp_path):
    text, rec = wp.posture_shown(tmp_path, "short posture", budget=45_326, now=DAY1)
    assert text == "short posture" and rec["mode"] == "whole" and rec["scheduled"] is False
    assert not (tmp_path / wp.POSTURE_COPY).exists() and not (tmp_path / wp.POSTURE_SEEN).exists()


def test_the_real_posture_fits_at_20k_and_is_scheduled_at_8k():
    from sage.gateway import heartbeat as hb
    n = len(hb.posture())
    assert n <= wp.share_chars(45_326, "posture"), "cbp-being's real 20k window: posture whole every beat"
    assert n > wp.share_chars(B8K, "posture"), "an 8k window: posture on its schedule"


def test_an_over_share_posture_is_whole_until_a_whole_showing_is_recorded(tmp_path):
    text, rec = wp.posture_shown(tmp_path, POSTURE, budget=B8K, now=DAY1)
    assert text == POSTURE and rec["mode"] == "whole" and rec["scheduled"] is True
    assert rec["why"] == "not yet shown whole under the profile"
    assert not (tmp_path / wp.POSTURE_SEEN).exists(), "posture_shown never records a showing"
    text2, rec2 = wp.posture_shown(tmp_path, POSTURE, budget=B8K, now=DAY1 + 60)
    assert text2 == POSTURE and rec2["mode"] == "whole", "not recorded, so whole again"


def test_after_a_recorded_whole_showing_the_rest_of_the_day_gets_the_pointer(tmp_path):
    wp.posture_shown(tmp_path, POSTURE, budget=B8K, now=DAY1)
    assert wp.record_posture_seen(tmp_path, POSTURE, now=DAY1)
    text, rec = wp.posture_shown(tmp_path, POSTURE, budget=B8K, now=DAY1 + 600)
    assert rec["mode"] == "pointer" and text == wp.posture_pointer(len(POSTURE))
    assert f"memory_read path {wp.POSTURE_COPY}" in text and rec["sent"] == len(text) < 600
    assert (tmp_path / wp.POSTURE_COPY).read_text(encoding="utf-8") == POSTURE, "the pointer names a faithful copy"
    assert "dp's words. dp's words." not in text, "the pointer never quotes or paraphrases the posture"


def test_the_first_beat_of_the_next_utc_day_is_whole_again(tmp_path):
    wp.record_posture_seen(tmp_path, POSTURE, now=DAY1)
    text, rec = wp.posture_shown(tmp_path, POSTURE, budget=B8K, now=DAY1 + 86_400)
    assert text == POSTURE and rec["why"] == "first beat of the UTC day"


def test_a_changed_posture_is_whole_at_once_and_its_copy_follows(tmp_path):
    wp.record_posture_seen(tmp_path, POSTURE, now=DAY1)
    wp.ensure_posture_copy(tmp_path, POSTURE)
    new = POSTURE + "\nOne new line from dp."
    text, rec = wp.posture_shown(tmp_path, new, budget=B8K, now=DAY1 + 60)
    assert text == new and rec["why"] == "changed since last shown whole"
    assert (tmp_path / wp.POSTURE_COPY).read_text(encoding="utf-8") == new


def test_no_pointer_without_a_faithful_copy(tmp_path, monkeypatch):
    wp.record_posture_seen(tmp_path, POSTURE, now=DAY1)
    monkeypatch.setattr(wp, "ensure_posture_copy", lambda *a, **k: False)
    text, rec = wp.posture_shown(tmp_path, POSTURE, budget=B8K, now=DAY1 + 60)
    assert text == POSTURE and rec["mode"] == "whole" and "could not be kept" in rec["why"]


def test_the_posture_copy_is_seat_owned(tmp_path):
    from sage.gateway import reference_f1a as rf
    from sage.gateway.tests.test_home_is_reachable import _being
    assert rf.POSTURE_COPY == wp.POSTURE_COPY, "one name on both sides"
    r, home = _being(tmp_path)
    (home / wp.POSTURE_COPY).write_text(POSTURE)
    for name in (wp.POSTURE_COPY, wp.POSTURE_COPY.upper(), str(home / wp.POSTURE_COPY)):
        with pytest.raises(ValueError, match="yours to read and not to edit"):
            r._safe_path(name, writing=True)
    assert r._safe_path(wp.POSTURE_COPY, writing=False) == (home / wp.POSTURE_COPY).resolve()


# ---------------------------------------------------------------- framing

def test_compaction_drops_only_the_two_bullets_said_elsewhere():
    from sage.gateway.heartbeat import AFFORDANCES
    new, rec = wp.compact_affordances(AFFORDANCES, {"witness", "recall"})
    assert rec["dropped"] == ["home", "witness"] and rec["saved"] == len(AFFORDANCES) - len(new) > 200
    assert wp.HOME_BULLET_KEEP in new and "Your home is your instance directory" not in new
    assert "- witness:" not in new
    for kept in ("request_scope:", "appeal:", "A recall result is a PREVIEW", "peer_ask / mesh",
                 "You can run Python you wrote with `run`", "Acting means calling a tool.", "{museum}"):
        assert kept in new, kept


def test_the_witness_bullet_stays_when_witness_is_not_offered_with_text():
    from sage.gateway.heartbeat import AFFORDANCES
    new, rec = wp.compact_affordances(AFFORDANCES, set())
    assert rec["dropped"] == ["home"] and "- witness:" in new


def test_changed_affordances_are_left_whole_and_the_record_says_why():
    new, rec = wp.compact_affordances("## What you have this beat\n- something else", {"witness"})
    assert new == "## What you have this beat\n- something else" and rec["saved"] == 0 and "upstream" in rec["why"]


def test_offered_with_text_counts_specs_and_router_lines_not_bare_names():
    tail = [_spec("witness", "Record a witnessed note."), _spec("appeal", "Appeal a refusal.")]
    assert wp.offered_with_text([_spec("describe"), wp.router_spec(tail, with_lines=True)]) == \
        {"describe", "witness", "appeal"}
    assert wp.offered_with_text([_spec("describe"), wp.router_spec(tail, with_lines=False)]) == {"describe"}


def test_compose_defaults_are_the_beat_as_it_was():
    from sage.gateway import heartbeat as hb
    kw = dict(name="n", machine="m", member="b", posture_text="POSTURE", header="H\n", state="S", recall="R",
              inbox="I", digest="D", tools=["describe"], posture_framing="standing_guidance")
    for act_first in (True, False):
        assert hb.compose(act_first, **kw) == hb.compose(act_first, profile=None, **kw)
        seed, _second = hb.compose(act_first, **kw)
        assert hb.AFFORDANCES.split("{museum}")[0] in seed[0]["content"]
    seed, second = hb.compose(True, profile={"affordances": "## What you have this beat\n- x{museum}",
                                             "posture_pointer": True}, **dict(kw, posture_text="(pointer)"))
    assert "- x" in seed[0]["content"] and "Your home is your instance directory" not in seed[0]["content"]
    assert "(pointer)" in second and "given to you each beat" not in second


# ---------------------------------------------------------------- through heartbeat.main

def _posture_turn(sent):
    return next((m for m, _t in sent if "Standing guidance" in m), None)


def test_absent_the_profile_compose_is_called_as_before_and_nothing_new_runs(beat, monkeypatch):
    from sage.gateway import heartbeat as hb

    def boom(*a, **k):
        raise AssertionError("a step-1b function ran with window_profile absent")
    for fn in ("posture_shown", "compact_affordances", "ensure_posture_copy", "record_posture_seen"):
        monkeypatch.setattr(wp, fn, boom)
    calls = []
    real = hb.compose

    def spy(*a, **k):
        calls.append(k)
        return real(*a, **k)
    monkeypatch.setattr(hb, "compose", spy)
    rec, sent = beat(posture_framing="standing_guidance")
    assert calls and all(k.get("profile") is None for k in calls)
    assert all(k["posture_text"] == hb.posture() for k in calls)
    assert any(hb.posture() in m for m, _t in sent)
    assert "window_profile" not in rec


def test_on_an_8k_profile_the_posture_is_whole_then_the_pointer_then_whole_next_day(beat, tmp_path):
    from sage.gateway import heartbeat as hb
    inst = tmp_path / "inst"
    full = hb.posture()
    rec, sent = beat(window_profile=True, posture_framing="standing_guidance")
    p = rec["window_profile"]["posture"]
    assert p["mode"] == "whole" and p["scheduled"] and p["delivered"] and p["seen_recorded"], p
    assert any(full in m for m, _t in sent)
    assert (inst / wp.POSTURE_COPY).read_text(encoding="utf-8") == full
    fr = rec["window_profile"]["framing"]
    # this fixture has no use history, so `verb` lists names only: witness has no line, and its bullet stays
    assert fr["saved"] > 150 and fr["dropped"] == ["home"], fr
    assert rec["window_profile"]["tools"]["router_lines"] is False
    assert not any(wp.HOME_BULLET in m for m, _t in sent)      # the bullet; the closing turn says it its own way

    rec2, sent2 = beat(window_profile=True, posture_framing="standing_guidance")
    p2 = rec2["window_profile"]["posture"]
    assert p2["mode"] == "pointer", p2
    assert not any(full in m for m, _t in sent2), "not repeated this beat"
    turn = _posture_turn(sent2)
    assert turn and wp.posture_pointer(len(full)) in turn and "given to you each beat" not in turn
    assert rec2["prompt_parts"]["chars"]["posture"] == len(wp.posture_pointer(len(full)))

    seen = json.loads((inst / wp.POSTURE_SEEN).read_text())
    (inst / wp.POSTURE_SEEN).write_text(json.dumps(dict(seen, day="2000-01-01")))
    rec3, sent3 = beat(window_profile=True, posture_framing="standing_guidance")
    assert rec3["window_profile"]["posture"]["why"] == "first beat of the UTC day"
    assert any(full in m for m, _t in sent3)


def test_a_whole_showing_that_never_reached_the_model_is_not_recorded(beat, tmp_path, monkeypatch):
    from sage.gateway import being_tool_loop
    from sage.gateway.being_tool_loop import ToolTurnResult
    inst = tmp_path / "inst"

    def unanswered(client, llm_, messages, *a, **kw):
        return ToolTurnResult(reply="", trace=[], steps=0)      # no count, no done reason: nothing reached it
    monkeypatch.setattr(being_tool_loop, "run_ollama_tool_turn", unanswered)
    rec, _sent = beat(window_profile=True, posture_framing="standing_guidance")
    p = rec["window_profile"]["posture"]
    assert p["mode"] == "whole" and p["delivered"] is False and p["seen_recorded"] is False
    assert not (inst / wp.POSTURE_SEEN).exists()
