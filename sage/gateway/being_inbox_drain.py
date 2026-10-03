"""
being_inbox_drain — the inbound half of being-to-being (PRD_ONE_BEING_ONE_EXPERIENCE S4).

A being holds its own hub identity (admitted member, own channel key). Notices addressed
to that identity land in a hub mailbox that nothing drained: hub-watch drains only the
seat's. This drain is the courier:

  1. READ the being's hub mailbox with the being's own key (the hub's `notifications`
     read is consume-once, so every notice is persisted BEFORE anything else happens);
  2. PERSIST each notice into the being's home, `notes/inbox/<ts>-<kind>-<id>.md`, with
     its full provenance (from, kind, pointer, hub id) and a label saying the seat's
     drain relayed it — seat content in the being's frame, labelled as the seat's;
  3. NOTIFY the being's hestia inbox from the SEAT's session (hestia_member_notify to the
     being, pointer = the relayed file), so the being's next beat sees it in its inbox
     peek and can memory_read it inside its home.

Idempotent by hub notice id (`notes/inbox/.seen`). Fail-open for the being, loud in the
returned summary. The seat never speaks as the being here: the hub read uses the being's
key (courier work, the same class as the egress drain), the hestia notify is the seat's.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

# hub kinds (fractal roots) -> hestia MEMBER_NOTICE_KINDS
_KIND_MAP = {"review": "review_request", "review.request": "review_request", "review.done": "review_done",
             "forum": "forum-note", "forum.note": "forum-note", "forum-note": "forum-note",
             "reply": "reply", "handoff": "handoff", "ack": "ack", "coordination": "coordination"}
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _env_from_file(path: str) -> Dict[str, str]:
    """KEY=value lines (quotes stripped, comments ignored) from a hub-mesh env file."""
    out: Dict[str, str] = {}
    for line in Path(os.path.expanduser(path)).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split("#", 1)[0].strip() if not v.strip().startswith(('"', "'")) else v.strip()
        # hub-mesh env files are shell-sourced by hub-notify, so `$HOME`, `${X}` and `~`
        # appear in values (measured: CHANNEL_CLIENT=$HOME/... on Sprout, 2026-09-05)
        out[k.strip()] = os.path.expanduser(os.path.expandvars(v.strip().strip('"').strip("'")))
    return out


def fetch_notifications(env_file: str, timeout: int = 60) -> List[Dict]:
    """Read (and thereby consume) the mailbox of the identity in `env_file`."""
    env = _env_from_file(env_file)
    cmd = [env["CHANNEL_CLIENT"], env["HUB_URL"], env["MY_LCT"], os.path.expanduser(env["MY_KEYPAIR"]),
           "notifications", "{}"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    # "CANNOT TELL" IS NOT "EMPTY" (Sprout, 2026-10-03). A failed call or an unreadable reply returned [] and the
    # beat recorded {fetched: 0, errors: []} -- 1,778 drains of sprout-being's mailbox, never one fetch, while
    # the hub's ledger shows sends addressed to it. Any of these now raises, so drain() records it in `errors`.
    def _why(text: str) -> str:
        return " ".join((text or "").split())[-200:]
    if p.returncode != 0:
        raise RuntimeError(f"channel_client exited {p.returncode}: {_why(p.stderr) or _why(p.stdout) or 'no output'}")
    try:
        d = json.loads(p.stdout or "")
    except Exception:
        raise RuntimeError(f"unreadable reply: {_why(p.stdout) or 'empty'}")
    if not isinstance(d, dict) or "notifications" not in d:
        raise RuntimeError(f"reply has no notifications field: {_why(json.dumps(d))}")
    return list(d.get("notifications") or [])


def map_kind(kind: str) -> str:
    k = (kind or "").strip()
    if k in _KIND_MAP:
        return _KIND_MAP[k]
    root = k.split(".", 1)[0]
    return _KIND_MAP.get(root, "coordination")


def persist_notice(instance: Path, n: Dict, relayed_by: str) -> Path:
    """Write one notice into the being's home with provenance; return the file."""
    inbox = Path(instance) / "notes" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    nid = str(n.get("pair_id") or n.get("id") or "")
    kind = str(n.get("kind") or "")
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    name = f"{stamp}-{_SAFE.sub('-', kind) or 'notice'}-{(_SAFE.sub('', nid) or 'noid')[:12]}.md"
    p = inbox / name
    body = (f"---\nkind: {kind}\nfrom: {n.get('from', '')}\npointer: {n.get('pointer_uri', '')}\n"
            f"hub_notice_id: {nid}\nrelayed_by: {relayed_by}\nrelayed_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n---\n\n"
            f"# A notice addressed to you on the hub\n\n"
            f"From `{n.get('from', '')}` (a hub member id; kind `{kind}`). Its content lives at the pointer:\n\n"
            f"    {n.get('pointer_uri', '')}\n\n"
            f"This file was written by your seat's inbox drain ({relayed_by}), not by you and not by the sender: "
            f"it is a copy of the envelope so you can find the notice from inside your home. "
            f"If the pointer is a path you hold no reach to, that is where request_scope applies.\n")
    p.write_text(body, encoding="utf-8")
    return p


def drain_once(instance: Path, env_file: str, notify: Optional[Callable[[str, str], Dict]] = None,
               fetch: Optional[Callable[[], List[Dict]]] = None, relayed_by: str = "sprout-claude",
               workspace: Optional[str] = None, member: str = "sprout-being") -> Dict:
    """One drain pass. `fetch` (test seam) defaults to the hub read with the being's key;
    `notify(kind, pointer)` (test seam) defaults to the seat's hestia member_notify to
    `member` — the being whose home `instance` is (its hestia plugin id, e.g. legion-being).
    Returns {fetched, persisted, notified, skipped, errors[]}.

    Legion 2026-09-05: the first cut hard-coded sprout-being as the notify target and
    sprout-claude as the courier, so the mirror drain on Legion would have persisted a notice
    into legion-being's home, marked it seen, and told sprout-being's hestia inbox about it —
    once, with no retry. The recipient must be the drained being, and the caller says who."""
    instance = Path(instance)
    seen_file = instance / "notes" / "inbox" / ".seen"
    seen = set(seen_file.read_text().split()) if seen_file.exists() else set()
    out = {"fetched": 0, "persisted": 0, "notified": 0, "skipped": 0, "errors": []}
    try:
        notices = fetch() if fetch is not None else fetch_notifications(env_file)
    except Exception as e:
        out["errors"].append(f"fetch: {type(e).__name__}: {e}")
        return out
    out["fetched"] = len(notices)
    files: List[Path] = []
    for n in notices:
        nid = str(n.get("pair_id") or n.get("id") or "")
        if nid and nid in seen:
            out["skipped"] += 1
            continue
        try:
            files.append((persist_notice(instance, n, relayed_by), n))
            out["persisted"] += 1
            if nid:
                seen.add(nid)
        except Exception as e:
            out["errors"].append(f"persist: {type(e).__name__}: {e}")
    seen_file.parent.mkdir(parents=True, exist_ok=True)
    seen_file.write_text("\n".join(sorted(seen)) + ("\n" if seen else ""))
    for p, n in files:
        try:
            ptr = str(p)
            if workspace and ptr.startswith(str(Path(workspace).resolve()) + "/"):
                ptr = os.path.relpath(ptr, Path(workspace).resolve().parent)  # sage/instances/...
            r = notify(map_kind(n.get("kind", "")), ptr) if notify is not None \
                else _seat_notify(map_kind(n.get("kind", "")), ptr, member=member)
            if r.get("ok"):
                out["notified"] += 1
            else:
                out["errors"].append(f"notify: {r.get('error')}")
        except Exception as e:
            out["errors"].append(f"notify: {type(e).__name__}: {e}")
    return out


def _seat_notify(kind: str, pointer: str, member: str = "sprout-being") -> Dict:
    """The seat tells the being's hestia inbox where the relayed notice is."""
    from sage.gateway.hestia_dispatch import _Mcp, _unwrap, _hestia_error, _ENDPOINT
    c = _Mcp(_ENDPOINT, "claude-code")
    c.init()
    conn = _unwrap(c.call("hestia_connect", {"plugin_id": "claude-code", "host_agent": "claude-code",
                                             "host_agent_version": "seat", "requested_role": "citizen",
                                             "host_session_id": "seat-inbox-drain"}))
    sid = conn.get("sessionId") or conn.get("session_id")
    if not sid:
        return {"ok": False, "error": _hestia_error(conn) or "no session"}
    r = _unwrap(c.call("hestia_member_notify", {"to_plugin_id": member, "kind": kind, "pointer_uri": pointer,
                                                 "session_id": sid}))
    err = _hestia_error(r)
    return {"ok": not err, "error": err, "queued_id": r.get("queued_id")}
