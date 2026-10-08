"""sage-tui's pure rendering (no terminal, no daemon)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from sage.tools import sage_tui as t  # noqa: E402


def test_header_shows_state_atp_beat_and_salience():
    lines = t.header_lines({"model": "m", "build": "b"},
                           {"metabolic_state": "wake", "metabolic_age_secs": 3, "metabolic_source": "heartbeat:explore",
                            "atp_percentage": 50.0, "beats": {"completed": 7, "current": {"beat_id": "heartbeat-abc", "phase": "explore", "age_secs": 9}},
                            "salience": {"surprise": 1.0, "novelty": 0.5, "total": 0.55}}, 200)
    assert "state wake" in lines[1] and "50.0%" in lines[1] and "█" * 10 in lines[1]
    assert "phase explore" in lines[2] and "beats completed 7" in lines[2]
    assert "surp" in lines[3] and "total 0.55" in lines[3]


def test_turns_wrap_and_show_the_trial_label_beside_the_words():
    lines = t.turn_lines({"turns": [{"ts": "2026-10-08T18:00:01Z", "from": "sprout-being", "trial": "answer-first",
                                     "text": "word " * 40}]}, 60)
    assert lines[0] == "18:00:01 sprout-being [TEST answer-first]:"
    assert all(len(l) <= 60 for l in lines) and len(lines) > 2


def test_input_is_offered_only_where_dp_may_write():
    assert t.writable({"writable_by": ["dp", "sprout-being"]})
    assert not t.writable({"writable_by": ["sprout-claude", "sprout-being"]})


def test_a_dead_daemon_is_an_error_value_not_a_crash():
    t.BASE = "http://127.0.0.1:9"
    d, e = t.fetch("/health", timeout=0.5)
    assert d == {} and e
