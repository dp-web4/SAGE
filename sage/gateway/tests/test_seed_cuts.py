"""Seed cuts as being parameters (2026-10-07). legion-being's seed filled ~53% of its 32,768
window before its first act, and 14 of 15 retries after retry_cause landed were the window.
Each cut is a row in being_params with a default that keeps every other being unchanged."""
import json

from sage.gateway import being_params as bp
from sage.gateway import conversations as conv
from sage.gateway.heartbeat import dir_listing, entrustment_shown, ENTRUSTMENT_SEEN


def _cfg(tmp_path, **params):
    (tmp_path / "instance.json").write_text(json.dumps({"params": params}))
    return tmp_path


# -- answered turns are capped even at the full rung --------------------------------------
def test_an_answered_turn_is_capped_at_the_full_rung_only_when_asked():
    me, t = "being", {"seq": 3}
    # the default keeps today's behaviour: at the full rung (turn_chars None) shown whole
    assert conv._cap_for(t, me, answered_upto=5, turn_chars=None) is None
    # with the parameter: capped even though the fitter did not step down
    assert conv._cap_for(t, me, answered_upto=5, turn_chars=None, answered_cap=600) == 600
    # a turn AFTER the being's last word is live work: never capped by it
    assert conv._cap_for({"seq": 9}, me, answered_upto=5, turn_chars=None, answered_cap=600) is None
    # under a ladder rung the existing short cap still wins
    assert conv._cap_for(t, me, answered_upto=5, turn_chars=1200, answered_cap=600) == conv.ANSWERED_TURN_CHARS


# -- listings --------------------------------------------------------------------------------
def test_the_listing_limit_is_the_beings_and_says_it_is_partial(tmp_path):
    (tmp_path / "notes").mkdir()
    for i in range(12):
        (tmp_path / "notes" / f"n{i:02d}.md").write_text("x")
    out = dir_listing(tmp_path, "notes", bp.value(_cfg(tmp_path, listing_limit=8), "listing_limit", 30))
    assert out.count("\n- n") == 8 and "4 older" in out


# -- the entrustment, daily ------------------------------------------------------------------
TEXT = "Opening, in dp's words.\n\n## What you have to work with\nmuch\n\n## The rest\nmore"


def test_full_mode_is_unchanged(tmp_path):
    assert entrustment_shown(tmp_path, TEXT, "full") == TEXT
    assert not (tmp_path / ENTRUSTMENT_SEEN).exists()


def test_daily_shows_it_whole_first_then_its_opening_with_a_pointer(tmp_path):
    day1 = 1791331200.0                                  # 2026-10-07T00:00Z
    first = entrustment_shown(tmp_path, TEXT, "daily", now=day1 + 60)
    assert first.startswith(TEXT) and "Shown whole" in first
    later = entrustment_shown(tmp_path, TEXT, "daily", now=day1 + 3600)
    assert later.startswith("Opening, in dp's words.") and "## The rest" not in later
    assert "entrustment.md" in later and "memory_read" in later
    # dp's words are a PREFIX of the file, never paraphrased
    assert TEXT.startswith(later.split("\n\n_(")[0])
    # a new day shows it whole again
    assert entrustment_shown(tmp_path, TEXT, "daily", now=day1 + 86400 + 60).startswith(TEXT)


def test_daily_shows_it_whole_the_moment_it_changes(tmp_path):
    day1 = 1791331200.0
    entrustment_shown(tmp_path, TEXT, "daily", now=day1 + 60)
    changed = TEXT + "\n\nAmended: a new line."
    out = entrustment_shown(tmp_path, changed, "daily", now=day1 + 120)
    assert out.startswith(changed) and "changed since you last saw it whole" in out


def test_a_seat_reading_the_state_does_not_consume_the_whole_showing(tmp_path):
    day1 = 1791331200.0
    entrustment_shown(tmp_path, TEXT, "daily", mark=False, now=day1 + 60)
    assert not (tmp_path / ENTRUSTMENT_SEEN).exists()
    assert entrustment_shown(tmp_path, TEXT, "daily", now=day1 + 120).startswith(TEXT)


def test_choice_parameters_are_refused_outside_their_words(tmp_path):
    h = _cfg(tmp_path)
    ok, text = bp.tune(h, "entrustment_mode", "weekly", "x")
    assert not ok and "full, daily" in text
    ok, _ = bp.tune(h, "entrustment_mode", "Daily", "fewer tokens on repeat beats")
    assert ok and bp.value(h, "entrustment_mode") == "daily"


def test_the_beat_records_a_whole_showing_from_the_state_it_sends(tmp_path):
    """e1439e70c tied the record to mark_conversations, which the beat always passes False
    (the fitter renders several rungs; a render is not a reading), so it never recorded and
    every beat carried the entrustment whole. The beat now records via record_entrustment_seen
    after fit_state, from the state it sends."""
    from sage.gateway.heartbeat import record_entrustment_seen
    day1 = 1791331200.0
    # a render during composition records nothing
    assert entrustment_shown(tmp_path, TEXT, "daily", mark=False, now=day1 + 60).startswith(TEXT)
    assert entrustment_shown(tmp_path, TEXT, "daily", mark=False, now=day1 + 61).startswith(TEXT)
    # the beat sends it whole, then records; the next beat the same day gets the short form
    record_entrustment_seen(tmp_path, TEXT, now=day1 + 62)
    later = entrustment_shown(tmp_path, TEXT, "daily", mark=False, now=day1 + 3600)
    assert not later.startswith(TEXT) and "entrustment.md" in later


def test_main_records_the_showing_after_the_fitter():
    import inspect
    from sage.gateway import heartbeat
    src = inspect.getsource(heartbeat.main)
    fit = src.index("fit_state(")
    rec = src.index("record_entrustment_seen(instance, entrusted)")
    assert fit < rec, "the showing must be recorded from the state the fitter chose"
