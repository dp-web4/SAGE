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
Forwarding uses the fleet's canonical sender, private-context/hub-mesh/hub-notify.sh
(operational channel key; validates kind/pointer gates) — the same path a human seat uses.
"""
from __future__ import annotations

import os
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


def _forward(row: Dict[str, Any], sender=None, plugin_id: str = "sprout-being") -> tuple[bool, str]:
    """Hand one row to the fleet mesh, signed as the member whose row it is when that
    member holds a hub identity here. Returns (accepted, detail)."""
    to = row.get("forward_on") or row.get("dest_peer_lct") or row.get("peer")
    kind = row.get("kind") or "coordination"
    ptr = row.get("pointer_uri") or row.get("pointer") or ""
    if not to or not ptr:
        return False, f"row missing forward_on/pointer_uri: {row}"
    if sender is not None:                       # injectable for tests
        return sender(str(to), str(kind), str(ptr))
    if not os.access(HUB_NOTIFY, os.X_OK):
        return False, f"hub-notify sender not available at {HUB_NOTIFY}"
    env_file, signed_as = hub_env_for(plugin_id)
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
    if not rows:
        return {"forwarded": 0, "failed": 0, "empty": True, "error": None,
                "signed_as": signed_as, "carrier": carrier}
    fwd = failed = 0
    for row in rows:
        rid = _row_id(row)
        ok, detail = _forward(row, sender, plugin_id=plugin_id)
        if ok:
            c.call("hestia_egress_pending", {"session_id": sid, "mark_forwarded": rid})
            fwd += 1; log(f"[egress] forwarded {rid} -> {row.get('forward_on')} ({detail[-80:]})")
        else:
            c.call("hestia_egress_pending", {"session_id": sid, "mark_failed": rid, "reason": detail[:200]})
            failed += 1; log(f"[egress] FAILED {rid}: {detail[-160:]}")
    return {"forwarded": fwd, "failed": failed, "empty": False, "error": None,
            "signed_as": signed_as, "carrier": carrier}


if __name__ == "__main__":
    r = drain_once()
    print(r)
    sys.exit(0 if r.get("error") is None else 1)
