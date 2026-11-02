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
            event(2, "presented", beat="b1", request_sha256=offer().request_sha256),
            event(3, "disposition", actor="being", decision="accept")]


def test_acknowledgement_and_completion_prose_are_not_acceptance():
    rows = [event(1, "beat_started", beat="b1"),
            event(2, "presented", beat="b1", request_sha256=offer().request_sha256),
            event(3, "utterance", actor="being", beat="b1", text="Yes, I accept. Done! I read it.")]
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
        assert project(restored, rows, now=now)["terminal_reason"] == "deadline_presented"
        assert opportunity_context(restored, rows, now=now) is None


def test_two_ordinary_beats_include_preacceptance_time():
    rows = [event(1, "beat_started", beat="b1"),
            event(2, "presented", beat="b1", request_sha256=offer().request_sha256),
            event(3, "beat_finished", beat="b1"), event(4, "beat_started", beat="b2"),
            event(5, "presented", beat="b2", request_sha256=offer().request_sha256),
            event(6, "disposition", actor="being", decision="accept")]
    assert project(offer(), rows, now=1010)["eligible_to_claim"]
    rows.append(event(7, "beat_finished", beat="b2"))
    assert project(offer(), rows, now=1010)["terminal_reason"] == "beat_limit"
    rows.append(event(8, "beat_started", beat="b3"))
    out = project(offer(), rows, now=1010)
    assert out["beats_presented"] == 2 and out["late_records"] == 1
    assert not out["eligible_to_claim"]


def test_unpresented_beats_do_not_spend_budget_or_prove_disposition():
    rows = [event(1, "beat_started", beat="unrelated"),
            event(2, "beat_finished", beat="unrelated"),
            event(3, "beat_started", beat="b1")]
    out = project(offer(), rows, now=1010)
    assert out["beats_presented"] == 0 and out["terminal_reason"] is None
    with pytest.raises(ValueError, match="presented"):
        project(offer(), rows + [event(4, "disposition", actor="being", decision="accept")], now=1010)
    assert project(offer(), rows, now=1600)["terminal_reason"] == "deadline_unpresented"


@pytest.mark.parametrize("count", [0, 1, 2])
def test_deadline_closes_honestly_for_zero_one_or_two_presentations(count):
    rows = []
    for n in range(count):
        seq = 3 * n + 1
        beat = f"b{n}"
        rows.extend([event(seq, "beat_started", beat=beat),
                     event(seq + 1, "presented", beat=beat, request_sha256=offer().request_sha256),
                     event(seq + 2, "beat_finished", beat=beat)])
    out = project(offer(), rows, now=1600)
    assert out["beats_presented"] == count
    assert out["terminal_reason"] == ("deadline_unpresented" if count == 0 else
                                      "deadline_presented" if count == 1 else "beat_limit")


def test_presentation_binds_active_beat_and_exact_request():
    start = [event(1, "beat_started", beat="b1")]
    for bad in (event(2, "presented", beat="other", request_sha256=offer().request_sha256),
                event(2, "presented", beat="b1", request_sha256="wrong")):
        with pytest.raises(ValueError):
            project(offer(), start + [bad], now=1010)
    shown = event(2, "presented", beat="b1", request_sha256=offer().request_sha256)
    with pytest.raises(ValueError):
        project(offer(), start + [shown, event(3, "presented", beat="b1",
                                               request_sha256=offer().request_sha256)], now=1010)


@pytest.mark.parametrize("decision", ["decline", "defer"])
def test_normal_closeout_of_declined_beat_is_not_late(decision):
    rows = accepted()
    rows[-1]["decision"] = decision
    rows.append(event(4, "beat_finished", beat="b1"))
    out = project(offer(), rows, now=1010)
    assert out["terminal_reason"] == decision and out["active_beat"] is None
    assert out["late_records"] == 0


@pytest.mark.parametrize("closure", ["decline", "deadline"])
def test_closing_beat_speech_is_not_late_but_another_beat_is(closure):
    rows = accepted()
    if closure == "decline":
        rows[-1]["decision"] = "decline"
        speech_at = 1004
    else:
        speech_at = 1600
    rows += [dict(event(4, "utterance", actor="being", beat="b1", text="Moving on."), at=speech_at),
             dict(event(5, "beat_finished", beat="b1"), at=speech_at),
             dict(event(6, "utterance", actor="being", beat="b2", text="A new turn."), at=speech_at)]
    out = project(offer(), rows, now=speech_at)
    assert out["active_beat"] is None and out["late_records"] == 1
    assert out["terminal_reason"] == ("decline" if closure == "decline" else "deadline_presented")


def test_utterance_during_open_episode_must_bind_the_active_beat():
    rows = accepted() + [event(4, "utterance", actor="being", beat="other", text="Hello.")]
    with pytest.raises(ValueError, match="active beat"):
        project(offer(), rows, now=1010)


def test_receipt_after_deadline_is_evidence_not_a_new_opportunity():
    claim = event(4, "opportunity_claimed", observer="observer", claim="claim-1")
    receipt = dict(event(5, "result_observed", observer="observer", claim="claim-1",
                         receipt="receipt-1"), at=1601)
    out = project(offer(), accepted() + [claim, receipt], now=1601)
    assert out["result_observed"] == {"claim": "claim-1", "receipt": "receipt-1", "at": 1601}
    assert out["terminal_reason"] == "deadline_presented" and not out["eligible_to_claim"]
    assert out["execution"] == out["completion"] == "not_established"
    with pytest.raises(ValueError, match="unique matching claim"):
        project(offer(), accepted() + [claim, dict(receipt, claim="other")], now=1601)


def test_retried_receipt_is_idempotent_but_conflicting_receipt_is_not():
    claim = event(4, "opportunity_claimed", observer="observer", claim="claim-1")
    receipt = event(5, "result_observed", observer="observer", claim="claim-1", receipt="receipt-1")
    retry = dict(receipt, seq=6, at=1601)
    out = project(offer(), accepted() + [claim, receipt, retry], now=1601)
    assert out["result_observed"] == {"claim": "claim-1", "receipt": "receipt-1", "at": 1005}
    assert out["execution"] == out["completion"] == "not_established"
    with pytest.raises(ValueError, match="conflicting receipt"):
        project(offer(), accepted() + [claim, receipt, dict(retry, receipt="receipt-2")], now=1601)


def test_preemption_closes_without_suppressing_or_reclassifying_later_input():
    rows = accepted() + [event(4, "preempted"),
                         event(5, "utterance", actor="being", beat="b2", text="Answering the newer request.")]
    out = project(offer(), rows, now=1010)
    assert out["terminal_reason"] == "preempted" and out["late_records"] == 1
    assert not out["eligible_to_claim"]


def test_persisted_claim_replays_once_but_proves_no_dispatch():
    claim = event(4, "opportunity_claimed", observer="observer", claim="claim-1")
    rows = accepted() + [claim, dict(claim)]
    restored = json.loads(json.dumps(rows))
    out = project(offer(), restored, now=1010)
    assert out["claim"] == {"id": "claim-1", "beat": "b1", "at": 1004}
    assert not out["eligible_to_claim"] and opportunity_context(offer(), restored, now=1010) is None
    assert out["execution"] == out["completion"] == "not_established"
    with pytest.raises(ValueError):
        project(offer(), rows + [event(5, "opportunity_claimed", observer="observer", claim="claim-2")], now=1010)


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
    rows[-1]["actor"] = "peer"
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
    assert out["terminal_reason"] == "deadline_presented"


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
