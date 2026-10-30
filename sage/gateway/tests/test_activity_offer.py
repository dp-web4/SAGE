"""Synthetic reference-contract tests, not heartbeat integration or model trials."""
from dataclasses import asdict, replace
import json

import pytest

from sage.gateway.activity_offer import Offer, opportunity_context, project


def offer():
    return Offer("being", "observer", "conversation", 17,
                 "Optional: read scratch/fixture.md.\nDecline or defer if you prefer.", 1000, 1600)


def event(seq, kind, **kw):
    return {"seq": seq, "at": 1000 + seq, "offer_id": offer().id, "kind": kind, **kw}


def accepted():
    return [event(1, "beat_started", beat="b1"),
            event(2, "disposition", actor="being", decision="accept")]


def test_acknowledgement_and_completion_prose_are_not_acceptance():
    rows = [event(1, "beat_started", beat="b1"),
            event(2, "utterance", actor="being", text="Yes, I accept. Done! I read it.")]
    out = project(offer(), rows, now=1010)
    assert out["disposition"] is None and not out["eligible_to_claim"]
    assert out["execution"] == out["completion"] == "not_established"
    assert opportunity_context(offer(), rows, now=1010) is None


def test_explicit_acceptance_retains_the_exact_offer_and_source():
    context = opportunity_context(offer(), accepted(), now=1010)
    assert context == {"offer_id": offer().id, "conversation": "conversation", "sequence": 17,
                       "request": offer().request, "request_sha256": offer().request_sha256,
                       "disposition": "accept"}
    # No grant, effector or execution claim is returned.
    assert project(offer(), accepted(), now=1010)["claim"] is None


@pytest.mark.parametrize("decision", ["decline", "defer"])
def test_decline_or_defer_ends_only_this_observation(decision):
    rows = accepted()
    rows[-1]["decision"] = decision
    out = project(offer(), rows, now=1010)
    assert out["terminal_reason"] == decision and not out["eligible_to_claim"]
    assert out["execution"] == "not_established"


def test_deadline_survives_serialization_and_never_rebases_on_restart():
    restored = Offer(**json.loads(json.dumps(asdict(offer()))))
    rows = json.loads(json.dumps(accepted()))
    assert project(restored, rows, now=1599)["eligible_to_claim"]
    for now in (1600, 1601, 2000):
        assert project(restored, rows, now=now)["terminal_reason"] == "deadline"
        assert opportunity_context(restored, rows, now=now) is None


def test_two_ordinary_beats_include_preacceptance_time():
    rows = [event(1, "beat_started", beat="b1"), event(2, "beat_finished", beat="b1"),
            event(3, "beat_started", beat="b2"),
            event(4, "disposition", actor="being", decision="accept")]
    assert project(offer(), rows, now=1010)["eligible_to_claim"]
    rows.append(event(5, "beat_finished", beat="b2"))
    assert project(offer(), rows, now=1010)["terminal_reason"] == "beat_limit"
    rows.append(event(6, "beat_started", beat="b3"))
    out = project(offer(), rows, now=1010)
    assert out["beats_started"] == 2 and out["late_records"] == 1
    assert not out["eligible_to_claim"]


def test_preemption_closes_without_suppressing_or_reclassifying_later_input():
    rows = accepted() + [event(3, "preempted"),
                         event(4, "utterance", actor="being", text="Answering the newer request.")]
    out = project(offer(), rows, now=1010)
    assert out["terminal_reason"] == "preempted" and out["late_records"] == 1
    assert not out["eligible_to_claim"]


def test_persisted_claim_replays_once_but_proves_no_dispatch():
    claim = event(3, "opportunity_claimed", observer="observer", claim="claim-1")
    rows = accepted() + [claim, dict(claim)]
    restored = json.loads(json.dumps(rows))
    out = project(offer(), restored, now=1010)
    assert out["claim"] == {"id": "claim-1", "beat": "b1", "at": 1003}
    assert not out["eligible_to_claim"] and opportunity_context(offer(), restored, now=1010) is None
    assert out["execution"] == out["completion"] == "not_established"
    with pytest.raises(ValueError):
        project(offer(), rows + [event(4, "opportunity_claimed", observer="observer", claim="claim-2")], now=1010)


@pytest.mark.parametrize("decision", [True, 1, "yes", "accepted", " accept "])
def test_disposition_has_no_coercion_or_prose_salvage(decision):
    rows = accepted()
    rows[-1]["decision"] = decision
    with pytest.raises(ValueError):
        project(offer(), rows, now=1010)


@pytest.mark.parametrize("changes", [
    {"request": "Different request"}, {"sequence": 18}, {"conversation": "other"},
    {"actor": "other"}, {"observer": "other"}, {"deadline": 1700},
])
def test_event_identity_binds_source_actor_and_budget(changes):
    with pytest.raises(ValueError):
        project(replace(offer(), **changes), accepted(), now=1010)


def test_wrong_author_and_conflicting_record_are_rejected():
    rows = accepted()
    rows[1]["actor"] = "peer"
    with pytest.raises(ValueError):
        project(offer(), rows, now=1010)
    rows = accepted()
    conflicting = dict(rows[-1], decision="decline")
    with pytest.raises(ValueError):
        project(offer(), rows + [conflicting], now=1010)


def test_late_acceptance_is_recorded_but_not_retroactive():
    rows = accepted()
    rows[-1]["at"] = 1600
    out = project(offer(), rows, now=1600)
    assert out["disposition"] is None and out["late_records"] == 1
    assert out["terminal_reason"] == "deadline"


@pytest.mark.parametrize("rows", [
    [event(1, "beat_finished", beat="b1")],
    [event(1, "disposition", actor="being", decision="accept")],
    [event(1, "beat_started", beat="b1"), event(2, "beat_started", beat="b2")],
    [event(1, "beat_started", beat="b1"), event(2, "beat_finished", beat="other")],
    [event(1, "beat_started", beat="b1"),
     event(2, "opportunity_claimed", observer="observer", claim="no-acceptance")],
])
def test_invalid_transition_is_not_repaired_by_guessing(rows):
    with pytest.raises(ValueError):
        project(offer(), rows, now=1010)


@pytest.mark.parametrize("changes", [
    {"sequence": True}, {"sequence": 0}, {"request": ""}, {"observer": " "},
    {"opened_at": True}, {"deadline": 1000}, {"deadline": float("nan")},
])
def test_invalid_offer_is_not_normalized(changes):
    with pytest.raises(ValueError):
        replace(offer(), **changes)


@pytest.mark.parametrize("changes", [
    {"seq": True}, {"seq": 0}, {"at": 999}, {"at": 2000},
    {"at": 1001.0}, {"kind": "completed"}, {"extra": "unrecognized"},
])
def test_invalid_records_fail_visibly(changes):
    rows = [dict(event(1, "beat_started", beat="b1"), **changes)]
    with pytest.raises(ValueError):
        project(offer(), rows, now=1010)


def test_observation_time_and_record_count_are_bounded():
    for now in (True, 999, float("nan")):
        with pytest.raises(ValueError):
            project(offer(), [], now=now)
    with pytest.raises(ValueError):
        project(offer(), [event(1, "preempted")] * 65, now=1010)


def test_candidate_context_cannot_mutate_offer_or_event_record():
    rows = accepted()
    context = opportunity_context(offer(), rows, now=1010)
    context["request"] = "Different request"
    assert opportunity_context(offer(), rows, now=1010)["request"] == offer().request
    assert rows == accepted()
