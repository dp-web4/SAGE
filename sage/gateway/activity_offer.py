"""Inert reference contract for #464; no model, dispatch, storage, or scheduling.

This projects an observer-owned event record, not untrusted model prose. It does
not authenticate authors or provide a durable lock. Runtime integration is held.
"""
from dataclasses import asdict, dataclass
import hashlib
import json


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 16384


def _time(value):
    # UTC epoch seconds. Reject bool, floats/NaN and ambiguous local timestamps.
    return type(value) is int and value >= 0


@dataclass(frozen=True)
class Offer:
    actor: str
    observer: str
    conversation: str
    sequence: int
    request: str
    opened_at: int
    deadline: int

    def __post_init__(self):
        if not all(_text(v) for v in (self.actor, self.observer, self.conversation, self.request)):
            raise ValueError("offer requires exact request, source and ownership")
        if type(self.sequence) is not int or self.sequence < 1:
            raise ValueError("source sequence must be a positive integer")
        if not (_time(self.opened_at) and _time(self.deadline) and self.deadline > self.opened_at):
            raise ValueError("offer requires an absolute future deadline")

    @property
    def request_sha256(self):
        return hashlib.sha256(self.request.encode("utf-8")).hexdigest()

    @property
    def id(self):
        raw = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_FIELDS = {
    "beat_started": {"beat"},
    "beat_finished": {"beat"},
    "utterance": {"actor", "text"},
    "disposition": {"actor", "decision"},
    "opportunity_claimed": {"observer", "claim"},
    "preempted": set(),
    "closed": set(),
}
_COMMON = {"seq", "at", "offer_id", "kind"}


def project(offer, events, *, now):
    """Replay up to 64 observer records; return evidence and advisory eligibility.

    Every record binds the whole offer, including actor, source and deadline.
    A claim is only a reserved opportunity: NOT an action, grant, or completion.
    Exact duplicate records are idempotent; conflicting sequence reuse is invalid.
    """
    if not isinstance(offer, Offer) or not _time(now) or now < offer.opened_at:
        raise ValueError("invalid offer or observation time")
    if not isinstance(events, list) or len(events) > 64:
        raise ValueError("requires a bounded event list")
    disposition = active = claimed = terminal = None
    beats, seen = [], {}
    last_seq, last_at, late = 0, offer.opened_at, 0
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("kind"), str):
            raise ValueError("event must be a typed object")
        kind = event["kind"]
        if kind not in _FIELDS or set(event) != _COMMON | _FIELDS[kind]:
            raise ValueError("unknown event kind or fields")
        seq, at = event["seq"], event["at"]
        if type(seq) is not int or seq < 1 or not _time(at):
            raise ValueError("invalid event sequence or timestamp")
        if event["offer_id"] != offer.id:
            raise ValueError("event belongs to another offer")
        if any(not _text(event[k]) for k in _FIELDS[kind]):
            raise ValueError("event fields must be nonempty bounded strings")
        if kind in ("disposition", "utterance") and event["actor"] != offer.actor:
            raise ValueError("event does not name the offered actor")
        if kind == "disposition" and event["decision"] not in ("accept", "defer", "decline"):
            raise ValueError("disposition must be explicit accept/defer/decline")
        if kind == "opportunity_claimed" and event["observer"] != offer.observer:
            raise ValueError("claim does not name the observer")
        if seq in seen:
            if seen[seq] != event:
                raise ValueError("conflicting event sequence reuse")
            continue
        if seq <= last_seq or at < last_at or at > now:
            raise ValueError("events must be ordered and not from the future")
        seen[seq], last_seq, last_at = dict(event), seq, at
        if terminal is not None or at >= offer.deadline:
            terminal = terminal or "deadline"
            late += 1
            continue
        if kind == "beat_started":
            if active is not None or event["beat"] in beats:
                raise ValueError("overlapping or reused beat identity")
            if len(beats) == 2:
                terminal = "beat_limit"
            else:
                active = event["beat"]
                beats.append(active)
        elif kind == "beat_finished":
            if active is None or event["beat"] != active:
                raise ValueError("finish must bind the active beat")
            active = None
            if len(beats) == 2:
                terminal = "beat_limit"
        elif kind == "disposition":
            if active is None:
                raise ValueError("disposition requires an ordinary beat")
            if disposition is not None and disposition != event["decision"]:
                raise ValueError("conflicting disposition; close and offer separately")
            disposition = event["decision"]
            if disposition != "accept":
                terminal = disposition
        elif kind == "opportunity_claimed":
            if active is None or disposition != "accept" or claimed is not None:
                raise ValueError("claim requires accepted work and one unused opportunity")
            claimed = {"id": event["claim"], "beat": active, "at": at}
        elif kind in ("preempted", "closed"):
            terminal = kind
        # utterance deliberately has no disposition/action semantics.
    if terminal is None and now >= offer.deadline:
        terminal = "deadline"
    return {
        "schema": "activity-offer-projection/v1", "offer_id": offer.id,
        "request_sha256": offer.request_sha256, "disposition": disposition,
        "beats_started": len(beats), "active_beat": active,
        "claim": claimed, "terminal_reason": terminal, "late_records": late,
        "eligible_to_claim": (terminal is None and active is not None
                              and disposition == "accept" and claimed is None),
        "execution": "not_established", "completion": "not_established",
    }


def opportunity_context(offer, events, *, now):
    """Exact payload for a *candidate* opportunity, not authorization to dispatch.

    The future adapter must durably claim and re-check preemption/deadline before
    calling the existing gated tool loop. Never dispatch directly from this value.
    """
    if not project(offer, events, now=now)["eligible_to_claim"]:
        return None
    return {"offer_id": offer.id, "conversation": offer.conversation,
            "sequence": offer.sequence, "request": offer.request,
            "request_sha256": offer.request_sha256, "disposition": "accept"}
