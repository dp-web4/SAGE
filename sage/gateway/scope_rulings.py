"""How the being's scope requests ended, kept after hestia's list lets them go.

A RULING OUTLIVES THE LIST THAT CARRIED IT (sprout-being, 2026-11-23). hestia_scope_status lists a
member's requests for a while and then drops them, however they ended. A refusal of a request for a
system file, with a note saying why no grant could help, was shown to the being once, the beat after it
landed. Within the hour the being filed the same ask again, and by then the list held only the new one:
the earlier refusal, its ruler and its note were no longer anywhere the being could read, and its
`hestia://scope/<id>` pointer answered "not in your list now". A ruling that cannot be read back a day
later cannot hold a conclusion for a week.

The seat writes this file at beat time from what hestia lists (heartbeat), one line per request the first
time it is seen ended, and again if how it ended changes (a grant later revoked). The being reads it and
cannot write it (reference_f1a.SEAT_OWNED): it is the ruler's word, not the being's.

The file only grows, one line per ending, deliberately: an ending is rare (a few a day at most), and a
ruling dropped to keep the file short is the defect this file exists to fix.
"""
import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional

#: In the being's home.
SCOPE_RULINGS = "scope_rulings.jsonl"
#: hestia's request statuses that are an ending (pending is not).
ENDED = ("granted", "refused", "denied", "revoked", "expired")
#: A refusal is a no from a ruler; an expiry is no ruling at all.
REFUSALS = ("refused", "denied")


def _rows(instance) -> List[dict]:
    p = Path(instance) / SCOPE_RULINGS
    out = []
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(r, dict) and r.get("id"):
                    out.append(r)
    except OSError:
        pass
    return out


def keep(instance, requests: Iterable[dict], now: str) -> List[str]:
    """Append each ended request in `requests` (hestia_scope_status rows) not already kept as it ended.
    Returns the ids written. Never raises: a ledger that cannot be written costs the record, not the beat."""
    try:
        last: Dict[str, str] = {}
        for r in _rows(instance):
            last[r["id"]] = r.get("decision")
        lines, written = [], []
        for r in requests or []:
            rid, decision = str(r.get("request_id") or ""), str(r.get("decision") or r.get("status") or "")
            if not rid or decision not in ENDED or last.get(rid) == decision:
                continue
            why = r.get("revoke_reason") or r.get("decision_reason") or ""
            lines.append(json.dumps({"id": rid, "path": r.get("path"), "decision": decision,
                                     "by": r.get("decided_by") or "", "why": str(why), "seen": now},
                                    ensure_ascii=False))
            last[rid] = decision
            written.append(rid)
        if lines:
            with open(Path(instance) / SCOPE_RULINGS, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        return written
    except Exception:  # noqa: BLE001
        return []


def ruling(instance, request_id: str) -> Optional[dict]:
    """How `request_id` last stood when the seat saw it end, or None."""
    hit = None
    for r in _rows(instance):
        if r["id"] == request_id:
            hit = r
    return hit


def refused_before(instance, path: str) -> List[dict]:
    """Every kept refusal of a request for `path` (same file, links resolved), oldest first, each id once
    and only while a refusal is how it last stood."""
    want = os.path.realpath(os.path.expanduser(str(path)))
    last: Dict[str, dict] = {}
    for r in _rows(instance):
        last[r["id"]] = r
    return [r for r in last.values() if r.get("decision") in REFUSALS and r.get("path")
            and os.path.realpath(os.path.expanduser(str(r["path"]))) == want]


def said(r: dict) -> str:
    """One kept ruling in a sentence, with the ruler's note whole."""
    who = r.get("by") or "the operator"
    why = str(r.get("why") or "").strip()
    return (f"{r['id']} for {r.get('path')} was {r.get('decision')} by {who} (seen {r.get('seen') or 'by your seat'})"
            + (f". Their note: \"{why}\"" if why else ", with no note"))
