"""
Refusal routing — wake the seat's auto session so the being's escalations are handled
AI-to-AI (dp, 2026-09-04: "seldom at the keyboard; the interaction should be ai-ai primarily").

A refused act is classified by its gate rule and routed:

  registry.*   bounded-registry refusal — by design, never escalated (the verb does not exist)
  mrh.*        SCOPE-class — the remedy the deny names is hestia_request_scope. We file it AS
               THE BEING (once per path), write an escalation note, and wake the seat. The seat
               rules it under an operator delegation when it holds one (hestia #952/#962:
               `hestia scope arbitrate <request_id> --grant|--deny --reason '…' --as <seat>`,
               which signs with the seat's registry key and calls hestia_scope_arbitrate; the
               grant is STANDING; NOT-SAME and the delegation's path/member bound are enforced
               by the daemon). With no delegation covering the path, the daemon refuses by name
               (hestia.scope_arbitrate_undelegated) and the request stays in dp's queue with the
               seat's recommendation attached.
  society.*    a law verdict, not an approval; appealable — noted for the seat (hestia_appeal
               shape pending), never auto-overridden.
  <escalation> a governance-write escalation named in the deny — a NOT-SAME peer may arbitrate
               (hestia_gate_arbitrate_escalation); the seat is woken to rule within the
               guardrails below.

The wake-up is the fleet's own mechanism: a routed mesh notice to the seat's hub mailbox
(<seat>/claude-code; the seat is the being's own machine, read from its identity.json, else the
member's prefix — legion-being wakes legion) with kind=coordination and a pointer to the note; hub-watch drains it
and fires a headless session with the note as the task. The note carries the ARBITER PROTOCOL
so any fired session can act without new skills:

  Approve only if ALL hold: the effector is in the being's bounded registry; the target is
  inside the being's own instance dir or a named fleet peer; no secret/credential/egress
  surface is touched; the act is reversible. Otherwise leave it for dp and say so in the
  thread. Always record the decision with a reason.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from sage.gateway.being_gate_client import BeingGateClient, BeingIntent, ResultEnvelope, _REGISTRY
from sage.gateway.hestia_witness import _ENDPOINT, _Mcp, _unwrap

NOTE_DIR = os.path.expanduser("~/ai-workspace/shared-context/escalations")
# the gate workspace: this checkout (governed_turn/heartbeat use the same root). Not a
# hard-coded ~/ai-workspace/sage — Legion's checkout is ~/ai-workspace/SAGE (case matters).
WORKSPACE = str(Path(__file__).resolve().parents[2])


def seat_for(member: str, memory_root: Optional[str] = None) -> str:
    """The seat that arbitrates this being: its own machine. identity.json `identity.machine`
    when the instance carries one, else the member prefix (`legion-being` -> `legion`).
    Sprout's first cut defaulted to 'sprout' for every seat; that wakes the wrong mailbox."""
    if memory_root:
        try:
            ident = json.loads(Path(memory_root, "identity.json").read_text()).get("identity", {})
            m = str(ident.get("machine") or "").strip().lower()
            if m:
                return m
        except Exception:
            pass
    return (member or "").split("-")[0].strip().lower() or "unknown"
_ESC_ID = re.compile(r"\b(esc-[0-9a-f]{6,}|escalation[-_ ]id[:= ]+([A-Za-z0-9-]+))")


def classify(env: ResultEnvelope) -> str:
    v = env.verdict
    rule = (v.rule if v else "") or ""
    reason = (v.reason if v else "") or (env.error or "")
    if rule.startswith("registry."):
        return "registry"
    if _ESC_ID.search(reason or ""):
        return "governance"
    if rule.startswith("mrh."):
        return "scope"
    if rule.startswith("society."):
        return "society"
    return "other"


def _scope_path(intent: BeingIntent, memory_root: str) -> str:
    """The path to ask reach for. A target INSIDE the being's own instance dir always asks for
    the instance root: one STANDING grant on the home covers journal.md, notes/x.md, all of it,
    and the arbiter's recommendation is the home dir in every such case anyway. Asking for the
    target's own directory filed a per-subdir request (`notes/` for a refused `notes/x.md`;
    Legion, SAGE#38 review). Outside the home: the target's directory, or the target itself
    when it has no extension (a directory)."""
    p = intent.args.get("path") or ""
    p = os.path.abspath(os.path.expanduser(p if os.path.isabs(p) else os.path.join(memory_root, p)))
    root = os.path.abspath(os.path.expanduser(memory_root))
    if p == root or p.startswith(root.rstrip(os.sep) + os.sep):
        return root
    return os.path.dirname(p) if os.path.splitext(p)[1] else p


def _file_scope_request(member: str, path: str, why: str, endpoint: str) -> Dict[str, Any]:
    m = _Mcp(endpoint, member); m.init()
    conn = _unwrap(m.call("hestia_connect", {"plugin_id": member, "host_agent": "sage-escalate",
                                              "host_agent_version": "sage", "requested_role": "citizen"}))
    sid = conn.get("sessionId")
    st = _unwrap(m.call("hestia_scope_status", {"plugin_id": member, "session_id": sid}))
    for r in st.get("requests") or []:
        if r.get("status") == "pending" and (r.get("path") or "").rstrip("/") == path.rstrip("/"):
            return {"request_id": r.get("request_id") or r.get("id"), "status": "already_pending"}
    r = _unwrap(m.call("hestia_request_scope", {"plugin_id": member, "path": path, "reason": why[:400], "session_id": sid}))
    if "_hestia_error" in r:
        return {"error": r["_hestia_error"]}
    return {"request_id": r.get("request_id"), "status": r.get("status"), "expires_at": r.get("expires_at")}


def write_note(member: str, intent: BeingIntent, env: ResultEnvelope, kind: str, extra: Dict[str, Any]) -> str:
    Path(NOTE_DIR).mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%d-%H%M%S")
    stem = f"{member}-{kind}-{intent.effector}-{ts}"
    p = Path(NOTE_DIR) / f"{stem}.md"
    n = 1
    while p.exists():   # two refusals in one second must not overwrite each other (Sprout, #38 review)
        n += 1
        p = Path(NOTE_DIR) / f"{stem}-{n}.md"
    v = env.verdict
    protocol = (
        "## Arbiter protocol (for the seat's auto session)\n"
        "Approve ONLY if all hold: (1) the effector is in the being's bounded registry; (2) the target is inside the\n"
        "being's own instance dir or a named fleet peer; (3) no secret/credential/egress surface; (4) reversible.\n"
        "Otherwise leave it for dp and say so in the thread. Record every decision with a reason.\n")
    body = (f"---\nkind: {kind}\nmember: {member}\neffector: {intent.effector}\nrule: {v.rule if v else ''}\n"
            f"stage: {v.stage if v else ''}\nts: {ts}\n---\n\n# {member}: {kind} — `{intent.effector}` refused\n\n"
            f"**intent**: `{intent.effector}({json.dumps(intent.args)[:300]})`\n\n"
            f"**verdict**: {v.decision if v else '?'} / {v.rule if v else ''} — {(v.reason if v else env.error or '')[:500]}\n\n"
            f"**routing**: {json.dumps(extra)[:600]}\n\n")
    how = {
        "scope": ("## What the seat can do now\n- Pre-review: is the path inside the being's own memory and does the protocol below hold?\n"
                  "- If yes, RULE it (hestia #952): `hestia scope arbitrate <request_id> --grant --reason '<why>' --as claude-code`\n"
                  "  (signs with this seat's registry key; the grant is STANDING; `--deny` to refuse). Use the request_id in\n"
                  "  the routing line above. The daemon refuses by name if you are the asker (scope_arbitrate_self) or hold\n"
                  "  no operator delegation covering this path+member (scope_arbitrate_undelegated): then leave it for dp\n"
                  "  with your recommendation, and say so in the thread. Do not fabricate a grant.\n"
                  "- The being sees the ruling on its next beat via hestia_scope_status (decided_by = delegate:<seat>).\n"),
        "governance": ("## What the seat can do now\n- `hestia_gate_pending_escalations` (pass your session) — if you_may_rule and the protocol holds, rule it:\n"
                       "  MCP `hestia_gate_arbitrate_escalation {escalation_id, approve: true|false, reason}` or\n"
                       "  `hestia gate approve|deny <id> --as claude-code --reason '<why>'`. No delegation needed (NOT-SAME peer).\n"),
        "society": ("## What the seat can do now\n- A law verdict. If plainly wrong, open an appeal on the being's behalf and corroborate; never override.\n"),
    }.get(kind, "")
    p.write_text(body + how + "\n" + protocol)
    return str(p)


def wake_seat(member: str, note_path: str, memory_root: str, seat: Optional[str] = None,
              endpoint: str = _ENDPOINT) -> Dict[str, Any]:
    """Routed mesh notice to the seat's own hub mailbox; hub-watch drains it and fires a session."""
    seat = seat or seat_for(member, memory_root)
    from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
    from sage.gateway import egress_drain
    inst_identity = os.path.join(memory_root, "identity.json")
    client = BeingGateClient(member, inst_identity, WORKSPACE,
                             dispatcher=HestiaF1aDispatcher(member, memory_root=memory_root, endpoint=endpoint))
    ptr = note_path
    i = ptr.find("shared-context/")
    if i >= 0:
        ptr = ptr[i:]
    env = client.dispatch(BeingIntent("mesh", {"to": seat, "kind": "coordination", "pointer_uri": ptr}))
    drained = egress_drain.drain_once(plugin_id=member, endpoint=endpoint, log=lambda *_: None) if env.ok else None
    return {"notified": env.ok, "seat": seat, "witness_id": env.witness_id, "error": env.error, "drain": drained, "pointer": ptr}


def escalate(member: str, intent: BeingIntent, env: ResultEnvelope, memory_root: str,
             seat: Optional[str] = None, endpoint: str = _ENDPOINT, wake: bool = True) -> Dict[str, Any]:
    """Route one refusal. Returns what was filed/notified; never raises into the being's turn.
    wake=False files the scope request only: no note, no mesh notice (the heartbeat's second and
    later refusals of a kind in one beat)."""
    kind = classify(env)
    out: Dict[str, Any] = {"kind": kind, "effector": intent.effector}
    if kind in ("registry", "other"):
        out["escalated"] = False
        out["why"] = "bounded-registry refusal is final by design" if kind == "registry" else "no remedy named"
        return out
    try:
        if kind == "scope":
            path = _scope_path(intent, memory_root)
            why = (f"{member} was refused {intent.effector} at {path} ({env.verdict.rule if env.verdict else ''}). "
                   f"Its seat's auto session will rule it under delegation if it holds one (hestia #952), "
                   f"else please rule as STANDING if it is the being's own memory.")
            out["scope_request"] = _file_scope_request(member, path, why, endpoint)
        # The note exists to be pointed at by the wake. Without a wake there is no reader, and a
        # beat with nine refused home writes would leave nine near-identical notes (Sprout, #38
        # review); the scope request above is still filed (the daemon dedups it on the path).
        if wake:
            note = write_note(member, intent, env, kind, out)
            out["note"] = note
            out["wake"] = wake_seat(member, note, memory_root, seat=seat, endpoint=endpoint)
        out["escalated"] = True
    except Exception as e:
        out["escalated"] = False
        out["error"] = f"{type(e).__name__}: {e}"
    return out
