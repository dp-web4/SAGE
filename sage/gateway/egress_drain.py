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
    """Whether this member holds its own hub identity file here. Not how a row's signer is
    chosen any more (that is `signer_for`, per row); kept for callers that ask the question.
    Historically: which hub identity signs this member's rows. The being's own env file
    (~/.config/hub-mesh-<plugin_id>.env: same hub and client, the being's LCT and keypair)
    when it exists, else the seat's default and a loud 'seat' label. dp 2026-09-05: the
    being's channel is the being's; Legion measured that at the hub every being notice
    had been a seat send because hub-notify signs with the seat's key."""
    p = os.path.expanduser(f"~/.config/hub-mesh-{plugin_id}.env")
    if os.path.isfile(p):
        return p, "being"
    return None, "seat"


# The variables hub-notify.sh reads to decide who signs. They are stripped from the
# environment of both the resolver and the send, so the env FILE is the only thing that
# decides: an inherited MY_LCT cannot make the shell sign as someone the resolver never saw.
_SIGNER_VARS = ("MY_LCT", "MY_KEYPAIR", "CHANNEL_CLIENT", "HUB_URL", "HUB_MESH_ENV", "HUB_MESH_STATE")


def _clean_env() -> Dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _SIGNER_VARS}


def _env_lct(path: Optional[str]) -> Optional[str]:
    """The MY_LCT a hub-mesh env file signs as, read the way hub-notify.sh reads it: by
    SOURCING the file in bash (SAGE #97 review). A Python parser of shell assignments
    disagrees with the shell on prefixes (`MY_LCT_OLD=`), duplicates (first vs last),
    `export` and quoting, and any disagreement certifies an identity the send does not
    use: #1030 again. Sourcing cannot disagree with sourcing. None when the file is absent,
    fails to source, or sets no MY_LCT."""
    if not path or not os.path.isfile(path):
        return None
    try:
        p = subprocess.run(
            ["bash", "-c", 'source "$1" >/dev/null 2>&1 || exit 3; printf %s "${MY_LCT-}"', "_", path],
            capture_output=True, text=True, timeout=10, env=_clean_env())
    except Exception:
        return None
    lct = p.stdout.strip()
    return lct if p.returncode == 0 and lct else None


def seat_env_path() -> str:
    """The seat's default hub identity: what hub-notify sources when HUB_MESH_ENV is unset."""
    return os.environ.get("HUB_MESH_ENV") or os.path.expanduser("~/.config/hub-mesh" + ".env")


def _member_env_path(member: str) -> str:
    return os.path.expanduser(f"~/.config/hub-mesh-{member}.env")


def identity_inventory(author: Optional[str] = None) -> List[tuple[str, str]]:
    """Every hub identity file on this host, as (path, label), in preference order: the row's
    AUTHOR's own file, then the seat's, then every other member file. Row-scoped (SAGE #97
    review): the drain lists the whole forwarding plane, so the member running the drain is
    not the member whose row it is.

    EXECUTION NOTE (review round 2, not yet contained): resolving a stamped carrier SOURCES
    each candidate file in turn until one matches, which widens execution from "the chosen
    identity file" (what hub-notify already sources) to "every identity file on the host".
    Same trust class, since these files are shell config the send path executes anyway, but a
    wider one. The containment is a declarative identity inventory (LCT -> file) that a
    search can read without executing anything."""
    out: List[tuple[str, str]] = []
    if author and os.path.isfile(_member_env_path(author)):
        out.append((_member_env_path(author), "being"))
    seat = seat_env_path()
    if os.path.isfile(seat):
        out.append((seat, "seat"))
    cfg = os.path.expanduser("~/.config")
    try:
        names = sorted(os.listdir(cfg))
    except OSError:
        names = []
    prefix, suffix = "hub-mesh-", ".env"
    for n in names:
        full = os.path.join(cfg, n)
        if n.startswith(prefix) and n.endswith(suffix) and full not in {x for x, _ in out}:
            out.append((full, "member:" + n[len(prefix):-len(suffix)]))
    return out


def signer_for(row: Dict[str, Any], plugin_id: str) -> tuple[Optional[str], str, Optional[str], Optional[str]]:
    """Which identity signs THIS row: (env_file, signed_as, carrier_lct, refusal).

    Decided per row, from the row (SAGE #97 review). `plugin_id` is only the drainer's hestia
    attribution; the row's own `from_plugin` is the author.

    * STAMPED (hestia #1030): the first identity file on this host whose sourced MY_LCT is
      the stamped carrier signs it, whichever member that file belongs to (a relay's carrier
      need not be the author or the seat). None matching is a refusal, never another key.
    * UNBOUND: the author's own file, else the seat, as before, naming the carrier chosen."""
    author = str(row.get("from_plugin") or plugin_id)
    inventory = identity_inventory(author)
    transport = row.get("transport")
    if isinstance(transport, dict):
        want = str(transport.get("carrier_lct") or "").strip()
        if not want:
            return None, "none", None, f"row stamped mode={transport.get('mode')} names no carrier_lct"
        for env_file, label in inventory:
            lct = _env_lct(env_file)
            if lct and lct.lower() == want.lower():
                return env_file, label, lct, None
        return None, "none", None, (f"no hub identity on this host signs as the stamped carrier {want}; "
                                    "not sending under another identity")
    for env_file, label in inventory:
        if label in ("being", "seat"):
            return env_file, label, _env_lct(env_file), None
    return None, "seat", None, None


def _hub_receipt(detail: str) -> Optional[Dict[str, str]]:
    m = re.search(r"ledger=(\S+)", detail or "")
    return {"ledger": m.group(1)} if m and m.group(1) != "?" else None


def _forward(row: Dict[str, Any], sender=None, plugin_id: str = "sprout-being",
             env_file: Optional[str] = None, signed_as: Optional[str] = None) -> tuple[bool, str]:
    """Hand one row to the fleet mesh under the signer `signer_for` chose. Returns
    (accepted, detail). The env file is passed EXPLICITLY as HUB_MESH_ENV with the signer
    variables stripped, so the shell sources exactly the file the resolver read."""
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
    if not env_file:
        return False, "no hub identity file to sign with on this host"
    env = _clean_env()
    env["HUB_MESH_ENV"] = env_file
    p = subprocess.run([HUB_NOTIFY, str(to), str(kind), str(ptr)], capture_output=True, text=True, timeout=60, env=env)
    out = (p.stdout + p.stderr).strip()
    return (p.returncode == 0 and "ledger=" in out), f"signed_as={signed_as} " + out[-300:]


def drain_once(plugin_id: str = "sprout-being", host_agent: str = "sage-egress-drain",
               endpoint: str = _ENDPOINT, mcp=None, sender=None, log=print) -> Dict[str, Any]:
    """One attributed drain pass. Returns {forwarded, failed, unsettled, empty, error,
    forwarded_rows, transport_faults, drainer_default_identity}.

    WHO CARRIED EACH ACT IS A PER-ROW FACT (SAGE #97 review, round 2). The signer is chosen per
    row (the author's identity, a stamped carrier, possibly a relay courier), so a single
    pass-level `signed_as`/`carrier` would be false by construction whenever the drain carries
    a row for a member other than the one running it. Every row this pass handled is recorded
    with its own `from_plugin`, `carrier_lct`, `signed_as` and `hub_receipt`, in
    `forwarded_rows` or `transport_faults`. The record is where a reader checks: hestia #1030
    measured that the chain said the being forwarded while the hub said the seat signed.

    `drainer_default_identity` is what an UNBOUND row authored by the member running the drain
    would sign as, resolved through the same shell-sourcing path as a real send. It is a fact
    about this host's configuration, present even on passes that forward nothing, and it is
    NOT a claim about who signed any row."""
    d_env, d_label, d_lct, _ = signer_for({"from_plugin": plugin_id, "transport": None}, plugin_id)
    default_identity = {"member": plugin_id, "signed_as": d_label if d_env else "none", "carrier_lct": d_lct}
    c = mcp
    if c is None:
        c = _Mcp(endpoint, plugin_id); c.init()
    conn = _unwrap(c.call("hestia_connect", {"plugin_id": plugin_id, "host_agent": host_agent,
                                              "host_agent_version": "sage", "requested_role": "citizen"}))
    if "_hestia_error" in conn:
        return {"forwarded": 0, "failed": 0, "empty": False, "error": conn["_hestia_error"],
                "forwarded_rows": [], "transport_faults": [], "drainer_default_identity": default_identity}
    sid = conn.get("sessionId")
    q = _unwrap(c.call("hestia_egress_pending", {"session_id": sid}))
    if "_hestia_error" in q:                     # never confuse "refused" with "empty"
        return {"forwarded": 0, "failed": 0, "empty": False, "error": q["_hestia_error"],
                "forwarded_rows": [], "transport_faults": [], "drainer_default_identity": default_identity}
    rows: List[Dict[str, Any]] = q.get("pending") or []
    # Rows the daemon failed before handing them out (a binding changed while they waited):
    # nothing to send, but the beat record says so, beside the rows that were sent.
    faults: List[Dict[str, Any]] = [
        {"row_id": r.get("row_id"), "fault": r.get("fault"), "reported_to": r.get("reported_to")}
        for r in (q.get("transport_refused") or []) if isinstance(r, dict)]
    if not rows:
        return {"forwarded": 0, "failed": 0, "unsettled": 0, "empty": not faults, "error": None,
                "forwarded_rows": [], "transport_faults": faults, "drainer_default_identity": default_identity}
    fwd = failed = unsettled = 0
    forwarded_rows: List[Dict[str, Any]] = []
    for row in rows:
        rid = _row_id(row)
        env_file, row_signed_as, row_carrier, refusal = signer_for(row, plugin_id)
        who = {"row_id": rid, "from_plugin": row.get("from_plugin"), "carrier_lct": row_carrier,
               "signed_as": row_signed_as}
        if refusal:
            res = _unwrap(c.call("hestia_egress_pending", {"session_id": sid, "mark_failed": rid,
                                                           "fault": "carrier_unavailable", "reason": refusal[:200]}))
            failed += 1; log(f"[egress] NOT SENT {rid}: {refusal}")
            faults.append(dict(who, fault="carrier-unavailable", detail=refusal,
                               reported_to=res.get("reported_to")))
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
                failed += 1; faults.append(dict(who, fault=res.get("fault"), hub_receipt=receipt,
                                                reported_to=res.get("reported_to")))
                log(f"[egress] sent {rid} but NOT a forwarded success: {res.get('fault')}")
            elif "_hestia_error" in res or not res:
                # The hub took it, but hestia did not settle the row (refused, errored, or said
                # nothing): the row may still be pending and the next pass may send it again.
                # Not a clean forward, and not silent (SAGE #97 review).
                unsettled += 1
                faults.append(dict(who, fault="sent-but-unsettled", hub_receipt=receipt,
                                   detail=res.get("_hestia_error") if res else "empty response"))
                log(f"[egress] sent {rid} but hestia did not settle it: {res}")
            else:
                forwarded_rows.append(dict(who, hub_receipt=receipt))
                fwd += 1; log(f"[egress] forwarded {rid} -> {row.get('forward_on')} as {row_signed_as} ({detail[-80:]})")
        else:
            c.call("hestia_egress_pending", {"session_id": sid, "mark_failed": rid, "reason": detail[:200]})
            failed += 1; log(f"[egress] FAILED {rid}: {detail[-160:]}")
    return {"forwarded": fwd, "failed": failed, "unsettled": unsettled, "empty": False, "error": None,
            "forwarded_rows": forwarded_rows, "transport_faults": faults,
            "drainer_default_identity": default_identity}


if __name__ == "__main__":
    r = drain_once()
    print(r)
    sys.exit(0 if r.get("error") is None else 1)
