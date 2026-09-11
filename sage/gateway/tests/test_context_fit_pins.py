"""Regression pins for context-fit behaviour in heartbeat._fill_headroom.

v2, authored by legion-being 2026-09-11. Replaces the six structural pins of
v1 after seat review (SAGE#69, turn 97): v1 pins passed against a no-op
_fill_headroom and their names overclaimed what they asserted. Every pin here
calls _fill_headroom directly with known inputs and asserts on its actual
return — behaviour, not structure.

Implementation cited: sage/gateway/heartbeat.py lines 285-349 (function body
read at 306-349 on 2026-09-11). Expected values use the literal reserve 6144
rather than importing _ANSWER_RESERVE, so a pin fails if that constant moves;
a pin computed from the imported constant would pass either way and pin nothing.

test_fill_headroom_is_beat_scoped is transcribed verbatim from seat turn 98
(legion-claude conversation, 2026-09-11T13:21:15Z), including its two edits
to my draft (num_ctx_resolved; literal 6144).
"""

import pathlib

from sage.gateway.heartbeat import _fill_headroom


def test_fill_headroom_is_beat_scoped(tmp_path):
    """The restored pin: the partial file is append-only across beats, so a
    scan that ignores host_session_id reports another beat's worst prompt as
    this one's. 9000 from an old beat must not leak into a now-beat whose max
    is 7000; and headroom measures against num_ctx_resolved minus the answer
    reserve, so 13_000 - 7000 - 6144 = -144 -> overcommitted."""
    partial = tmp_path / "prompt_evals.jsonl"
    partial.write_text(
        '{"host_session_id": "beat-OLD", "prompt_eval_count": 9000}\n'
        '{"host_session_id": "beat-NOW", "prompt_eval_count": 7000}\n'
        '{"host_session_id": "beat-NOW", "prompt_eval_count": 5200}\n')
    cfg = {"num_ctx_resolved": 13_000}      # NOT num_ctx
    out = _fill_headroom(cfg, partial, "beat-NOW")
    assert out is cfg
    assert cfg["prompt_tokens_max"] == 7000
    assert cfg["headroom_tokens"] == 13_000 - 7000 - 6144   # NOT 640
    assert cfg["context_overcommitted"] is True


def test_fill_headroom_no_matching_lines_reports_none(tmp_path):
    """A beat whose session id appears nowhere in the partial file: best stays
    None, prompt_tokens_max reports that honestly as None, and the headroom /
    overcommit keys are absent rather than computed from a stale or guessed
    number."""
    partial = tmp_path / "prompt_evals.jsonl"
    partial.write_text(
        '{"host_session_id": "beat-OLD", "prompt_eval_count": 9000}\n')
    cfg = {"num_ctx_resolved": 13_000}
    out = _fill_headroom(cfg, partial, "beat-NOW")
    assert out is cfg
    assert cfg["prompt_tokens_max"] is None
    assert "headroom_tokens" not in cfg
    assert "context_overcommitted" not in cfg


def test_fill_headroom_undercommitted_reports_positive_headroom(tmp_path):
    """The sign of headroom: a beat whose max prompt leaves room after the
    answer reserve reports positive headroom and overcommitted False. The
    literal 6144 makes this pin fail if the reserve constant moves."""
    partial = tmp_path / "prompt_evals.jsonl"
    partial.write_text(
        '{"host_session_id": "beat-NOW", "prompt_eval_count": 2000}\n')
    cfg = {"num_ctx_resolved": 13_000}
    out = _fill_headroom(cfg, partial, "beat-NOW")
    assert out is cfg
    assert cfg["prompt_tokens_max"] == 2000
    assert cfg["headroom_tokens"] == 13_000 - 2000 - 6144   # 4856
    assert cfg["context_overcommitted"] is False


def test_fill_headroom_skips_non_int_counts(tmp_path):
    """prompt_eval_count values that are not ints (a string "9000" from a
    malformed upstream writer) must be skipped by the isinstance guard, not
    accepted into best — otherwise prompt_tokens_max would carry a str and the
    headroom branch would never fire for this beat."""
    partial = tmp_path / "prompt_evals.jsonl"
    partial.write_text(
        '{"host_session_id": "beat-NOW", "prompt_eval_count": "9000"}\n'
        '{"host_session_id": "beat-OLD", "prompt_eval_count": 9000}\n')
    cfg = {"num_ctx_resolved": 13_000}
    out = _fill_headroom(cfg, partial, "beat-NOW")
    assert out is cfg
    assert cfg["prompt_tokens_max"] is None


def test_fill_headroom_takes_beat_max_not_last(tmp_path):
    """Within one beat the file appends a line per generate; the field that
    matters for headroom is the beat's worst (max) prompt, not its last. A
    scan that takes the final line reports 5200 where the true max is 7000."""
    partial = tmp_path / "prompt_evals.jsonl"
    partial.write_text(
        '{"host_session_id": "beat-NOW", "prompt_eval_count": 7000}\n'
        '{"host_session_id": "beat-NOW", "prompt_eval_count": 5200}\n')
    cfg = {"num_ctx_resolved": 13_000}
    out = _fill_headroom(cfg, partial, "beat-NOW")
    assert out is cfg
    assert cfg["prompt_tokens_max"] == 7000
