"""
Egress drain — the forwarding plane's worker (hestia r6-routing branch 2).

Notices a LOCAL member addresses `peer/member` are queued by the daemon; nothing leaves the
machine until a drain forwards each row to the fleet mesh and REPORTS the outcome. Legion's
hub-watch is the reference; Sprout's lacked this branch, so the being's mesh/peer_ask acts
would have sat queued forever. This closes that.

Contract (hestia_egress_pending, attributed caller):
  * list `pending` rows; each carries an id, `forward_on` (an LCT is roster-validated; a NAME
    is prefix-resolved by hub-notify) + `forward_on_is_lct`, kind, pointer_uri, attempts.
  * on_success: report `mark_forwarded:<id>` — the MESH accepted it (not read-by-recipient).
  * on_failure: report `mark_failed:<id>` with `reason:<text>`; a failed row left pending
    never increments attempts, the bound never fires, the sender is never told.
  * max_attempts 5. Never silence: check `_hestia_error` before concluding the queue is empty.
  * hestia #1030: a row carrying `transport` is signed by its stamped `carrier_lct` and by
    nothing else. With no key here for that carrier the drain sends nothing and reports
    `mark_failed` with `fault: "carrier_unavailable"` (the daemon retires it as a local fault
    and tells the author). Every `mark_forwarded` names the carrier that signed (`carrier_lct`)
    and what the hub returned (`hub_receipt`). A row with `transport: null` is unbound: the
    being's own identity when it holds one, else the seat, as before, but always reported.
Forwarding uses the fleet's canonical sender, private-context/hub-mesh/hub-notify.sh
(operational channel key; validates kind/pointer gates) — the same path a human seat uses.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional

from sage.gateway.hestia_witness import _ENDPOINT, _Mcp, _unwrap

HUB_NOTIFY = os.path.expanduser("~/ai-workspace/private-context/hub-mesh/hub-notify.sh")


def _row_id(r: Dict[str, Any]) -> Optional[int]:
    """The daemon parses mark_forwarded/mark_failed with `as_u64()` — a string id is
    silently ignored and the row re-forwards every drain (measured: row 2 sent twice)."""
    for k in ("id", "queued_id", "notice_id", "noticeId", "row_id"):
        if r.get(k) is not None:
            try:
                return int(r[k])
            except (TypeError, ValueError):
                return None
    return None


def hub_env_for(plugin_id: str) -> tuple[Optional[str], str]:
    """Which hub identity signs this member's rows. The being's own env file
    (~/.config/hub-mesh-<plugin_id>.env: same hub and client, the being's LCT and keypair)
    when it exists, else the seat's default and a loud 'seat' label. dp 2026-09-05: the
    being's channel is the being's; Legion measured that at the hub every being notice
    had been a seat send because hub-notify signs with the seat's key."""
    p = os.path.expanduser(f"~/.config/hub-mesh-{plugin_id}.env")
    if os.path.isfile(p):
        return p, "being"
    return None, "seat"


def _env_lct(path: Optional[str]) -> Optional[str]:
    """The MY_LCT a hub-mesh env file signs as, or None."""
    if not path:
        return None
    try:
        for line in open(path):
            s = line.strip()
            if s.startswith("MY_LCT"):
                return s.split("=", 1)[1].split("#", 1)[0].strip().strip('"').strip("'") or None
    except Exception:
        return None
    return None


def seat_env_path() -> str:
    """The seat's default hub identity: what hub-notify sources when HUB_MESH_ENV is unset."""
    return os.environ.get("HUB_MESH_ENV") or os.path.expanduser("~/.config/hub-mesh" + ".env")


def signer_for(row: Dict[str, Any], plugin_id: str) -> tuple[Optional[str], str, Optional[str], Optional[str]]:
    """Which identity signs this row: (env_file, signed_as, carrier_lct, refusal).

    A STAMPED row (hestia #1030) names its carrier; only an env file whose MY_LCT is that
    carrier may sign it, and with none the answer is a refusal, never another key. An UNBOUND
    row keeps the old choice (the being's own file, else the seat) and names the carrier it
    picked, so the daemon's witness records it."""
    being_env, _ = hub_env_for(plugin_id)
    seat_env = seat_env_path()
    seat_env = seat_env if os.path.isfile(seat_env) else None
    transport = row.get("transport")
    if isinstance(transport, dict):
        want = str(transport.get("carrier_lct") or "").strip()
        if not want:
            return None, "none", None, f"row stamped mode={transport.get('mode')} names no carrier_lct"
        for env_file, label in ((being_env, "being"), (seat_env, "seat")):
            lct = _env_lct(env_file)
            if lct and lct.lower() == want.lower():
                return env_file, label, lct, None
        return None, "none", None, (f"no hub identity on this host signs as the stamped carrier {want}; "
                                    "not sending under another identity")
    if being_env:
        return being_env, "being", _env_lct(being_env), None
    return None, "seat", _env_lct(seat_env), None


def _hub_receipt(detail: str) -> Optional[Dict[str, str]]:
    m = re.search(r"ledger=(\S+)", detail or "")
    return {"ledger": m.group(1)} if m and m.group(1) != "?" else None


def _forward(row: Dict[str, Any], sender=None, plugin_id: str = "sprout-being",
             env_file: Optional[str] = None, signed_as: Optional[str] = None) -> tuple[bool, str]:
    """Hand one row to the fleet mesh under the signer `signer_for` chose. Returns
    (accepted, detail)."""
    to = row.get("forward_on") or row.get("dest_peer_lct") or row.get("peer")
    kind = row.get("kind") or "coordination"
    ptr = row.get("pointer_uri") or row.get("pointer") or ""
    if not to or not ptr:
        return False, f"row missing forward_on/pointer_uri: {row}"
    if sender is not None:                       # injectable for tests
        return sender(str(to), str(kind), str(ptr))
    if not os.access(HUB_NOTIFY, os.X_OK):
        return False, f"hub-notify sender not available at {HUB_NOTIFY}"
    if signed_as is None:
        env_file, signed_as, _, _ = signer_for(row, plugin_id)
    env = dict(os.environ)
    if env_file:
        env["HUB_MESH_ENV"] = env_file
    p = subprocess.run([HUB_NOTIFY, str(to), str(kind), str(ptr)], capture_output=True, text=True, timeout=60, env=env)
    out = (p.stdout + p.stderr).strip()
    return (p.returncode == 0 and "ledger=" in out), f"signed_as={signed_as} " + out[-300:]


def drain_once(plugin_id: str = "sprout-being", host_agent: str = "sage-egress-drain",
               endpoint: str = _ENDPOINT, mcp=None, sender=None, log=print) -> Dict[str, Any]:
    """One attributed drain pass. Returns {forwarded, failed, empty, error, signed_as, carrier}.

    `signed_as` is the CARRIER: which hub identity's key signed the envelope ("being" when the
    member holds `~/.config/hub-mesh-<plugin_id>.env`, else "seat"). It rides the summary
    because the record is where a reader checks: hestia #1030 (cbp, 2026-09-15) measured that
    the chain says the being forwarded, the hub says the seat signed, and the only place the
    carrier appeared was a detail string this function threw away."""
    # The carrier, resolved BEFORE any return path: every summary says which hub identity
    # would sign, including the passes that forward nothing (hestia #1030).
    env_file, signed_as = hub_env_for(plugin_id)
    carrier = None
    if env_file:
        try:
            for line in open(env_file):
                if line.strip().startswith("MY_LCT"):
                    carrier = line.split("=", 1)[1].split("#", 1)[0].strip().strip('"').strip("'")
                    break
        except Exception:
            pass
    c = mcp
    if c is None:
        c = _Mcp(endpoint, plugin_id); c.init()
    conn = _unwrap(c.call("hestia_connect", {"plugin_id": plugin_id, "host_agent": host_agent,
                                              "host_agent_version": "sage", "requested_role": "citizen"}))
    if "_hestia_error" in conn:
        return {"forwarded": 0, "failed": 0, "empty": False, "error": conn["_hestia_error"],
                "signed_as": signed_as, "carrier": carrier}
    sid = conn.get("sessionId")
    q = _unwrap(c.call("hestia_egress_pending", {"session_id": sid}))
    if "_hestia_error" in q:                     # never confuse "refused" with "empty"
        return {"forwarded": 0, "failed": 0, "empty": False, "error": q["_hestia_error"],
                "signed_as": signed_as, "carrier": carrier}
    rows: List[Dict[str, Any]] = q.get("pending") or []
    # Rows the daemon failed before handing them out (a binding changed while they waited):
    # nothing to send, but the beat record says so, beside the rows that were sent.
    faults: List[Dict[str, Any]] = [
        {"row_id": r.get("row_id"), "fault": r.get("fault"), "reported_to": r.get("reported_to")}
        for r in (q.get("transport_refused") or []) if isinstance(r, dict)]
    if not rows:
        return {"forwarded": 0, "failed": 0, "empty": not faults, "error": None,
                "signed_as": signed_as, "carrier": carrier, "transport_faults": faults}
    fwd = failed = 0
    for row in rows:
        rid = _row_id(row)
        env_file, row_signed_as, row_carrier, refusal = signer_for(row, plugin_id)
        if refusal:
            res = _unwrap(c.call("hestia_egress_pending", {"session_id": sid, "mark_failed": rid,
                                                           "fault": "carrier_unavailable", "reason": refusal[:200]}))
            failed += 1; log(f"[egress] NOT SENT {rid}: {refusal}")
            faults.append({"row_id": rid, "fault": "carrier-unavailable", "detail": refusal,
                           "reported_to": res.get("reported_to")})
            continue
        ok, detail = _forward(row, sender, plugin_id=plugin_id, env_file=env_file, signed_as=row_signed_as)
        if ok:
            mark: Dict[str, Any] = {"session_id": sid, "mark_forwarded": rid}
            if row_carrier:
                mark["carrier_lct"] = row_carrier
            receipt = _hub_receipt(detail)
            if receipt:
                mark["hub_receipt"] = receipt
            res = _unwrap(c.call("hestia_egress_pending", mark))
            if res.get("fault"):          # the daemon judged the carrier and refused the success
                failed += 1; faults.append({"row_id": rid, "fault": res.get("fault"),
                                            "reported_to": res.get("reported_to")})
                log(f"[egress] sent {rid} but NOT a forwarded success: {res.get('fault')}")
            else:
                fwd += 1; log(f"[egress] forwarded {rid} -> {row.get('forward_on')} as {row_signed_as} ({detail[-80:]})")
        else:
            c.call("hestia_egress_pending", {"session_id": sid, "mark_failed": rid, "reason": detail[:200]})
            failed += 1; log(f"[egress] FAILED {rid}: {detail[-160:]}")
    return {"forwarded": fwd, "failed": failed, "empty": False, "error": None,
            "signed_as": signed_as, "carrier": carrier, "transport_faults": faults}


if __name__ == "__main__":
    r = drain_once()
    print(r)
    sys.exit(0 if r.get("error") is None else 1)
