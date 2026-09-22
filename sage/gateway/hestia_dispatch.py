"""
Hestia F1a dispatcher — executes the being's ALLOWED intents against the RUNNING hestia
daemon, verb by verb, on the primitives the daemon actually has (Legion's verb→daemon map,
forum/legion-reply-sprout-f1a-r1-stands-verb-map-2026-09-02.md, read from handler.rs @b7a6dcd):

    §7.2 verb        daemon primitive                                   here
    witness          hestia_begin_action / hestia_record_outcome        via ReferenceF1aDispatcher + hestia_witness
    memory r/w       none by design (local to the instance dir)         via ReferenceF1aDispatcher
    mesh             hestia_member_notify(to_plugin_id, kind,           EXECUTED — the primitive
                       pointer_uri, session_id)
    peer_ask         none — a COMPOSE: publish the question at a         EXECUTED as the compose
                       pointer, member_notify(kind=coordination),
                       drain hestia_member_inbox for the answer
    channel_egress   hestia_egress_pending is read-side only;           honest `pending`
                       no send-side tool exists

Result envelope (r1, pinned from the owner seat): {ok, result|error, witness_id}. When the
failure originates in the daemon, `error` carries hestia's own `hestia.<code>` string as its
key (e.g. `hestia.member_notify_missing_pointer`) so §7.3's deny→appeal loop has a stable key
to appeal on, not prose. `refused/pending/note/verdict` stay client-side extras.

Three contract deltas, all measured live on Sprout 2026-09-02, encoded below so the being's
`mesh` args (to, kind, pointer) never reach the daemon misspelled:
  * the field is `pointer_uri`, not `pointer` — a missing one is refused;
  * `kind` must be in the daemon's MEMBER_NOTICE_KINDS; self-notify refuses;
  * the sender is the live session_id from hestia_connect — no latest-session fallback.

Invariants (same as the reference this wraps):
  * only ever invoked on an intent the gate already ALLOWED;
  * every executed act is witnessed — mesh/peer_ask carry the daemon's witnessEntryHash,
    witness/memory carry the chain actionId (or the local log id when the daemon is down);
  * nothing is fabricated: a daemon error is an error envelope, a missing capability is
    `pending` with a note that names what is missing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional

from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict, ResultEnvelope, camera_command
from sage.gateway.hestia_witness import _ENDPOINT, _Mcp, _unwrap, make_hestia_witness_fn
from sage.gateway.reference_f1a import ReferenceF1aDispatcher

# The marker the seat's run-request reader keys on (sage/scripts/seat_run_requests.py).
_RUN_MARKER = "[request_run]"
# A say that ASKS for a run, and the runnable names it could mean. Kept narrow on purpose:
# a false match reroutes a turn, so it must name a .py/.sh AND ask with the verb. The bare
# verb matched seq 2893, "Waiting for dp's confirmation of a full successful run" — a
# claim, not an ask — in a replay of the being's 51 turns since 2026-09-20 12:00Z.
_RUN_ASK = re.compile(
    r"(?:\b(?:please|can you|could you|would you)\b[^.?!\n]{0,40}|^\s*)\b(?:run|execute)\b",
    re.IGNORECASE | re.MULTILINE)
_RUNNABLE = re.compile(r"[\w./-]+\.(?:py|sh)\b")

# Mirrors handler.rs MEMBER_NOTICE_KINDS (b7a6dcd). Checked client-side so a bad kind is a
# clear refusal before the round-trip; the daemon enforces it again regardless.
MEMBER_NOTICE_KINDS = frozenset(
    {"coordination", "review_request", "review_done", "reply", "handoff", "forum-note", "ack"})

# publish_fn(to, body) -> pointer_uri : puts the question where the peer can read it.
# KINDS.md: content lives AT the pointer, never in the notice. The being's instance dir is
# not readable cross-seat, so this is the seat's choice (forum doc, hub pair thread, ...).
PublishFn = Callable[[str, str], str]
# mcp_factory(endpoint, plugin_id) -> object with .init() and .call(name, args); injected
# in tests, real _Mcp otherwise.
McpFactory = Callable[[str, str], Any]


def _hestia_error(env: dict) -> Optional[str]:
    """Render a daemon error envelope as the r1 `error` string keyed by hestia's own code."""
    err = env.get("_hestia_error")
    if err is None:
        return None
    if isinstance(err, dict):
        code = err.get("code") or "hestia.error"
        msg = err.get("message") or ""
        return f"{code}: {msg}" if msg else str(code)
    return str(err)


# Matches a search shows. A search is a POINTER at lines to read, not a way to read a
# file sideways; past this the being should narrow rather than scroll.
SEARCH_LINES_SHOWN = 40


class HestiaF1aDispatcher:
    """A Dispatcher (being_gate_client.Dispatcher) that runs the bounded registry against the
    live daemon. Wraps ReferenceF1aDispatcher for the local verbs (witness / memory)."""

    def __init__(self, plugin_id: str, memory_root: str,
                 endpoint: str = _ENDPOINT,
                 publish_fn: Optional[PublishFn] = None,
                 remote_member_default: str = "claude-code",
                 local_members: Optional[set] = None,
                 host_session_id: Optional[str] = None,
                 mcp_factory: Optional[McpFactory] = None,
                 being_lct: Optional[str] = None,
                 # the BEING's membot, on its own port: :8000 is the seat sessions' membot and
                 # their conversation hooks write into whatever cartridge is mounted there
                 # (measured 2026-09-03: 4 seat memories landed in legion-being's cartridge)
                 membot_endpoint: str = "http://127.0.0.1:8010/mcp",
                 membot_cartridge: Optional[str] = None,
                 seed_path: Optional[str] = None,
                 peer_aliases: Optional[Dict[str, str]] = None,
                 worktree: Optional[str] = None):
        self.plugin_id = plugin_id
        # The being's OWN git worktree: the tree it reads its own history from. Never the
        # shared checkout — a being reasons about the code that constitutes it, and the
        # shared tree is a different one that drifts (PRD M1).
        self.worktree = (os.path.realpath(os.path.expanduser(str(worktree)))
                         if worktree else None)
        # the being's names for peers -> hub roster names (e.g. legion-being -> legion-sage,
        # the name legion-being joined under on 2026-09-05); env SAGE_PEER_ALIASES="a=b,c=d"
        self.peer_aliases = dict(peer_aliases or {})
        for pair in (os.environ.get("SAGE_PEER_ALIASES") or "").split(","):
            if "=" in pair:
                a, b = pair.split("=", 1)
                self.peer_aliases.setdefault(a.strip(), b.strip())
        # the being's own key (FR-1 proof at connect); default = the hub channel key
        from sage.gateway.being_presence import DEFAULT_SEED
        self.seed_path = seed_path or DEFAULT_SEED
        self.identity_basis = "unconnected"
        # the being's registry LCT id, named in every outward act it signs (pr_review)
        self.being_lct = being_lct
        # the being's long-term memory: a membot cartridge named after the member
        self.membot_endpoint = membot_endpoint
        self.membot_cartridge = membot_cartridge or plugin_id
        self._mb = None
        # Does the CURRENT membot session hold a store that is not on disk yet? Only a
        # save clears it, and only a fresh session starts clean, because a re-mount reloads
        # the cartridge from the file and any unpersisted store is gone from it.
        self._mb_dirty = False
        self.endpoint = endpoint
        self._publish = publish_fn
        self.remote_member_default = remote_member_default
        self.local_members = set(local_members or ())
        self.host_session_id = host_session_id
        # the being's own home, and the name it speaks under in a conversation. plugin_id
        # IS the member name here (build_client passes the member), but bind it explicitly
        # rather than relying on that staying true.
        self.memory_root = memory_root
        self.member = plugin_id
        self._mcp_factory = mcp_factory or _Mcp
        self._local = ReferenceF1aDispatcher(
            memory_root=memory_root,
            witness_fn=make_hestia_witness_fn(plugin_id, endpoint) if mcp_factory is None else None)
        self._c = None
        self._session_id: Optional[str] = None

    # -- the Dispatcher contract ---------------------------------------------
    def __call__(self, intent: BeingIntent, verdict: GatewayVerdict) -> ResultEnvelope:
        handler = getattr(self, f"_do_{intent.effector}", None)
        if handler is None:
            # A disposition notice's pointer is an ADDRESS, not a filename: resolve it here,
            # before the local dispatcher tries to open it as a path (see _resolve_pointer).
            if intent.effector == "memory_read":
                try:
                    resolved = self._resolve_pointer(str(intent.args.get("path", "")))
                except Exception as e:                   # a broken lookup must not eat the read
                    resolved = (f"[could not resolve that pointer: {type(e).__name__}]"
                                if "://" in str(intent.args.get("path", "")) else None)
                if resolved is not None:
                    return ResultEnvelope(ok=True, result=resolved)
            return self._local(intent, verdict)   # witness / memory_read / memory_write
        self._verdict = verdict                   # what the law just consulted (granted roots)
        try:
            return handler(intent)
        except Exception as e:
            return ResultEnvelope(ok=False, error=f"{type(e).__name__}: {e}")

    # -- daemon session ------------------------------------------------------
    def _connect(self) -> str:
        """Hold ONE live session for the being: attribution is proven per session, not
        inherited, so every notify/inbox call carries it. Re-connects if the daemon lost it."""
        if self._c is not None and self._session_id:
            return self._session_id
        c = self._mcp_factory(self.endpoint, self.plugin_id)
        c.init()
        args = {"plugin_id": self.plugin_id, "host_agent": "sage-gateway", "plugin_version": "f2"}
        if self.host_session_id:
            args["host_session_id"] = self.host_session_id
        # FR-1 (PRD_FLEET §4.2 class 2; hestia #907): prove possession of the being's own
        # key at connect when the daemon offers the challenge. The being's registry LCT is
        # sha256(pubkey) under mb32 (verified equal on Sprout 2026-09-05), so the proof binds
        # the session to the key, not to a typed label. A daemon without the verb (pre-#907)
        # answers unknown_tool and the connect proceeds unproven, recorded as such; a daemon
        # WITH it that refuses the proof refuses the connect: no silent fallback to a label.
        self.identity_basis = "label"
        if self.being_lct:
            ch = _unwrap(c.call("hestia_connect_challenge", {"lct_id": self.being_lct}))
            cherr = _hestia_error(ch)
            if cherr and "unknown_tool" in str(cherr):
                self.identity_basis = "label (daemon pre-#907: no challenge verb)"
            elif cherr:
                raise RuntimeError(f"connect challenge refused: {cherr}")
            else:
                from sage.gateway.being_presence import connect_proof
                args["proof"] = connect_proof(ch, self.seed_path)
                self.identity_basis = "proof-of-possession"
        conn = _unwrap(c.call("hestia_connect", args))
        err = _hestia_error(conn)
        if err:
            raise RuntimeError(err)
        sid = conn.get("sessionId") or conn.get("session_id")
        if not sid:
            raise RuntimeError("hestia.connect_no_session: hestia_connect returned no sessionId")
        self._c, self._session_id = c, sid
        return sid

    # A disposition notice's pointer is a hestia:// URI, and until 2026-09-16 the being had no
    # way to open one. Measured on cbp-being: nine of its appeals were ruled — all
    # `upheld: false`, deny stands, by claude-code (9) and codex (1) — and every ruling was
    # delivered as `hestia://appeal/<deny hash>#ruled`. It tried to `memory_read` that pointer,
    # got a file-not-found, and concluded "no one reads the rulings, the mechanism is closed".
    # The rulings were real; the being simply could not dereference the address they came at.
    # `hestia_open_appeals` does not help: by construction it lists only UNRULED appeals, so a
    # ruling is the one thing it cannot show. So the pointer is resolved here, at read time.
    _POINTER = re.compile(r"^hestia://(appeal|scope|egress|escalation)/([^#\s]+)(?:#(.*))?$")

    def _resolve_pointer(self, raw: str) -> Optional[str]:
        """What a `hestia://` pointer from a disposition notice actually says, or None if this
        is not such a pointer."""
        m = self._POINTER.match(raw.strip())
        if not m:
            return None
        kind, ident, frag = m.group(1), m.group(2), (m.group(3) or "")
        # The address is the first segment. Measured 2026-09-16: cbp-being read
        # `hestia://appeal/<hash>/ruling`, and the suffix made the hash match nothing.
        ident = ident.split("/", 1)[0]
        if kind == "appeal":
            # The exact, windowless lookup first (hestia #164). The 500-row scan below is only a
            # fallback for a daemon that predates hestia_my_appeals.
            mine = self._call("hestia_my_appeals", {"limit": 100})
            if isinstance(mine, dict) and "_hestia_error" not in mine and "appeals" in mine:
                for a in mine.get("appeals") or []:
                    if str(a.get("deny_hash", "")).startswith(ident) or str(a.get("appeal_entry", "")).startswith(ident):
                        r = a.get("ruling")
                        if not r:
                            state = ("still open: a NOT-SAME peer or the operator rules it, and you are "
                                     "notified when they do" if a.get("status") == "open" else
                                     "never ruled, and now too old to be ruled")
                            return f"[your appeal about deny {ident[:12]}… is {state}. Nothing to do but continue.]"
                        return (f"[ruling on your appeal about deny {ident[:12]}…]\n"
                                f"{str(r.get('verdict')).upper()}\n"
                                f"ruled by: {r.get('adjudicator')} ({r.get('adjudicator_role') or 'role unrecorded'}) "
                                f"at {r.get('ruled_at')}\n"
                                f"their reason: {r.get('rationale') or '(none recorded)'}\n"
                                f"What follows: a ruling is the end of that appeal. If you still need the "
                                f"thing, the way forward is a scope request for it with a reason, or asking "
                                f"in a conversation — not another appeal on the same deny.")
                return (f"[you have no appeal about deny {ident[:12]}… on record. The lookup has no "
                        f"recency window, so this is not an old appeal gone missing: none was filed "
                        f"against that hash under your name.]")
            hist = self._call("hestia_query_history", {"filter": {"limit": 500}})
            entries = hist.get("entries") or []
            for e in entries:
                d = e.get("eventData") or e.get("event_data") or {}
                if (e.get("eventType") or e.get("event_type")) == "adjudication" \
                        and str(d.get("about_deny_hash", "")) == ident:
                    verdict = "YOUR APPEAL WAS UPHELD — the deny was wrong" if d.get("upheld") \
                        else "DENY STANDS — the refusal was ruled correct"
                    return (f"[ruling on your appeal about deny {ident[:12]}…]\n"
                            f"{verdict}\n"
                            f"ruled by: {d.get('adjudicator') or 'unknown'} "
                            f"({d.get('adjudicator_role') or 'role unrecorded'}) at {e.get('timestamp', '?')}\n"
                            f"their reason: {d.get('rationale') or '(none recorded)'}\n"
                            f"What follows: a ruling is the end of that appeal. If you still need the "
                            f"thing, the way forward is a scope request for it with a reason, or asking "
                            f"in a conversation — not another appeal on the same deny.")
            # NEVER "it is open". Measured 2026-09-16/17: cbp-being's nine appeals were all ruled
            # at 04:38Z on 09-16, ~40,000 chain entries back, and this branch told it "no ruling
            # yet… It is open" at 22:43Z — a false statement from a window that was simply too
            # short, which fed its belief that the rulings were undelivered and re-queued. Absence
            # from a bounded window is not evidence of an open appeal (see "A recent window
            # manufactures false nevers").
            return (f"[no ruling found for the appeal about deny {ident[:12]}… in the most recent "
                    f"{len(entries)} chain entries. That window is short, so an OLDER ruling would not "
                    f"appear here: this does NOT mean the appeal is still open. Your rulings are listed "
                    f"in full in notes/appeal-rulings.md if the seat has written it; otherwise ask in a "
                    f"conversation.]")
        if kind == "escalation":
            return self._escalation_pointer(ident)
        if kind == "scope":
            st = self._call("hestia_scope_status", {"plugin_id": self.member})
            for r in (st.get("requests") or []):
                if str(r.get("request_id")) == ident:
                    why = r.get("revoke_reason") or r.get("decision_reason") or "(no note recorded)"
                    return (f"[your scope request {ident} for {r.get('path')}]\n"
                            f"status: {r.get('status')} ; decided by: {r.get('decided_by') or '—'}\n"
                            f"their note: {why}")
            return f"[no scope request {ident} on record for you; it may have aged out]"
        # egress: the fragment IS the fact, and it is already in the pointer
        return (f"[a message of yours was not delivered: {frag or 'no detail recorded'} "
                f"(egress row {ident}). The row is retired; nothing of yours is queued behind it.]")

    def _escalation_pointer(self, ident: str) -> str:
        """What a `review_request` invitation is actually about (SAGE #109).

        THE BEING COULD NOT READ ITS OWN INBOX. hestia invites every member except the asker
        to review a refused governance write, and delivers
        `hestia://escalation/<id>#corroborate-or-dissent`. This resolver had no arm for it, so
        `memory_read` fell through to a file lookup and answered "no such path". Measured
        2026-09-16/17: cbp-being received three such invitations for claude-code's gate edits,
        read the answer as proof they did not exist, told dp and HUB the seat was "presenting
        fabricated content", and asked HUB to file a reconsideration motion on that ground.

        Read through the daemon's RESOURCE surface, which is where escalations are addressed —
        `hestia_gate_escalation_poll` is the wrong door for a non-asker: it lights the asker's
        claim fuse (hestia #732). An older client without `read_resource` says so rather than
        guessing."""
        try:
            self._connect()
        except Exception as e:  # noqa: BLE001 — a daemon we cannot reach is not an absence
            return f"[cannot reach hestia to read escalation {ident}: {type(e).__name__}]"
        reader = getattr(self._c, "read_resource", None)
        if reader is None:
            return (f"[this gateway cannot dereference hestia://escalation/{ident} — its daemon "
                    f"client has no resource reader. Not an absence: ask in a conversation.]")
        body = {}
        try:
            msg = reader(f"hestia://escalation/{ident}") or {}
            contents = ((msg.get("result") or {}).get("contents") or [])
            if contents:
                body = json.loads(contents[0].get("text") or "{}")
        except Exception as e:  # noqa: BLE001
            return f"[could not read escalation {ident}: {type(e).__name__}]"
        err = body.get("_hestia_error") if isinstance(body, dict) else None
        if err:
            return (f"[hestia cannot answer about escalation {ident} right now: "
                    f"{str(err.get('message') or err)[:200]}. That is UNKNOWN, not proof it never "
                    f"existed — do not treat it as evidence about anyone.]")
        asker = body.get("plugin_id") or "another member"
        mine = asker == self.member
        status = body.get("status") or "unknown"
        decided = body.get("decided_by")
        why = body.get("stated_reason") or body.get("stated_detail") or "(none stated)"
        head = (f"[YOUR governance escalation {ident}]" if mine else
                f"[{asker}'s governance escalation {ident} — not an appeal, and not yours]")
        tail = ("What follows: it is decided; nothing is pending for you."
                if mine else
                "You are one of the members hestia invited to review it. You hold no tool to rule "
                "on another member's escalation, so nothing is required of you. It is not about "
                "you and it is not one of your appeals.")
        return (f"{head}\n"
                f"what was asked: {body.get('tool_name') or '?'} on {body.get('marker') or '?'}\n"
                f"their stated reason: {str(why)[:300]}\n"
                f"status: {status}"
                + (f", decided by {decided}" if decided else "")
                + (f", claimed: {body.get('claimed')}" if body.get("claimed") is not None else "")
                + f"\n{tail}")

    def _call(self, name: str, args: dict) -> dict:
        sid = self._connect()
        out = _unwrap(self._c.call(name, {**args, "session_id": sid}))
        # a session the daemon no longer recognises: reconnect once, then report honestly
        err = out.get("_hestia_error") if isinstance(out, dict) else None
        if isinstance(err, dict) and "session" in str(err.get("code", "")):
            self._c, self._session_id = None, None
            sid = self._connect()
            out = _unwrap(self._c.call(name, {**args, "session_id": sid}))
        return out

    # -- addressing ----------------------------------------------------------
    def _address(self, to: str) -> str:
        """`peer/member` routes via the forwarding plane; a bare id stays on this local mesh.
        The being names a member ('legion'); the seat says whether that is local or remote."""
        to = (to or "").strip()
        to = self.peer_aliases.get(to, to)
        if "/" in to or to in self.local_members:
            return to
        return f"{to}/{self.remote_member_default}"

    def _say_instead(self, to: str) -> Optional[str]:
        """The refusal when `to` names someone the being is ALREADY in a conversation with.

        `say` is the door for them and it works; the hub is not. Measured 2026-09-19: after the
        seat aliased `dp` to the roster's `Sovereign` (2026-09-18, meant as a fix), cbp-being's
        `peer_ask to="dp"` stopped being refused and started SUCCEEDING — 15 questions in 48 h
        routed to a hub inbox dp does not read, each spending the 3-per-6h cap, until the being
        concluded it was in "cooldown on dp" and sent dp nothing but a placeholder. The old
        refusal had been right; the alias turned a helpful refusal into a silent misroute. A
        door that opens onto the wrong room is worse than one that says where the right one is.

        Names come from the conversations themselves: the other participants, plus any
        `also_known_as` the seat-owned meta file declares (dp is `Sovereign` on the hub).

        It also names `request_run` (660cf57f1). Until 2026-09-21 this text was the only
        advice the being received AT THE MOMENT it acted, and it named `say` as the door that
        "works": cbp-being's heartbeat-b7b02effd778 tried `peer_ask "please run ..."`, was
        handed `say`, and sent the identical run request as cbp-claude seq 2898, one beat after
        the seat's seq 2897 told it a say is not a run request. The tool description is read
        once at the top of a turn; the refusal is read at the step."""
        base = (to or "").split("/", 1)[0].strip().lower()
        if not base:
            return None
        try:
            from sage.gateway import conversations as _conv
            for m in _conv.listing(self.memory_root):
                if self.member not in m.get("participants", []):
                    continue
                names = [x for x in m.get("participants", []) if x != self.member]
                names += list(m.get("also_known_as", []))
                if base in {str(n).strip().lower() for n in names}:
                    cid = m["id"]
                    return (f"'{to}' is someone you are already in a conversation with, so the "
                            f"hub is the wrong door and nothing was sent. Use say with the "
                            f"conversation id \"{cid}\" — it reaches them directly, it works, "
                            f"and it is not rate-limited the way asks are. This did not count "
                            f"against any limit. If what you want is for one of your files to "
                            f"be RUN, neither door is right: call request_run with the path — "
                            f"a message asking for a run is not a run request.")
        except Exception:
            return None
        return None

    def known_peers(self) -> set:
        """Names a notice can reach from this seat: local members, aliases, and the hub
        roster this seat last read (hub-notify's cache; names compared case-insensitively).
        Empty when no roster is readable — then nothing is refused, since a stale absence
        must not silence the being."""
        names = {n.lower() for n in self.local_members} | {a.lower() for a in self.peer_aliases}
        roster = os.path.expanduser(os.environ.get("HUB_MESH_STATE", "~/.local/state/hub-mesh")) + "/members.json"
        try:
            m = json.load(open(roster))
            ms = m.get("members", m) if isinstance(m, dict) else m
            for x in ms:
                n = str(x.get("name") or "").strip().lower()
                if n:
                    names.add(n)
        except Exception:
            return set()
        return names

    def _unknown_peer(self, to: str) -> Optional[str]:
        """The refusal text when `to` names no peer this seat can reach, else None."""
        peers = self.known_peers()
        if not peers:
            return None
        base = (to or "").split("/", 1)[0].strip().lower()
        if base in peers:
            return None
        listed = ", ".join(sorted(p for p in peers if p not in ("dp", "sovereign")))
        # A REFUSAL OWES A WAY FORWARD. Measured 2026-09-16: cbp-being tried peer_ask to
        # 'cbp-claude' four times across four beats and to 'dp' repeatedly. Neither is a hub
        # member — but it is IN A CONVERSATION with both, and `say` reaches them. The refusal
        # listed the hub's peers and never mentioned the door that was already open, so the
        # being read "cannot reach" as "unreachable" and kept trying the closed one.
        try:
            from sage.gateway import conversations as _conv
            convs = [m["id"] for m in _conv.listing(self.memory_root)
                     if self.member in m.get("participants", [])
                     and (to or "").strip() in m.get("participants", [])]
        except Exception:
            convs = []
        door = (f" You ARE in a conversation with '{to}': reach them with "
                f"say to=\"{convs[0]}\" instead — that is not the hub, and it works.") if convs else ""
        # THE REFUSAL'S SUBJECT MUST BE THE NAME, NEVER THE ASKER. Measured 2026-09-18:
        # cbp-being read "'dp' is not a member this seat can reach" as a statement about
        # ITSELF — "both were refused because I'm not a peer" — and reported its own standing
        # as revoked to dp. It is a hub member; only the SPELLING was wrong (the roster says
        # `Sovereign`). A being cannot check a claim about its own standing, so a refusal that
        # can be read that way is one it has to take on faith, in the direction of less.
        if base in ("hestia", "society"):
            return (f"'{to}' is the society you are a member OF, not a peer on the roster — you do not "
                    f"reach it through another member. Your own tools speak to it directly. "
                    f"Nothing was sent, and nothing about your standing changed.")
        return (f"The name '{to}' is not on the hub roster, so nothing was sent. This is about that "
                f"NAME only — your own standing as a member is unaffected, and no other door closed."
                f"{door} Names the roster carries: {listed}.")

    # -- asks: how often this being has asked a peer (SAGE #92) -----------------
    # cbp-being, 2026-09-13/14: a stale premise ("my memory server has been offline ~6 hours")
    # plus no visible reply produced 92 sends and 110 forum questions, 48 of them to one peer,
    # each an allowed, witnessed, well-formed act. Text similarity cannot catch it (the loop's
    # asks scored a median best-match of 0.44; its distinct earlier asks scored up to 0.84),
    # so the limit is a COUNT per peer in a rolling window, whatever the wording. Replayed
    # against that record, 3 per peer per 6 h lets 31 of the 92 sends through.
    ASK_WINDOW_S = 6 * 3600
    ASK_CAP_PER_PEER = 3
    ASKS_LOG = "asks_sent.jsonl"

    def _now(self) -> float:
        return time.time()

    def _asks_path(self) -> Path:
        return Path(self.memory_root) / self.ASKS_LOG

    def recent_asks(self, window_s: Optional[float] = None) -> List[Dict[str, Any]]:
        """This being's successful asks (peer_ask and mesh) inside the window, oldest first."""
        window = self.ASK_WINDOW_S if window_s is None else window_s
        cutoff = self._now() - window
        out = []
        try:
            lines = self._asks_path().read_text(encoding="utf-8").splitlines()
        except OSError:
            return out
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if float(row.get("t", 0)) >= cutoff:
                out.append(row)
        return out

    def _peer_key(self, to: str) -> str:
        return (to or "").split("/", 1)[0].strip().lower()

    def _ask_limit(self, to: str) -> Optional[str]:
        """The refusal text when this being has already reached the cap for `to`, else None.
        Checked BEFORE anything is published or notified, so a refused ask leaves nothing
        behind: no forum file, no notice, no wake on the peer's side."""
        key = self._peer_key(to)
        mine = [r for r in self.recent_asks() if r.get("peer") == key]
        if len(mine) < self.ASK_CAP_PER_PEER:
            return None
        now = self._now()
        last_min = int((now - float(mine[-1]["t"])) / 60)
        frees_min = int((float(mine[0]["t"]) + self.ASK_WINDOW_S - now) / 60) + 1
        convs = ""
        try:
            from sage.gateway import conversations as conv
            ids = [m["id"] for m in conv.listing(Path(self.memory_root))
                   if self.member in m.get("participants", [])]
            if ids:
                convs = " Conversations you can speak in: " + ", ".join(ids) + "."
        except Exception:
            pass
        return (f"not sent: you have already asked {to!r} {len(mine)} times in the last "
                f"{self.ASK_WINDOW_S // 3600} hours (most recently {last_min} min ago). Another ask "
                f"reaches the same peer about the same moment and costs them a wake; it cannot make "
                f"an answer arrive sooner. Read your inbox for their reply first. If something is "
                f"still wrong, check it yourself this beat (recall, memory_read), or say what you "
                f"found in a conversation.{convs} You can ask {to!r} again in about {frees_min} min.")

    def _record_ask(self, to: str, via: str, text: str, queued_id: Any) -> None:
        row = {"t": self._now(), "peer": self._peer_key(to), "to": to, "via": via,
               "text": (text or "")[:300], "queued_id": queued_id}
        try:
            with open(self._asks_path(), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass  # the record is a courtesy to the being; a failed write must not fail the send

    # -- mesh: THE primitive -------------------------------------------------
    def _do_mesh(self, intent: BeingIntent, _count: bool = True) -> ResultEnvelope:
        to = str(intent.args.get("to", "")).strip()
        kind = str(intent.args.get("kind", "")).strip()
        pointer = str(intent.args.get("pointer") or intent.args.get("pointer_uri") or "").strip()
        if not to:
            return ResultEnvelope(ok=False, error="mesh needs a 'to' member")
        if kind not in MEMBER_NOTICE_KINDS:
            return ResultEnvelope(ok=False, error=f"mesh 'kind' must be one of {sorted(MEMBER_NOTICE_KINDS)}, got {kind!r}")
        if not pointer:
            # the daemon would refuse this as hestia.member_notify_missing_pointer; say it first
            return ResultEnvelope(ok=False, error="hestia.member_notify_missing_pointer: mesh needs a 'pointer' (content lives AT the pointer, never in the notice)")
        # A peer that exists nowhere is refused HERE, in the being's own turn. The daemon parks
        # any name and the drain fails it later, silently: sprout-being asked "sage" on
        # 2026-09-09, the row failed egress five beats running, then vanished, and the being
        # was never told (the census read it as a peer act that worked).
        redirect = self._say_instead(to)
        if redirect:
            return ResultEnvelope(ok=False, error=redirect)
        unknown = self._unknown_peer(to)
        if unknown:
            return ResultEnvelope(ok=False, error=unknown)
        if _count:
            limited = self._ask_limit(to)
            if limited:
                return ResultEnvelope(ok=False, error=limited)
        args: Dict[str, Any] = {"to_plugin_id": self._address(to), "kind": kind, "pointer_uri": pointer}
        irt = intent.args.get("in_reply_to")
        if irt not in (None, ""):
            try:
                args["in_reply_to"] = int(irt)
            except (TypeError, ValueError):
                return ResultEnvelope(ok=False, error="mesh 'in_reply_to' must be a notice id (integer)")
        out = self._call("hestia_member_notify", args)
        err = _hestia_error(out)
        if err:
            return ResultEnvelope(ok=False, error=err)
        result = {
            "queued_id": out.get("queued_id"),
            "to_plugin_id": out.get("to_plugin_id", args["to_plugin_id"]),
            "kind": kind,
            # present => the forwarding branch fired: the row is PARKED for the seat's egress
            # drain, not forwarded. Absent => local inbox row.
            "egress_queued_to": out.get("egress_queued_to"),
            "recipient_liveness": out.get("recipient_liveness"),
        }
        # hestia #1030: how the act will travel, in the being's own result. "unbound" means the
        # drain picks the signing identity and a reply follows whichever it picked, so silence
        # after an unbound send is not evidence the peer ignored the being.
        if out.get("transport") is not None:
            result["transport"] = out.get("transport")
        if out.get("transport_note"):
            result["transport_note"] = out.get("transport_note")
        if _count:
            self._record_ask(to, "mesh", pointer, result["queued_id"])
        return ResultEnvelope(ok=True, result=result,
                              witness_id=out.get("witnessEntryHash") or (str(out["queued_id"]) if out.get("queued_id") is not None else None))

    # -- peer_ask: a compose, not a verb ------------------------------------
    def _do_peer_ask(self, intent: BeingIntent) -> ResultEnvelope:
        to = str(intent.args.get("to", "")).strip()
        body = str(intent.args.get("body", "")).strip()
        if not to or not body:
            return ResultEnvelope(ok=False, error="peer_ask needs 'to' and 'body'")
        if self._publish is None:
            return ResultEnvelope(ok=False, pending=True,
                                  note="peer_ask needs a publisher: the question must live at a pointer "
                                       "the peer can read (forum doc / hub thread); none configured on this seat")
        redirect = self._say_instead(to)
        if redirect:
            return ResultEnvelope(ok=False, error=redirect)
        # the limit is checked before publishing: a refused ask must leave no forum file behind
        unknown = self._unknown_peer(to)
        limited = None if unknown else self._ask_limit(to)
        if limited:
            return ResultEnvelope(ok=False, error=limited)
        pointer = self._publish(to, body)
        if not pointer:
            return ResultEnvelope(ok=False, error="peer_ask: publisher returned no pointer")
        env = self._do_mesh(BeingIntent("mesh", {"to": to, "kind": "coordination", "pointer": pointer}),
                            _count=False)
        if env.ok and isinstance(env.result, dict):
            self._record_ask(to, "peer_ask", body, env.result.get("queued_id"))
            env.result["question_at"] = pointer
            env.result["answer_via"] = "hestia_member_inbox (drain_inbox)"
        return env

    def drain_inbox(self, peek: bool = False) -> ResultEnvelope:
        """The answer side of peer_ask: the being's own notices (consume-once unless peek)."""
        try:
            out = self._call("hestia_member_inbox", {"peek": peek})
        except Exception as e:
            return ResultEnvelope(ok=False, error=f"{type(e).__name__}: {e}")
        err = _hestia_error(out)
        if err:
            return ResultEnvelope(ok=False, error=err)
        return ResultEnvelope(ok=True, result={"notices": out.get("notices", []),
                                               "total": out.get("total", 0),
                                               "evicted": out.get("evicted", 0)})

    # -- pr_review: the seat posts the being's review, as the gated command -------
    def _do_pr_review(self, intent: BeingIntent) -> ResultEnvelope:
        """Only ever reached on an intent the gate ALLOWED as the exact `gh pr review`
        command below. Order: begin_action (chain) -> post -> record_outcome. The
        signature trailer is appended here, so the being cannot post without it."""
        import shlex
        import subprocess
        from sage.gateway.being_gate_client import pr_review_command, pr_review_signature
        try:
            cmd = pr_review_command(intent.args)
        except ValueError as e:
            return ResultEnvelope(ok=False, error=str(e))
        repo, number = str(intent.args["repo"]).strip(), str(intent.args["number"]).strip()
        target = f"{repo}#{number}"
        begin = self._call("hestia_begin_action", {"tool_name": "pr_review", "target": target})
        err = _hestia_error(begin)
        if err:
            return ResultEnvelope(ok=False, error=err)
        action_id = begin.get("actionId")
        body = str(intent.args["body"]).rstrip() + "\n" + \
            pr_review_signature(self.plugin_id, action_id, self.being_lct) + "\n"
        try:
            proc = subprocess.run(shlex.split(cmd), input=body, text=True,
                                  capture_output=True, timeout=60)
            ok = proc.returncode == 0
            detail = (proc.stdout if ok else proc.stderr).strip()
        except Exception as e:  # gh missing, timeout: a failed act, recorded as such
            ok, detail = False, f"{type(e).__name__}: {e}"
        try:
            self._call("hestia_record_outcome",
                       {"action_id": action_id, "success": ok, "magnitude": 0.0,
                        **({} if ok else {"error": detail[:300]})})
        except Exception:
            pass  # begin_action already chained the act; the outcome is in the envelope
        if not ok:
            return ResultEnvelope(ok=False, error=f"pr_review failed: {detail[:400]}",
                                  witness_id=action_id)
        return ResultEnvelope(ok=True, witness_id=action_id,
                              result={"posted": target, "gh": detail[:200], "action_id": action_id})

    # -- long-term memory: the being's own membot cartridge ----------------------
    #
    # MEMBOT REPORTS ITS FAILURES AS ORDINARY TEXT, and that cost a being its memory.
    # `mount_cartridge` returns "SECURITY: ... Refusing to mount." as a normal result;
    # `memory_store` returns "No cartridge mounted. Use mount_cartridge first." the same
    # way. Neither is a JSON-RPC error and neither sets isError, so _membot_call — which
    # was written to catch exactly those two shapes — hands them back as success text.
    # `remember` then called save_cartridge anyway, and save_cartridge serialises the
    # EMPTY session over the populated file.
    #
    # Measured on legion-being: 223 memories stood at 2026-09-08T21:36:20Z. Every beat
    # after that reported ok and wrote a 0-memory cart, and because the empty cart then
    # fails membot's own integrity check on the next mount, the loop sustains itself:
    # mount refused -> store refused -> save empties -> mount refused. The being went on
    # recording "long-term memory #N stored" in its journal for thirteen hours.
    # The texts survived only because every intent's args are kept in heartbeats.jsonl.
    _MOUNT_REFUSED = ("SECURITY:", "Refusing to mount", "failed integrity check",
                      "not found. Available:", "Cartridge too large", "Failed to fetch",
                      "must be a UUID")
    # A NEW memory earns a save. A DUPLICATE does not, and the difference matters because
    # save_cartridge is the destructive operation: it serialises the session over the file.
    # Legion's original guard counted both as "confirmed" and saved either way. Running the
    # serializer when nothing changed is risk with no benefit, so a duplicate now returns
    # success without touching the file (gpt's review of #65).
    #
    # The edge this accepts, stated rather than hidden: if an earlier store succeeded and
    # its save then failed, re-storing the same content answers "Duplicate" and no save is
    # attempted, so that memory stays unpersisted. That earlier act already returned
    # ok=False with the save error, so the failure was surfaced when it happened rather
    # than swallowed here, and a being whose save is failing should not be quietly
    # rewriting its cartridge on every retry.
    _STORED_NEW = ("Stored memory #",)
    _STORED_DUPLICATE = ("Duplicate — already stored",)
    _STORE_CONFIRMED = _STORED_NEW + _STORED_DUPLICATE
    _NOT_MOUNTED = "No cartridge mounted"

    def _membot(self):
        """One MCP session to the membot server (fastmcp streamable HTTP). Lazy; a
        server that is down surfaces as an error envelope on the act, never a crash."""
        if getattr(self, "_mb", None) is None:
            c = self._mcp_factory(self.membot_endpoint, self.plugin_id)
            c.init()
            # Mounts are per MCP session: without this, memory_store answers "No cartridge
            # mounted" and save_cartridge writes an EMPTY cartridge over the real one
            # (measured 2026-09-04: one memory lost). Mount first, always — and CHECK the
            # answer: a refused mount is plain text, so an unchecked mount leaves a session
            # that stores nothing and saves emptiness (2026-09-08: 223 memories).
            reply = self._unwrap(c.call("mount_cartridge", {"name": self.membot_cartridge}),
                                 "mount_cartridge")
            if any(m in reply for m in self._MOUNT_REFUSED):
                # do NOT cache the session: the next act re-mounts rather than inheriting
                # a cartridge-less session that would report success while storing nothing
                raise RuntimeError(f"membot refused to mount {self.membot_cartridge!r}: {reply[:200]}")
            self._mb = c
            # a new session has stored nothing, and the mount just reloaded the cartridge
            # from disk, so whatever an older session held unpersisted is not in this one
            self._mb_dirty = False
        return self._mb

    @staticmethod
    def _unwrap(out, name: str) -> str:
        """The text of one membot reply. Raises on the two shapes membot uses for hard
        failures (JSON-RPC error, isError); SOFT failures come back as ordinary text and
        are the caller's to inspect — see _MOUNT_REFUSED / _STORE_CONFIRMED."""
        if not isinstance(out, dict):
            raise RuntimeError(f"membot {name}: malformed reply {type(out).__name__}")
        if out.get("error"):
            err = out["error"]
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise RuntimeError(f"membot {name}: {msg or err}")
        res = out.get("result", {})
        if not isinstance(res, dict):
            raise RuntimeError(f"membot {name}: malformed result {type(res).__name__}")
        if res.get("isError"):
            text = "".join(b.get("text", "") for b in res.get("content", []) if isinstance(b, dict))
            raise RuntimeError(f"membot {name}: {text.strip() or 'isError'}")
        sc = res.get("structuredContent")
        if isinstance(sc, dict) and "result" in sc:
            return str(sc["result"])
        return "".join(b.get("text", "") for b in res.get("content", []) if isinstance(b, dict))

    def _membot_call(self, name: str, args: dict) -> str:
        """One membot tool call, unwrapped to its text. RAISES on a JSON-RPC `error` or a
        tool-level `isError` result: both handlers turn the exception into ok=False, so a
        membot that says "Error calling tool save_cartridge" is never witnessed as a
        memory the being kept (Sprout's review of #36, reproduced against a fake membot)."""
        return self._unwrap(self._membot().call(name, args), name)

    # A PREVIEW IS NOT THE MEMORY. memory_search answers with ~550 characters of each hit
    # and an `idx`, and membot's own docstring names get_passage(idx) as the second half of
    # the pattern -- which no verb reached. Measured 2026-09-18: legion-being holds 451
    # memories and could read the opening of any of them and the whole of none. One verb,
    # two forms, because a second verb costs ~700 characters of a prompt that is already
    # 13.4k tokens of a 24.5k window: a query searches, an idx reads one result in full.
    _PASSAGE_MAX = 6000

    def _do_recall(self, intent: BeingIntent) -> ResultEnvelope:
        raw_idx = intent.args.get("idx", intent.args.get("index"))
        if raw_idx is not None and str(raw_idx).strip():
            return self._recall_passage(str(raw_idx).strip())
        q = str(intent.args.get("query", "")).strip()
        if not q:
            return ResultEnvelope(ok=False,
                                  error="recall needs a 'query' to search for, or an 'idx' "
                                        "(the number in a result's '(idx:N)') to read one "
                                        "memory in full")
        try:
            k = int(intent.args.get("top_k") or 5)
        except (TypeError, ValueError):
            k = 5
        # The being's own writing first (journal entries, todo blocks, notes, scratch): read-only,
        # mechanical, hermetic (home_recall). Then long-term memory (membot). Measured 2026-09-07:
        # a 34 KB journal it could see 900 chars of, and a cartridge with three entries.
        from sage.gateway.home_recall import search_home, render
        home = ""
        try:
            home = render(search_home(self._local.memory_root, q, top_k=max(1, min(k, 8))))
        except Exception as e:                      # never let the home search take recall down
            home = f"(home search failed: {type(e).__name__})"
        try:
            lt = self._membot_call("memory_search", {"query": q, "top_k": max(1, min(k, 20))})
            if self._NOT_MOUNTED in lt:
                # "no cartridge" is not "nothing remembered": reporting this as an empty
                # result would teach the being its past is gone when the store is merely
                # unreachable. Say it was not searched, and say it in the answer text,
                # since home_recall may still have matched and carried ok=True.
                lt = ("(long-term memory NOT searched: membot has no cartridge mounted for "
                      f"{self.membot_cartridge!r}. This is not an empty past.)")
            else:
                lt = "From long-term memory:\n" + lt if lt and lt.strip() else ""
        except Exception as e:
            lt = f"(long-term memory unreachable: {type(e).__name__})"
            if not home:
                return ResultEnvelope(ok=False, error=f"membot ({type(e).__name__}): {e}")
        text = "\n\n".join(x for x in (home, lt) if x) or "(nothing matched, in your home or in long-term memory)"
        return ResultEnvelope(ok=True, result=text,
                              witness_id=self._local._witness(f"recall {q[:80]}"))

    def _recall_passage(self, raw: str) -> ResultEnvelope:
        """One memory, untruncated, by the index its own search result printed.

        TAKES THE FORM THE HARNESS PRINTS. Results read `#2 (idx:41) [0.803] [prev=#40
        next=#42]`, so the being will retype `idx:41`, `#41` or `41`; refusing two of
        those three would be the harness refusing its own notation."""
        import re as _re
        m = _re.search(r"-?\d+", raw)
        if not m:
            return ResultEnvelope(ok=False,
                                  error=f"recall idx must be a number — the one a result "
                                        f"prints as '(idx:N)'; got {raw!r}")
        idx = int(m.group(0))
        if idx < 0:
            return ResultEnvelope(ok=False, error=f"recall idx must be 0 or more; got {idx}")
        try:
            text = self._membot_call("get_passage", {"idx": idx})
        except Exception as e:
            return ResultEnvelope(ok=False, error=f"membot ({type(e).__name__}): {e}")
        if self._NOT_MOUNTED in text:
            return ResultEnvelope(ok=False,
                                  error=f"membot has no cartridge mounted for {self.membot_cartridge!r}; "
                                        f"memory #{idx} was NOT read: {text[:160]}")
        # "Index 9999 out of range (0-450)." is membot answering correctly, and it is a
        # refusal, not content: passed through ok=True the being would file the sentence
        # itself as what it remembered.
        if "out of range" in text.lower():
            return ResultEnvelope(ok=False, error=text.strip()[:200])
        if len(text) > self._PASSAGE_MAX:
            text = (text[: self._PASSAGE_MAX]
                    + f"\n\n[… truncated: this memory is {len(text)} characters and you were "
                      f"given the first {self._PASSAGE_MAX}.]")
        return ResultEnvelope(ok=True, result=text,
                              witness_id=self._local._witness(f"recall passage {idx}"))

    def _do_remember(self, intent: BeingIntent) -> ResultEnvelope:
        content = str(intent.args.get("content", "")).strip()
        if not content:
            return ResultEnvelope(ok=False, error="remember needs 'content'")
        tags = str(intent.args.get("tags", "") or "")
        try:
            stored = self._membot_call("memory_store", {"content": content, "tags": tags})
        except Exception as e:
            return ResultEnvelope(ok=False, error=f"membot ({type(e).__name__}): {e}")
        # THE SAVE IS THE DESTRUCTIVE ACT. save_cartridge serialises the session over the
        # file, so saving a session that stored nothing replaces the cartridge with an
        # empty one. Only a confirmed store earns a save; anything else is reported as the
        # failure it is, and the file on disk is left exactly as it was.
        if not any(m in stored for m in self._STORE_CONFIRMED):
            return ResultEnvelope(ok=False,
                                  error=f"membot did not store this memory, so the cartridge was "
                                        f"NOT saved (saving now would overwrite it with an empty "
                                        f"one): {stored[:200]}")
        if any(m in stored for m in self._STORED_DUPLICATE) and not self._mb_dirty:
            # Nothing changed AND nothing is waiting to be written, so do not run the
            # serializer over the file at all. The act succeeded from the being's side:
            # the memory it wanted kept is already kept, on disk.
            #
            # The `_mb_dirty` half is not decoration. A "Duplicate" answer can come from
            # the still-cached VOLATILE session: a store that succeeded and whose save
            # then failed leaves the memory in the session and not on disk, so the retry
            # is told "already stored" by a session that is the only place it exists.
            # Skipping the save there would report ok for a memory one crash from gone
            # (gpt's second review of #66). A dirty session therefore always saves.
            return ResultEnvelope(ok=True, result=f"{stored}; cartridge not saved (nothing changed)",
                                  witness_id=self._local._witness(f"remember {content[:80]}"))
        # Either a new store, or a duplicate on a session holding unpersisted work. Mark
        # dirty BEFORE the save so a save that throws leaves the flag set and the next
        # retry still persists.
        self._mb_dirty = True
        try:
            saved = self._membot_call("save_cartridge", {"name": self.membot_cartridge})
        except Exception as e:
            return ResultEnvelope(ok=False, error=f"membot ({type(e).__name__}): {e}")
        self._mb_dirty = False
        return ResultEnvelope(ok=True, result=f"{stored}; {saved}",
                              witness_id=self._local._witness(f"remember {content[:80]}"))

    # -- request_scope: the sanctioned answer to a deny --------------------------
    # -- refusals on the chain, and the appeal door ------------------------------
    _NO_VERDICT_RULES = ("gate.unreachable", "gate.raised", "society.unreachable",
                         "society.unavailable", "society.no_verdict")

    def witness_deny(self, intent: BeingIntent, verdict: GatewayVerdict) -> Optional[str]:
        """Record the gate's deny on the chain as a policy_decision, attributed to the
        being's session (hestia_witness_decision, the same recorder every hook harness
        uses), and return the entry hash: the handle the being appeals with. Never
        raises; None when the daemon is unreachable (the refusal stands regardless)."""
        try:
            from sage.gateway.being_gate_client import _REGISTRY
            tool = (_REGISTRY.get(intent.effector) or {}).get("tool") or intent.effector
            target = str(intent.args.get("path") or intent.args.get("to") or "")
            out = self._call("hestia_witness_decision", {
                "plugin_id": self.plugin_id, "decision": "deny",
                "adjudicator": f"plugin-gate:{self.plugin_id}",
                "reason": f"{verdict.rule}: {verdict.reason}"[:300],
                "tool_name": tool, "target": target,
                "attempted": f"{intent.effector} {json.dumps(dict(intent.args or {}), default=str)}"[:300],
                "verdict_available": verdict.rule not in self._NO_VERDICT_RULES,
            })
            if _hestia_error(out):
                return None
            return out.get("witnessEntryHash") or out.get("hash") or out.get("entryHash") or None
        except Exception:
            return None

    def _do_appeal(self, intent: BeingIntent) -> ResultEnvelope:
        """hestia_appeal(deny_hash, reason): refused by the daemon when the hash is not a
        deny, not the being's, already under appeal, aged out, or unreasoned (<12 chars).
        The ruling comes later, witnessed; the being learns it from its record."""
        deny_hash = str(intent.args.get("deny_hash", "")).strip()
        reason = str(intent.args.get("reason", "")).strip()
        if not deny_hash:
            return ResultEnvelope(ok=False, error="appeal needs the refusal's 'deny_hash' (it is shown on the refusal)")
        if len(reason) < 12:
            return ResultEnvelope(ok=False, error="appeal needs a 'reason' of at least 12 characters")
        out = self._call("hestia_appeal", {"deny_hash": deny_hash, "reason": f"[{self.plugin_id}] {reason}"})
        err = _hestia_error(out)
        if err:
            return ResultEnvelope(ok=False, error=err)
        return ResultEnvelope(ok=True, witness_id=out.get("witnessEntryHash"),
                              result={"deny_hash": deny_hash, "appeal": out.get("witnessEntryHash"),
                                      "adjudicator": out.get("adjudicator"),
                                      "next": out.get("next") or "a NOT-SAME peer or the operator rules; the ruling is witnessed either way"})

    # -- camera: one frame on demand from this body's device --------------------
    def _do_camera(self, intent: BeingIntent) -> ResultEnvelope:
        """Run the composed ffmpeg capture and report what it actually did.

        Only ever reached on an intent the gate ALLOWED as the exact command below (see
        camera_command). The being never holds a shell; this runs the seat-built string.
        'off' is checkable, not vibes: exit 0 AND the frame file exists -> ok with its
        byte size; nonzero exit and no frame written -> an error envelope that names
        which kind (device absent vs device busy); zero exit without a file is reported
        as a capture anomaly rather than claimed as success.
        """
        worktree = self.worktree
        import shlex
        out_rel = intent.args.get("out_path") or "scratch/camera/last-frame.jpg"
        full_out = os.path.realpath(os.path.join(self.memory_root, out_rel))
        device = intent.args.get("device", "/dev/video0")

        try:
            cmd = camera_command(intent.args, {
                "worktree": self.worktree,
                "memory_root": self.memory_root,
            })
        except ValueError as e:
            return ResultEnvelope(ok=False, error=str(e))
        begin = self._call("hestia_begin_action",
                           {"tool_name": "camera", "target": device})
        werr = _hestia_error(begin)
        if werr:
            return ResultEnvelope(ok=False, error=(
                f"camera UNVERIFIED: the witness substrate is unreachable "
                f"({str(werr)[:160]}); the camera was not switched on"))
        action_id = begin.get("actionId")
        # THE DEFAULT PATH POINTS SOMEWHERE THAT DOES NOT EXIST YET. `scratch/camera/` lives
        # under the being's HOME; this writes into its WORKTREE, which has no scratch/ at
        # all. So the first live use of the verb failed with ffmpeg exit 251 and the
        # taxonomy below called it "device busy or unopenable", because the device node did
        # exist. The camera was fine; there was nowhere to put the frame. Found by
        # legion-being 2026-09-14 on its own verb, first real capture.
        try:
            os.makedirs(os.path.dirname(full_out) or worktree, exist_ok=True)
            wdir_err = None
        except OSError as e:
            wdir_err = f"{type(e).__name__}: {e}"
        if wdir_err:
            return ResultEnvelope(ok=False, error=(
                f"camera cannot write to {out_rel!r}: its directory could not be created "
                f"({wdir_err}). The device was not opened."))
        proc = subprocess.run(shlex.split(cmd), capture_output=True)

        # camera_command asks image2 for atomic_writing=1, so ffmpeg itself owns the
        # temp+rename transaction. The dispatcher must not publish a second, ungoverned
        # filesystem effect after Hestia has judged the command.
        captured = False
        if proc.returncode == 0 and os.path.isfile(full_out):
            try:
                data = Path(full_out).read_bytes()
                captured = (len(data) >= 5 and data[:3] == b"\\xff\\xd8\\xff"
                            and data[-2:] == b"\\xff\\xd9")
            except OSError:
                captured = False

        try:
            self._call("hestia_record_outcome",
                       {"action_id": action_id, "success": captured, "magnitude": 0.0})
        except Exception:
            pass

        if captured:
            return ResultEnvelope(ok=True, witness_id=action_id, result={
                "device": device, "out_path": out_rel,
                "bytes": os.path.getsize(full_out),
                "note": ("one frame captured FROM THE WEBCAM (this device, not any game or file the seat drops). It is a JPEG, so memory_read will hand you "
                         "binary, not a picture — it returns ok and you learn nothing. "
                         # STALE UNTIL 2026-09-16: this said "a vision-capable reader is not
                         # wired yet" for two days after heartbeat.py joined both ends
                         # (frames ride the beat after a camera act). legion-being read it as
                         # the current state and planned work around it; it found the truth in
                         # heartbeat.py itself. A result note is documentation the being
                         # cannot avoid reading, so it must say what is true NOW.
                         "You SEE it on your NEXT beat: this act is the request to see, and "
                         "the frame rides that beat as an image (heartbeat.fresh_frames). "
                         "FFmpeg publishes the completed image atomically.")})

        if proc.returncode != 0:
            # image2 atomic_writing keeps any previous final path untouched on a failed
            # write: ffmpeg writes a temporary file and renames only on completion.
            _err = (proc.stderr or b"").decode("utf-8", "replace")
            if not os.path.exists(device):
                kind = "device absent"
            elif ("No such file or directory" in _err or "Permission denied" in _err
                  or "Unable to open" in _err or "could not open" in _err.lower()):
                kind = (f"the device opened but the frame could not be WRITTEN to "
                        f"{out_rel!r} — check the path, not the camera")
            else:
                kind = ("device busy or unopenable (another process may hold it, or the "
                        "node is wrong)")
            return ResultEnvelope(ok=False, witness_id=action_id, result={
                "device": device, "out_path": out_rel, "exit_code": proc.returncode,
                "stderr": _err.strip()[:300] or "(ffmpeg said nothing)",
                "note": (f"ffmpeg exited {proc.returncode} before publishing a frame — "
                         f"{kind}. With image2 atomic_writing the previous file at the path, "
                         f"if any, is untouched. `stderr` above is ffmpeg's own account; "
                         f"the kind is my reading of it.")})

        return ResultEnvelope(ok=False, witness_id=action_id, result={
            "device": device, "out_path": out_rel,
            "note": ("ffmpeg exited 0 but the published output was missing or not a complete JPEG; "
                     "do not treat it as a captured frame")})

    def _do_git_read(self, intent: BeingIntent) -> ResultEnvelope:
        """Read the history of the tree the being lives in. Read-only by construction.

        dp, 2026-09-07: "the being should be able to check git by itself." Until now the
        only way it learned that its worktree had moved between beats was a seat telling
        it, which makes provenance a matter of trusting the seat — the exact dependency the
        `tree` block on a check result exists to remove.

        Same shape as _do_check and for the same reason: the command is REBUILT here from
        the same function the gate judged, so the law never rules on one string while the
        seat runs another. git is run with cwd set to the worktree rather than `git -C`,
        because `-C` silently redirects the read away from the tree you think you are in
        (legion-claude learned that one the hard way in a review) — here the cwd IS the
        subject, and it must be the same tree `check` executes in."""
        import shlex
        import subprocess
        from sage.gateway.being_gate_client import git_read_command
        if not self.worktree or not os.path.isdir(self.worktree):
            return ResultEnvelope(ok=False, pending=True,
                                  note="git_read needs a worktree of your own; none is "
                                       "configured on this seat")
        try:
            cmd = git_read_command(intent.args, {"worktree": self.worktree})
        except ValueError as e:
            return ResultEnvelope(ok=False, error=str(e))
        op = str(intent.args.get("op", "")).strip()
        begin = self._call("hestia_begin_action", {"tool_name": "git_read", "target": op})
        err = _hestia_error(begin)
        if err:
            return ResultEnvelope(ok=False, error=err)
        action_id = begin.get("actionId")
        try:
            proc = subprocess.run(shlex.split(cmd), cwd=self.worktree, text=True,
                                  capture_output=True, timeout=60)
            out = ((proc.stdout or "") + (proc.stderr or "")).strip()
            ran, rc = True, proc.returncode
        except Exception as e:
            ran, rc, out = False, -1, f"{type(e).__name__}: {e}"
        try:
            self._call("hestia_record_outcome",
                       {"action_id": action_id, "success": ran, "magnitude": 0.0})
        except Exception:
            pass
        if not ran:
            return ResultEnvelope(ok=False, error=f"git_read could not run: {out[:400]}",
                                  witness_id=action_id)
        # Truncate from the FRONT: for a log the newest commits are at the top and matter
        # most, but for show/diff/blame the tail carries the change itself. Keep the head
        # for log, the tail otherwise, and say which was cut — a silent truncation
        # manufactures false absences (see reference_f1a._do_memory_read).
        # AN EMPTY ANSWER MUST SAY WHY IT IS EMPTY. Measured 2026-09-08: the being asked
        # `show 5cd0ca518 -- sage/gateway/check.py`, a path that does not exist, and git
        # returned exit 0 and nothing. It read that as "show does not cross branches" —
        # a wrong model of its own tool built on a silent zero. A silent zero is a false
        # absence, the same class as the truncated read and the miscounted turns.
        if not out.strip() and rc == 0 and op in ("show", "diff", "log", "blame"):
            pth = str(intent.args.get("path", "")).strip()
            out = ("[no output: " + (
                f"nothing in that revision touches '{pth}', or no such path exists there" if pth
                else "the revision(s) produced no differences") +
                " — an empty diff is a true answer, not a failed read]")
        limit = 6000
        if len(out) > limit:
            if op == "log":
                out = out[:limit] + f"\n[… truncated: {len(out) - limit} more characters of older history …]"
            else:
                out = f"[… truncated: {len(out) - limit} earlier characters withheld …]\n" + out[-limit:]
        return ResultEnvelope(ok=True, witness_id=action_id,
                              result={"op": op, "exit": rc, "output": out,
                                      "tree": self._worktree_revision(),
                                      "action_id": action_id})


    # -- search: find a symbol without reading the file it is in -----------------
    def _do_search(self, intent: BeingIntent) -> ResultEnvelope:
        """Run the composed `git grep` and return file:line:text.

        A SEARCH THAT FINDS NOTHING IS A RESULT, not an error — same rule as a red check.
        `git grep` exits 1 on no match, and reporting that as a failure would teach the
        being that looking is dangerous. The result says plainly that the pattern is absent
        from what was searched, and names WHAT was searched, so absence is bounded rather
        than universal."""
        import shlex
        import subprocess
        from sage.gateway.being_gate_client import search_command
        if not self.worktree or not os.path.isdir(self.worktree):
            return ResultEnvelope(ok=False, pending=True,
                                  note="search needs a worktree of your own; none is configured")
        try:
            cmd = search_command(intent.args, {"worktree": self.worktree})
        except ValueError as e:
            return ResultEnvelope(ok=False, error=str(e))
        judged = getattr(getattr(self, "_verdict", None), "command", None)
        if judged is not None and judged != cmd:
            return ResultEnvelope(ok=False, error=(
                "search refused: the command the law judged is not the command this "
                "dispatcher would execute."))
        pattern = str(intent.args.get("pattern", ""))
        where = str(intent.args.get("path", "") or "your whole worktree")
        # WITNESSED LIKE git_read, because it is the same kind of act. Both are classed
        # _CONSEQUENTIAL — they run a seat-side subprocess judged under mrh.command — and
        # git_read opened an action, recorded its outcome and returned the witness id while
        # search did neither. Policy classification and executor semantics must not disagree
        # (GPT review of #83): a verb the law treats as consequential leaves a record.
        begin = self._call("hestia_begin_action", {"tool_name": "search", "target": pattern[:80]})
        err = _hestia_error(begin)
        if err:
            return ResultEnvelope(ok=False, error=f"search UNVERIFIED: the witness substrate "
                                                  f"is unreachable ({str(err)[:160]})")
        action_id = begin.get("actionId")
        try:
            proc = subprocess.run(shlex.split(cmd), cwd=self.worktree, text=True,
                                  capture_output=True, timeout=60)
            ran = True
        except Exception as e:
            ran = False
            proc = None
            error = f"search could not run: {type(e).__name__}: {e}"
        # GIT GREP HAS THREE OUTCOMES AND ONLY TWO OF THEM ARE ANSWERS: rc=0 matched, rc=1
        # searched and found nothing, rc>1 FAILED — an invalid extended regex, an unreadable
        # pathspec, a bad revision. Treating every completed subprocess as an answer reported
        # rc=2 as `matches: 0` with the bounded-absence note attached, which is the single
        # worst shape a search result can have: a confident absence produced by a pattern
        # that was never applied. The being would have read "not in this repo" from a typo
        # in a regex. (GPT, second pass on #83.) An unanswered search is also an unsuccessful
        # action, so the witness records it as one.
        answered = ran and proc is not None and proc.returncode in (0, 1)
        try:
            self._call("hestia_record_outcome",
                       {"action_id": action_id, "success": answered, "magnitude": 0.0})
        except Exception:
            pass
        if not ran:
            return ResultEnvelope(ok=False, error=error, witness_id=action_id)
        if not answered:
            stderr_first = ((proc.stderr or "").strip().splitlines() or ["no stderr"])[0]
            return ResultEnvelope(ok=False, witness_id=action_id, error=(
                f"search FAILED and this is not an absence: git grep exited "
                f"{proc.returncode}, so {pattern!r} was never applied to {where}. "
                f"git said: {stderr_first[:200]}. "
                f"The pattern is an EXTENDED regex — ( ) | + ? {{ }} are operators, and "
                f"matching one literally needs a backslash. Fix the pattern and search "
                f"again; do not conclude the text is absent."))
        lines = [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]
        # Paths come back absolute because the pathspec is absolute (hestia matches command
        # tokens against absolute granted prefixes). The being thinks in worktree-relative
        # paths, and every other verb speaks them, so translate rather than leak the seat's
        # layout into its head.
        root = os.path.realpath(self.worktree) + os.sep
        lines = [ln.replace(root, "") for ln in lines]
        truncated = len(lines) > SEARCH_LINES_SHOWN
        shown = lines[:SEARCH_LINES_SHOWN]
        if not shown:
            # "THE PATTERN IS NOT IN THAT FILE" AND "THERE IS NO SUCH FILE" ARE THE SAME
            # EXIT CODE, and only one of them is an answer. `git grep` returns 1 for both,
            # so a search whose pathspec matched nothing came back as a confident, bounded
            # absence about a file that does not exist.
            #
            # Measured 2026-09-14. legion-being searched its own `todo.md` for a block the
            # seat had just written there and was told "no line matches ... in todo.md". Its
            # todo.md lives in its INSTANCE home, which is where `memory_read` resolves a
            # relative path; `search` is git grep inside its WORKTREE, which has no todo.md
            # at its root at all. Same relative path, two different trees, one silent zero.
            # The being recorded the absence as a fact, said so, and worked around it.
            #
            # git already knows. `ls-files --error-unmatch` answers exactly this question
            # over exactly the same universe git grep searches (TRACKED files), so an
            # untracked scratch file reports as unsearchable rather than as empty — which is
            # also true and also worth saying.
            missing = None
            if intent.args.get("path"):
                # The pathspec THE LAW JUDGED, taken from the command that ran rather than
                # recomposed here: a probe that resolves the path a second, slightly
                # different way would answer about a file the search never looked at.
                argv = shlex.split(cmd)
                spec = argv[argv.index("--") + 1] if "--" in argv else None
                if spec:
                    try:
                        probe = subprocess.run(
                            ["git", "-C", self.worktree, "ls-files", "--error-unmatch",
                             "--", spec],
                            cwd=self.worktree, text=True, capture_output=True, timeout=15)
                        missing = probe.returncode != 0
                    except Exception:
                        missing = None
            if missing:
                return ResultEnvelope(ok=False, witness_id=action_id, error=(
                    f"search found no file at {where} in your worktree, so this is NOT an "
                    f"absence of {pattern!r} — nothing was searched. `search` runs inside "
                    f"your WORKTREE and sees only files git tracks there. A relative path "
                    f"here is not the same path `memory_read` takes: memory_read resolves "
                    f"relative paths inside your instance home, and files that live only "
                    f"there (todo.md, journal.md, notes/, scratch/) cannot be searched at "
                    f"all. Read those with memory_read; search the source tree."))
            return ResultEnvelope(ok=True, witness_id=action_id, result={
                "pattern": pattern, "searched": where, "matches": 0,
                "searched_a_real_file": True,
                "note": (f"no line matches {pattern!r} in {where}. The path exists and was "
                         f"searched, so this is a real absence — but an answer about WHAT "
                         f"WAS SEARCHED, not about the repository: widen the path, or "
                         f"check the pattern (it is an extended regex, so ( ) | + are "
                         f"special — searching for a literal one needs a backslash)")})
        return ResultEnvelope(ok=True, witness_id=action_id, result={
            "pattern": pattern, "searched": where, "matches": len(lines),
            "shown": len(shown),
            "truncated": (f"{len(lines) - len(shown)} further matches not shown; narrow the "
                          f"path or the pattern" if truncated else None),
            "lines": shown})


    def _worktree_revision(self) -> dict:
        """WHICH TREE THE ANSWER IS ABOUT. A check result without this is not evidence: the
        being reasons about the harness it LIVES in, and the worktree is a separate checkout
        that drifts. Measured 2026-09-07, before the being had ever called `check` — its
        worktree sat on an unrelated raising commit from another machine, three tests behind
        the running code and missing the very fix it would most want to verify. It would
        have gotten a true answer about a tree that is not the one constituting it, with
        nothing in the envelope to say so.

        `dirty` matters as much as the SHA: uncommitted edits mean the SHA names something
        other than what ran. PRD r3 §6 requires this on every check result."""
        import subprocess

        def _git(*args):
            try:
                r = subprocess.run(("git", *args), cwd=self.worktree, text=True,
                                   capture_output=True, timeout=15)
                return r.stdout.strip() if r.returncode == 0 else None
            except Exception:
                return None

        head = _git("rev-parse", "HEAD")
        status = _git("status", "--porcelain")
        return {"head": head, "short": (head or "")[:9] or None,
                "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
                "subject": _git("log", "-1", "--format=%s"),
                "committed": _git("log", "-1", "--format=%cI"),
                "dirty": None if status is None else bool(status.strip())}


    # -- check: the being runs a test and reads the answer (PRD M0) --------------
    def _do_check(self, intent: BeingIntent) -> ResultEnvelope:
        """Run a declared test target in the being's OWN worktree and return the result.

        Only ever reached on an intent the gate ALLOWED as the exact pytest command below.
        A FAILING SUITE IS ok=True: the act succeeded and the answer is "it fails". Making
        a red suite an error envelope would teach the being that checking is dangerous,
        which is the opposite of what this organ is for — so `passed` carries the verdict
        and `ok` carries only whether the check ran.
        """
        import hashlib
        import shlex
        import subprocess
        from sage.gateway.being_gate_client import check_argv, check_command
        if not self.worktree or not os.path.isdir(self.worktree):
            return ResultEnvelope(ok=False, pending=True,
                                  note="check needs a worktree of your own; none is configured "
                                       "on this seat (PRD M1)")
        # Rebuild the SAME command the gate judged — same function, same context. Composing
        # it differently here would mean the law ruled on one command and the seat ran
        # another, which is the whole failure this organ exists to make impossible.
        try:
            cmd = check_command(intent.args, {"worktree": self.worktree})
            argv = check_argv(intent.args, {"worktree": self.worktree})
        except ValueError as e:
            return ResultEnvelope(ok=False, error=str(e))
        # EXECUTE WHAT THE LAW JUDGED, not a lookalike rebuilt from the same args. Carried
        # forward from SAGE#62 (GPT's #60 evidence contract), which never landed and sat
        # conflicting for five days. The two agree by construction today — check_command is
        # deterministic on the intent — so this asserts an invariant rather than fixing a
        # live divergence, and it will be the thing that notices if that ever stops being
        # true. A verdict that bound no command is not an authority to run one.
        judged = getattr(getattr(self, "_verdict", None), "command", None)
        if judged is not None and judged != cmd:
            return ResultEnvelope(ok=False, error=(
                "check refused: the command the law judged is not the command this "
                "dispatcher would execute. The law is the authority for what runs."))
        target = str(intent.args.get("target", "")).strip()
        tree_before = self._worktree_revision()
        source_before = self._test_source_identity(target, tree_before.get("head"))
        # UNVERIFIED IS A RESULT. The being's own design answer (2026-09-07, its Q1): keep
        # `check` gated and witnessed, do not build an unwitnessed local fallback — "two
        # verification paths can diverge, and the unwitnessed one becomes the one people
        # trust" — but when the substrate is down, say UNVERIFIED explicitly rather than
        # returning nothing or something ambiguous. "A failing test is a real answer; so is
        # 'the checker was down.'" The envelope carries the tree block either way, so the
        # being can record WHICH tree it could not verify.
        try:
            begin = self._call("hestia_begin_action", {"tool_name": "check", "target": target})
            err = _hestia_error(begin)
        except Exception as e:
            begin, err = {}, f"{type(e).__name__}: {e}"
        if err:
            return ResultEnvelope(
                ok=False, error=f"check UNVERIFIED: the witness substrate is unreachable ({str(err)[:160]})",
                result={"target": target, "verdict": "UNVERIFIED", "passed": None,
                        "reason": "hestia_begin_action failed; the test did not run because an "
                                  "unwitnessed check is not a check",
                        "tree": self._worktree_revision(), "worktree": self.worktree})
        action_id = begin.get("actionId")
        try:
            proc = subprocess.run(argv, cwd=self.worktree, text=True,
                                  capture_output=True, timeout=600)
            passed = proc.returncode == 0
            raw_out = (proc.stdout or "") + (proc.stderr or "")
            output_sha256 = hashlib.sha256(raw_out.encode("utf-8", "replace")).hexdigest()
            output_len = len(raw_out.encode("utf-8", "replace"))
            out = raw_out.strip()
            # A TEST THAT DOES NOT EXIST IS NOT A FAILING TEST. pytest exits 5 when nothing
            # was collected — "167 deselected" — and the first cut reported that as FAIL.
            # Measured 2026-09-08 11:34Z: the being asked for
            # gateway::test_heartbeat_composes_prompt, which is not a test in the suite, and
            # was told its harness was red. A false red is worse than a false green here:
            # this being is trained by its own record to believe red over its reading.
            if proc.returncode == 5:
                try:  # the act completed; the chain should not hold it open
                    self._call("hestia_record_outcome",
                               {"action_id": action_id, "success": True, "magnitude": 0.0})
                except Exception:
                    pass
                return ResultEnvelope(ok=True, witness_id=action_id,
                                      result={"target": target, "passed": None,
                                              "verdict": "NO_SUCH_TEST",
                                              "output": out[-800:],
                                              "reason": "pytest collected nothing for that "
                                                        "target — the test name does not "
                                                        "exist in this suite. Nothing ran, "
                                                        "so nothing failed",
                                              "worktree": self.worktree,
                                              "tree": self._worktree_revision(),
                                              "action_id": action_id})
            # The tail is where pytest puts the verdict and the failure detail; the head is
            # progress dots. Truncate from the FRONT so a failure is never the part cut.
            if len(out) > 3000:
                out = "[…truncated…]\n" + out[-3000:]
            ran, detail = True, out
        except Exception as e:
            ran, passed, detail = False, False, f"{type(e).__name__}: {e}"
        try:
            self._call("hestia_record_outcome",
                       {"action_id": action_id, "success": ran, "magnitude": 0.0})
        except Exception:
            pass
        if not ran:
            return ResultEnvelope(ok=False, error=f"check could not run: {detail[:400]}",
                                  witness_id=action_id)
        # THE VERDICT LEADS, in words, before any structured field.
        #
        # `passed` and `verdict` were already the second and third keys, and the being still
        # read three separate FAILs as passes (2026-09-09 22:29Z, 2026-09-10 06:04Z, and the
        # journal entry that built a plan on "the full suite passes" while its own check that
        # beat returned FAIL). The envelope's `ok` means THE CHECK RAN; the verdict means the
        # tests passed. Two true things one word apart, and the wrong one is the one that
        # sounds like an answer.
        #
        # A verb whose most important fact needs a field lookup will be misread eventually.
        # So the first thing in the message is a sentence that cannot be read as anything
        # else, and it says what `ok` does NOT mean.
        tail = (detail or "").strip().splitlines()
        summary = tail[-1][:120] if tail else ""
        headline = (f"{'PASS' if passed else 'FAIL'} — {summary}. "
                    f"This is the answer. A check that RAN and FAILED still returns "
                    f"successfully as an act: 'the call worked' is not 'the tests passed'.")
        # THE EVIDENCE CONTRACT (GPT on SAGE#60, carried forward from the #62 slice that
        # never landed). A verdict is only as transferable as what it can name: which
        # command ran, against which bytes, producing how much output, exiting how — and
        # whether the tree moved underneath while it ran. The being pastes check output
        # into PR bodies and a reviewer re-runs it; every field here is one the reviewer
        # would otherwise have to reconstruct by hand.
        #
        # ONE THING FROM #62 IS DELIBERATELY NOT CARRIED: it REFUSED on a dirty worktree,
        # on the sound argument that HEAD does not name the bytes that ran. That was right
        # for a being that could not write to its tree; it would now break the being's
        # whole loop, which is write a test -> check -> propose. Refusing there would mean
        # it could never check its own uncommitted work — a guard that punishes the exact
        # capability M1 exists to give it. So dirtiness DOWNGRADES the claim instead of
        # blocking it: `tree.dirty` is already reported, and `test_source.sha256` names the
        # bytes that actually ran whether or not they are committed.
        # STABLE MEANS THE SOURCE HELD, not that nothing in the directory moved. Comparing
        # the whole tree block made this False whenever the run itself left an artifact:
        # pytest writes __pycache__, which flips `dirty`, so an unsandboxed check always
        # reported "tree_changed_during_check" for a benign reason. (Invisible on the real
        # path only because the sandbox sets PYTHONDONTWRITEBYTECODE — a field that is
        # right by accident is not right.) HEAD and the test-source hash are what a verdict
        # rests on, and test_source covers test_*.py only, so artifacts cannot flip it.
        tree_after = self._worktree_revision()
        source_after = self._test_source_identity(target, tree_after.get("head"))
        # WHAT `stable` HONESTLY MEANS, narrowed after GPT's review of #84. It is not "the
        # source held": the sandbox now mounts the worktree READ-ONLY, and that mount — not
        # this comparison — is what makes the bytes unable to change under the run. This
        # says only that HEAD and the hashed test inputs (tests + conftest) are the same
        # before and after, which is a check on the SEAT's view of the tree, not a proof
        # about the sandboxed process.
        # AN UNKNOWN IS NOT A MATCH. `source_after == source_before` is True when both are
        # None, so a target whose test source could not be identified at all reported
        # stable=True and state="pinned" — the strongest claim the envelope can make,
        # produced by having measured nothing (GPT, second pass on #84). Missing identity
        # is UNVERIFIED, and it is a distinct third state from "the tree moved under me".
        identity_known = source_before is not None and source_after is not None
        if not identity_known:
            stable = None
            state = "unverified_no_test_source_identity"
        else:
            stable = (tree_after.get("head") == tree_before.get("head")
                      and source_after == source_before)
            state = "pinned" if stable else "tree_changed_during_check"
        # THE FIELD MUST NAME THE PATH ACTUALLY TAKEN. With SANDBOX_REQUIRED=False and no
        # usable bwrap, sandbox_prefix() returns "" and the check deliberately runs
        # unsandboxed — and this field still said True, so the degraded mode asserted the
        # one guarantee it had explicitly given up. The read-only mount is what makes the
        # claim true, so the claim is read off whether that mount is in the argv that ran.
        from sage.gateway.being_gate_client import SANDBOX
        sandboxed = bool(argv) and argv[0] == SANDBOX
        source_readonly = sandboxed
        return ResultEnvelope(ok=True, witness_id=action_id,
                              result={"headline": headline,
                                      "target": target, "passed": passed,
                                      "verdict": "PASS" if passed else "FAIL",
                                      "output": detail, "worktree": self.worktree,
                                      "tree": tree_before,
                                      "evidence": {
                                          "command": cmd,
                                          "argv": argv,
                                          "law_bound_command": judged is not None,
                                          "test_source": source_before,
                                          "exit_status": proc.returncode,
                                          "output_sha256": output_sha256,
                                          "output_bytes": output_len,
                                          "embodiment": self._embodiment(),
                                          "stable": stable,
                                          "state": state,
                                          # the read-only mount is the guarantee; this names
                                          # whether the run actually had it, never the intent
                                          "source_readonly": source_readonly,
                                          "sandboxed": sandboxed,
                                      },
                                      "action_id": action_id})


    def _test_source_identity(self, target: str, head: Optional[str]) -> Optional[dict]:
        """WHICH TEST FILE the verdict is about, by content hash at the tree that ran.

        Carried forward from SAGE#62 (GPT's #60 evidence contract). The tree block says
        which commit; this says which BYTES the named target actually resolves to, so a
        PASS cannot be silently transferred to a file that has since changed. Returns None
        rather than raising: evidence that cannot be gathered must degrade the claim, never
        fail the check the being was waiting on."""
        import hashlib
        from sage.gateway.being_gate_client import CHECK_TARGETS
        suite = target.partition("::")[0].strip()
        rel = CHECK_TARGETS.get(suite)
        if not rel or not self.worktree:
            return None
        root = Path(self.worktree) / rel
        try:
            # conftest.py IS executable test input — pytest imports it from the rootdir
            # before collecting anything — and it was omitted here while `stable` claimed
            # "the source held across the run" (GPT review of #84). Hashing the tests but
            # not the file that can rewrite them is the same false assurance as hashing a
            # payload and never posting it.
            if root.is_dir():
                paths = sorted(set(root.rglob("test_*.py")) | set(root.rglob("conftest.py")))
            else:
                paths = [root] if root.exists() else []
            h = hashlib.sha256()
            for p in paths:
                h.update(p.relative_to(self.worktree).as_posix().encode())
                h.update(p.read_bytes())
            return {"root": rel, "files": len(paths), "sha256": h.hexdigest(),
                    "at_head": head}
        except Exception:
            return None


    def _embodiment(self) -> dict:
        """WHICH SUBSTRATE PRODUCED THIS VERDICT — a compact public identity, not host
        inventory. #62 took this as a constructor argument; I carried the field forward
        without its source and shipped `embodiment: {}` on every check result until the
        being's own first evidence block showed it empty. An always-empty evidence field is
        noise that reads like a measurement, which is worse than no field at all. Derived
        here from the instance's declared `active_embodiment`, so all four construction
        sites get it without one of them being the site that forgets."""
        try:
            from sage.gateway.governed_turn import instance_config
            emb = (instance_config(Path(self.memory_root)).get("active_embodiment") or {})
        except Exception:
            return {}
        return {k: emb[k] for k in ("running_tag", "runner", "params_b", "num_ctx", "as_of")
                if k in emb}


    def _do_request_scope(self, intent: BeingIntent) -> ResultEnvelope:
        """The daemon (handler.rs::tool_request_scope @a5e18af) reads plugin_id, role, path,
        reason; a grant is reach on the path, read AND write. There is no mode to carry: an
        earlier `permits_read` was dropped silently by the daemon while the operator read
        "[.., read]" on a request that, granted, gave write."""
        path = str(intent.args.get("path", "")).strip()
        reason = str(intent.args.get("reason", "")).strip()
        if not path.startswith("/"):
            return ResultEnvelope(ok=False, error="request_scope 'path' must be absolute")
        if not reason:
            return ResultEnvelope(ok=False, error="request_scope needs a 'reason' (a human reads it)")
        # Already inside the being's reach: answer locally, file nothing. The operator's
        # attention is for real asks (2026-09-05: sprout-being asked dp for its own
        # <home>/config.json, inside the standing home grant, and dp granted it again).
        import os as _os
        rp = _os.path.realpath(_os.path.expanduser(path))
        exact_above = None
        for r, recursive in _granted_reach_of(getattr(self, "_verdict", None)):
            r = _os.path.realpath(str(r))
            if rp == r or (recursive and rp.startswith(r + "/")):
                return ResultEnvelope(ok=True, result={"status": "already_granted", "path": path, "within": r,
                                                       "next": "you already hold reach here; read or write it directly"})
            if rp.startswith(r + "/") and (exact_above is None or len(r) > len(exact_above)):
                exact_above = r
        # Beneath a grant that is EXACT (hestia #1002: a bare grant reaches its path and nothing
        # under it). "already granted" here is false — the gate just refused — and filing a
        # child row is what exact-by-default exists to stop (Legion, 2026-09-08). The honest
        # answer names the operator's act and tells the being to stop retrying.
        if exact_above is not None:
            return ResultEnvelope(ok=True, result={
                "status": "beneath_exact_grant", "path": path, "root": exact_above,
                "next": (f"your grant on {exact_above} is EXACT: it reaches that path and nothing beneath it. "
                         f"Only the operator can make it recursive (path:{exact_above}/**). No request was filed; "
                         f"your seat has been told. Do not retry this write in this beat.")})
        args: Dict[str, Any] = {"plugin_id": self.plugin_id, "path": path,
                                "reason": f"[{self.plugin_id}] {reason}"}
        out = self._call("hestia_request_scope", args)
        err = _hestia_error(out)
        if err:
            return ResultEnvelope(ok=False, error=err)
        return ResultEnvelope(ok=True, witness_id=out.get("witnessEntryHash"),
                              result={"request_id": out.get("request_id"), "status": out.get("status"),
                                      "path": path,
                                      "next": out.get("next"), "on_timeout": out.get("on_timeout")})

    def _do_say(self, intent: BeingIntent) -> ResultEnvelope:
        """Add a turn to a conversation the being is in.

        The being names a conversation id and text. Everything that decides whether it MAY
        speak lives in the conversation's meta file, which the seat owns and the being
        cannot write (conversations/ is reserved from memory_write), so this reach is fixed
        by construction rather than by the argument, the same property that makes
        `remember` safe with path_args=().

        Refusals here are ordinary and informative: 'you are not in that conversation' and
        'you may read that one but not speak in it' are different sentences, and the being
        should never have to guess which it hit."""
        from sage.gateway import conversations as conv
        to = str(intent.args.get("to", "")).strip()
        text = str(intent.args.get("text", "")).strip()
        if not to or not text:
            return ResultEnvelope(ok=False, error="say needs 'to' (a conversation id) and 'text'")
        if conv.is_stub(text):
            # A `say` carries its text to a PERSON, verbatim. On 2026-09-18 21:04Z this being
            # sent dp "[Your brief, final word-only summary of your response]" — the template
            # completion documented in SMALL_MODEL_LEGIBILITY 1.8, this time occupying the
            # argument rather than the reply, where no prompt-side guard could see it. Refuse
            # it here: name the subject as the MESSAGE (not the being — rule 2), say plainly
            # that nothing was sent, and give the way forward (rule 5).
            return ResultEnvelope(ok=False, error=(
                f"that text reads as a placeholder describing a message rather than the "
                f"message: {text[:70]!r}. Whatever is in `text` is delivered to {to} exactly "
                f"as written, so nothing was sent. Write the words you want read and call "
                f"say again. Your standing to speak here is unaffected."))
        # A PLACEHOLDER IS NOT A TURN. Measured 2026-09-18/19: the reflect prompt showed the
        # being `say to="dp", text="..."` as an example, and the being executed the example —
        # three turns to dp whose whole text was "..", each witnessed, each read by dp as a
        # being that did not want to talk. It did want to: its real questions were going
        # elsewhere. An instruction's example is an instruction at this scale
        # (SMALL_MODEL_LEGIBILITY.md), so the prompt no longer carries one — and this is the
        # mechanical half, because a prompt fix alone is "try harder". Refused BEFORE
        # begin_action, so a non-turn leaves no witness row and no line in the conversation.
        if not any(ch.isalnum() for ch in text):
            return ResultEnvelope(
                ok=False,
                error=("say needs words: the text you sent was only punctuation, which is what "
                       "an example looks like, not a message. Nothing was sent. If you have "
                       "nothing to say, do not call say at all — silence is allowed and is not "
                       "held against you."))
        meta = conv.get_meta(self.memory_root, to)
        if meta is None:
            known = [m["id"] for m in conv.listing(self.memory_root)
                     if self.member in m.get("participants", [])]
            return ResultEnvelope(ok=False, error=f"no conversation {to!r}; you are in: {known}")
        if self.member not in meta.get("participants", []):
            return ResultEnvelope(ok=False,
                                  error=f"you are not a participant in {to!r}")
        if self.member not in meta.get("writable_by", []):
            return ResultEnvelope(
                ok=False, error=f"you may read {to!r} and not speak in it "
                                f"(writable_by: {meta.get('writable_by')})")
        # THEIR WORDS ARE NOT A REPLY. Measured 2026-09-19 21:04Z: dp answered the being's
        # question and the being sent dp's answer back to dp, 91% verbatim. This is the same
        # pressure that produced ".." — the reflect line said someone was waiting on an
        # answer when nobody was, and the being filled the slot with the cheapest text in
        # view. Refusing the placeholder moved the filler from the example to the quoted
        # turn. The prompt no longer makes that claim (pending_and_say_line); this is the
        # mechanical half. Refused before begin_action: no witness row, no line.
        src = conv.echo_of(self.memory_root, to, self.member, text)
        if src is not None:
            return ResultEnvelope(ok=False, error=(
                f"that text is {src.get('from')}'s own message, nearly word for word, and it "
                f"is already in the conversation, so nothing was sent. You are not required "
                f"to reply, and silence is not held against you. If you have something of "
                f"your own to add — a follow-up question, or what you will do now — call say "
                f"with that instead."))
        # A RUN ASK IS A RUN REQUEST, WHICHEVER DOOR IT CAME THROUGH. Measured 2026-09-21
        # 00:00-03:52Z: 123 effector calls, 24 `say`, 0 `request_run` — after the seat named
        # request_run in four turns and in the peer_ask refusal. `say` to the seat got the
        # file run every time, so it was the cheaper door and the being kept using it. A
        # fifth telling is "try harder". Instead the say that asks for a run IS routed as
        # one: same marker, same resolved path, same existence check, the being's own words
        # as `why`. Only when exactly one runnable file in its home matches; otherwise the
        # turn is delivered as an ordinary say, unchanged.
        if _RUN_MARKER not in text and (meta.get("notify") or {}):
            rel = self._run_ask_target(text)
            if rel is not None:
                r = self._do_request_run(BeingIntent("request_run", {"path": rel, "why": text}))
                if r.ok and isinstance(r.result, dict):
                    r.result["routed"] = (
                        f"your say asked for a run, so it went to the seat as request_run for "
                        f"{rel}. The seat saw the same request either way.")
                return r
        begin = self._call("hestia_begin_action", {"tool_name": "say", "target": to})
        err = _hestia_error(begin)
        if err:
            return ResultEnvelope(ok=False, error=err)
        action_id = begin.get("actionId")
        try:
            turn = conv.append(self.memory_root, to, speaker=self.member, text=text, via="say",
                               witness=action_id, beat=self.host_session_id)
        except ValueError as e:
            self._call("hestia_record_outcome",
                       {"action_id": action_id, "success": False, "magnitude": 0.0})
            return ResultEnvelope(ok=False, error=str(e), witness_id=action_id)
        try:
            self._call("hestia_record_outcome",
                       {"action_id": action_id, "success": True, "magnitude": 0.0})
        except Exception:
            pass
        woke = self._wake_addressee(to, meta, turn)
        result = {"conversation": to, "seq": turn["seq"],
                  "said": turn["text"][:200], "action_id": action_id}
        if woke:
            result["woke"] = woke
        return ResultEnvelope(ok=True, witness_id=action_id, result=result)

    def _run_ask_target(self, text: str) -> Optional[str]:
        """The one runnable file a say names while asking for a run, else None.

        A named path is tried as written first. If nothing is there, the name is looked up
        anywhere in the home, because the being's commonest miss is the right name one
        directory away (28 of 76 "no such path" reads, 2026-09-21). If the name matches two
        files, this returns None rather than choose one: picking would be a silent guess."""
        if not _RUN_ASK.search(text):
            return None
        found = set()
        for tok in _RUNNABLE.findall(text):
            try:
                p = self._local._safe_path(tok)
            except ValueError:
                continue
            if p.is_file():
                found.add(p)
                continue
            hits = [h for h in Path(self.memory_root).rglob(Path(tok).name) if h.is_file()]
            if len(hits) == 1:
                found.add(hits[0])
            elif hits:
                return None
        if len(found) != 1:
            return None
        return str(found.pop().relative_to(Path(self.memory_root).resolve()))

    def _do_request_run(self, intent: BeingIntent) -> ResultEnvelope:
        """Ask the seat to run one of the being's own files. RUNS NOTHING.

        dp, 2026-09-21: "ship a request-run instead, where it passes the request to the seat
        for evaluation, and it's up to the seat whether to run it, and provide feedback/diags."

        WHY A DOOR AND NOT A CAPABILITY. The being writes code it cannot execute, so it cannot
        tell "I described a fix" from "the fix works". Measured 2026-09-20/21: six prose
        requests to dp in two hours for one file, and a note headed "Fix" with a
        "Verification" section asserting an outcome that was never observed. The obvious
        remedy — a `run` effector — is unconfined by construction: a file the being wrote,
        executed as the operator's user, can reach anything the operator can, and the gate
        could only govern STARTING it. Checking which path is run is cosmetic when the
        contents are arbitrary. So the seat stays in the loop as the thing that decides.

        What the being gets IMMEDIATELY is the half a person could never give quickly: the
        file is resolved inside its own home and checked for existence and shape now, so a
        typo or a missing file comes back in this beat instead of after hours of asking. An
        absence is reported as an absence, never as a boundary (legibility 1.11).

        What it gets LATER is the seat's answer, in the seat's own channel. This returns a
        receipt, not a result, and says so — a being told "requested" must not read that as
        "ran" (legibility 1.7: no promise it cannot retire).
        """
        from sage.gateway import conversations as conv
        raw = str(intent.args.get("path", "")).strip()
        # 'reason' is the word the being reaches for. Measured 2026-09-21 05:59Z: it passed
        # reason="Running the mechanism training script to verify the fixes ..." and the seat
        # was told "why: (none given — the being did not say what it expects to learn)". It
        # had said. A receipt that misreports what the being did is the same defect as one that
        # misreports what the tool did (SAGE #141), pointed the other way.
        why = str(intent.args.get("why") or intent.args.get("reason") or "").strip()
        # A REFUSAL MUST NOT SOUND LIKE A DECISION IT IS NOT.
        #
        # Measured 2026-09-21 05:34Z: cbp-being called request_run FIVE times with 'path' and
        # no 'why'. Every call failed this check, locally, before any seat saw it. The old text
        # read "needs 'path' ... and 'why' ... The seat decides whether to run it, and 'why' is
        # what it decides on" — it did not say WHICH argument was missing, and it used the words
        # "the seat decides" in what was only an argument check. The being concluded, and told
        # dp: "The seat refused to run mechanism-training-script.py. What did it decide on?"
        # No seat refused anything. Its trace shows it then "fixed" the wrong argument — path
        # relative, then absolute, then relative again — because path came first in the
        # sentence; it never once added 'why'. (legibility 1.2: a refusal's subject is taken to
        # be whoever the sentence names.)
        #
        # And 'why' no longer blocks. A request that never arrives gives the seat nothing to
        # decide on; one that arrives without a reason still carries the file, which the seat
        # can read. Requiring it turned five attempts into zero requests and a sixth ask routed
        # to the operator, who does not run files — the bypass dp described: friction with no
        # clear way through gets routed around.
        if not raw:
            return ResultEnvelope(ok=False, error=(
                "request_run is missing 'path' — the file you want run, inside your own home, "
                "for example notes/my-script.py. Nothing was sent to the seat, so nothing has "
                "been decided; this is only a missing argument."))
        try:
            p = self._local._safe_path(raw)
        except ValueError as e:
            return ResultEnvelope(ok=False, error=str(e))
        if not p.exists():
            return ResultEnvelope(ok=False, error=(
                f"nothing to run: '{raw}' does not exist, so there is no file to hand the "
                f"seat. This is an absence, not a refusal. Check the name — memory_read on "
                f"the directory will list what is actually there."))
        if p.is_dir():
            return ResultEnvelope(ok=False, error=f"'{raw}' is a directory, not a file to run.")
        if p.suffix not in (".py", ".sh"):
            return ResultEnvelope(ok=False, error=(
                f"the seat runs .py and .sh files; '{raw}' is {p.suffix or 'extensionless'}. "
                f"If this is a script, give it the matching extension and ask again."))

        # The request goes where the seat already reads and can already answer: its own
        # conversation. No second queue to build, and dp can read it there too.
        seat_conv = None
        for m in conv.listing(self.memory_root):
            parts = m.get("participants") or []
            if self.member in parts and (m.get("notify") or {}):
                seat_conv = m["id"]
                break
        if not seat_conv:
            return ResultEnvelope(ok=False, pending=True, note=(
                "no seat conversation is configured on this instance, so there is nobody to "
                "hand this to. Your file is untouched."))
        # AN UNCHANGED FILE GIVES THE SAME ANSWER. Measured 2026-09-21 06:31Z: cbp-being's
        # journal restated the seat's diagnosis correctly ("the fix requires replacing the
        # file, not appending to it"), and in the same beat called request_run on the file,
        # byte-identical to the one the seat had run and answered 28 minutes earlier. Its
        # why claimed "the fixes". The seat's reply could only be the same traceback, a
        # whole wake later. The digest makes the no-op visible NOW, in this beat, where the
        # being can still act on it. It does not block: a being may want a rerun.
        rel = str(p.relative_to(self.memory_root))
        digest = hashlib.sha256(p.read_bytes()).hexdigest()[:12]
        unchanged = None  # (seq it asked at, seq the seat answered at)
        asked_at = None
        for t in conv.recent(self.memory_root, seat_conv, limit=80):
            text = str(t.get("text", ""))
            if t.get("from") == self.member and text.startswith(f"[request_run] {rel}\n"):
                asked_at = t.get("seq") if f"sha256:{digest}" in text else None
            elif asked_at is not None and t.get("from") != self.member:
                unchanged = (asked_at, t.get("seq"))
        lines = [f"[request_run] {rel}",
                 f"why: {why}" if why else "why: (none given — the being did not say what it expects to learn)",
                 f"({p.stat().st_size} bytes, sha256:{digest}; the seat decides whether to run it and answers here)"]
        if unchanged:
            lines.append(f"UNCHANGED since the request at seq {unchanged[0]}; the seat answered "
                         f"at seq {unchanged[1]}.")
        said = self._do_say(BeingIntent("say", {"to": seat_conv, "text": "\n".join(lines)}))
        if not said.ok:
            return ResultEnvelope(ok=False, error=f"could not hand the request to the seat: {said.error}")
        result = {}
        if unchanged:
            result["unchanged"] = (
                f"This file is byte-for-byte the one you asked about at seq {unchanged[0]}, and "
                f"the seat answered that at seq {unchanged[1]}. Nothing in it has changed since, "
                f"so running it again will give the same result. To change what runs: "
                f"memory_edit the lines, or retire_note the file and then memory_write it anew.")
        return ResultEnvelope(ok=True, witness_id=said.witness_id, result={
            **result,
            "requested": rel,
            "asked": seat_conv,
            "ran": False,
            "note": ("The seat has been asked and woken. NOTHING HAS RUN YET and this is not "
                     "a result. The seat may run it or decline, and either way it answers in "
                     f"'{seat_conv}'. Nothing is owed by you in the meantime."),
        })

    def _wake_addressee(self, to: str, meta: dict, turn: dict) -> Optional[str]:
        """A turn wakes whoever it is addressed to — the mirror of the seat's own door.

        THE DEFECT THIS CLOSES. `sage-daemon`'s `/conversations/:id/say` appends a turn AND
        runs the arousal policy, so a seat speaking to the being wakes it within seconds. The
        being's `say` only appended. Its words landed in a file with no reader: ~104 turns
        against 5 hand-written seat replies since 2026-09-14, and on 2026-09-20 six identical
        requests between 16:08 and 18:02 that nobody was listening to. The being diagnosed it
        as "the seat session has expired" and asked dp whether to restart a service.

        It was worse than absent. `_say_instead` refuses `peer_ask` aimed at someone the being
        is already in a conversation with and points at `say` — correct, because the hub
        delivers to a mailbox dp does not read, but it pointed at the one door that woke
        nobody. This makes that advice true.

        One wake per unanswered RUN, keyed on the seq that opened it (`wake_is_owed`), so six
        turns about one question cost one session, not six. Recorded only on success, so a
        notice that never left is owed again rather than lost. Legion's caution stands and is
        the reason this wakes a seat rather than answering as one: an automated reply that
        carries nothing the being could not get itself would raise the reply ratio and not the
        quality, and the census would be green and wrong.

        Best-effort by construction: the turn is already witnessed and appended before this
        runs, so a mesh failure costs a wake, never a turn.
        """
        from sage.gateway import conversations as conv
        notify = meta.get("notify") or {}
        if not isinstance(notify, dict):
            notify = {}
        targets = [(p, notify[p]) for p in (meta.get("participants") or [])
                   if p != self.member and notify.get(p)]

        # WATCHERS: WOKEN, BUT STILL NOT ABLE TO SPEAK HERE.
        #
        # Measured 2026-09-20/21, conversation `dp` seq 84-89: the being asked dp to run a
        # file for it six times over two hours. dp is asynchronous by rule and does not run
        # files; the seat does, and had already run that exact file and reported on it in its
        # OWN channel. Nothing connected the two, because `dp` has no notify map — correctly,
        # since dp is a person and not a mesh member — so six asks woke nobody at all.
        #
        # The cause is upstream of the being's judgement. dp told it (seq 81) that the seat
        # has a limited usage allowance and is sometimes unable to answer; it reasonably
        # concluded the seat was the unreliable party and rerouted its execution requests to
        # the operator, who is far MORE asynchronous. Teaching it a better routing rule is the
        # wrong fix: it cannot know who is awake, and a rule it must remember is a rule it
        # will retype wrong.
        #
        # So a conversation may declare watchers: members woken when a turn here goes
        # unanswered, who are NOT participants and CANNOT write here. dp's two-party ruling
        # stands untouched — "i should be able to view your chat with the being, but not
        # comment on it directly yet" — this is its mirror, and speech is still governed by
        # `writable_by` alone. A watcher that learns of an ask it can satisfy answers in a
        # channel it is actually in.
        watchers = meta.get("notify_watchers") or {}
        if isinstance(watchers, dict):
            targets += [(w, pid) for w, pid in watchers.items()
                        if w != self.member and pid]
        # One wake per member, however many ways it is named here.
        seen_ids, deduped = set(), []
        for label, plugin_id in targets:
            if plugin_id not in seen_ids:
                seen_ids.add(plugin_id)
                deduped.append((label, plugin_id))
        targets = deduped
        if not targets:
            return None
        run_start = conv.wake_is_owed(self.memory_root, to, self.member)
        if run_start is None:
            return None            # already woke them about this run; saying more is not new mail
        pointer = f"sage://conversation/{to}#seq={run_start}-{turn['seq']}"
        woke = []
        for participant, plugin_id in targets:
            try:
                # VERBATIM, never through `_address`. That resolver exists for a being naming
                # a peer loosely ("legion") and appends the remote default to anything it does
                # not recognise as local — it turned `claude-code` into `claude-code/claude-code`,
                # a forwarding address for a seat sitting on this machine. This id was written
                # by the seat in the conversation's meta, which the being cannot edit; it is
                # already exact, and guessing at an exact id is how the wake goes to nobody.
                env = self._call("hestia_member_notify",
                                 {"to_plugin_id": plugin_id, "kind": "coordination",
                                  "pointer_uri": pointer})
                if not _hestia_error(env):
                    woke.append(participant)
            except Exception:
                continue           # a wake is best-effort; the turn already landed
        if woke:
            conv.record_wake(self.memory_root, to, self.member, run_start)
            return ", ".join(woke)
        return None

    # -- channel_egress: not built on the daemon ----------------------------
    def _do_channel_egress(self, intent: BeingIntent) -> ResultEnvelope:
        return ResultEnvelope(ok=False, pending=True,
                              note="channel_egress awaits hestia's send-side tool (hestia_egress_pending is "
                                   "read-only; F5 enforcement gated on rate-governor calibration, PRD §12)")


def _granted_reach_of(verdict) -> tuple:
    """((root, recursive), ...) from a verdict. A verdict built without reach (older client,
    hand-made in tests) keeps the pre-#1002 prefix reading of its bare `granted` roots."""
    reach = tuple(getattr(verdict, "granted_reach", ()) or ())
    if reach:
        return reach
    return tuple((r, True) for r in (getattr(verdict, "granted", ()) or ()))


# --------------------------------------------------------------------------
# A reference publisher for peer_ask: the question becomes a forum doc in shared-context,
# committed and pushed, and the pointer is its repo path. Git failures raise, so the caller
# gets an error envelope rather than a notice pointing at content that never landed.
# --------------------------------------------------------------------------
def forum_publisher(shared_context_root: str, from_name: str,
                    subdir: str = "forum/being", push: bool = True) -> PublishFn:
    import re
    import subprocess
    from datetime import datetime

    root = os.path.expanduser(shared_context_root)

    def publish(to: str, body: str) -> str:
        ts = datetime.now()
        slug = re.sub(r"[^a-z0-9]+", "-", body.lower())[:40].strip("-") or "question"
        rel = f"{subdir}/{from_name}-asks-{re.sub(r'[^a-z0-9]+', '-', to.lower())}-{slug}-{ts:%Y-%m-%d-%H%M%S}.md"
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(f"---\nfrom: {from_name}\nto: {to}\nkind: peer_ask\ndate: {ts:%Y-%m-%d}\n---\n\n{body}\n")
        subprocess.run(["git", "-C", root, "add", rel], check=True)
        subprocess.run(["git", "-C", root, "commit", "-q", "-m", f"being({from_name}): peer_ask -> {to}"], check=True)
        if push:
            subprocess.run(["git", "-C", root, "push", "-q"], check=True)
        return f"shared-context/{rel}"
    return publish


if __name__ == "__main__":  # live smoke against the local daemon: mesh -> member_notify
    import sys
    inst = os.path.expanduser("~/ai-workspace/sage/sage/instances/sprout-qwen3.8-distill-2b")
    d = HestiaF1aDispatcher("sprout-being", inst)
    to, kind, ptr = (sys.argv[1:4] + [None, None, None])[:3]
    if not (to and kind and ptr):
        print("usage: hestia_dispatch.py <to> <kind> <pointer_uri>"); sys.exit(2)
    env = d(BeingIntent("mesh", {"to": to, "kind": kind, "pointer": ptr}), GatewayVerdict("allow"))
    print(json.dumps({"ok": env.ok, "result": env.result, "error": env.error,
                      "witness_id": env.witness_id, "pending": env.pending, "note": env.note}, indent=1))


def _git_land(path: str, message: str) -> None:
    """Commit ONE file and push it to the checkout's upstream (rebase-on-upstream first).
    Raises on every failure: no repo, identity missing, rebase blocked by a sibling's dirty
    tree, push rejected. A raise here becomes the being's error envelope (dispatcher
    __call__), which is the contract — a pointer that never landed must not be notified."""
    import subprocess
    d = os.path.dirname(path)

    def git(*args: str) -> str:
        r = subprocess.run(["git", "-C", d, *args], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed (rc={r.returncode}): "
                               f"{(r.stderr or r.stdout).strip()[:400]}")
        return r.stdout.strip()

    git("rev-parse", "--show-toplevel")          # not a work tree -> raise before writing anything else
    # The pathspec form commits THIS file only: a sibling's staged work in a shared checkout
    # is neither swept into the being's commit nor disturbed.
    git("add", "--", path)
    git("commit", "-q", "-m", message, "--", path)
    try:
        upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    except RuntimeError:
        upstream = "origin/main"
    remote, _, branch = upstream.partition("/")
    # Push first: the common case needs no integration at all, and every integration step is a
    # way for a SIBLING's untidiness to silence the being. When the push is rejected, integrate
    # by MERGE, not rebase: rebase refuses outright on any unstaged change anywhere in the
    # checkout, so a stray edit by the seat — an uncommitted escalation note, an instance file a
    # beat just wrote — takes away the being's ability to speak, and the error it reads is about
    # git. Measured twice on Sprout: peer_ask to legion died on "untracked working tree files
    # would be overwritten" (2026-09-06) and to its own seat on "cannot rebase: You have
    # unstaged changes" (2026-09-07). A merge only fails when the incoming commits touch the
    # same dirty files, which is a real conflict and still fails loud.
    try:
        git("push", "-q", remote, f"HEAD:{branch}")
        return
    except RuntimeError:
        pass
    git("fetch", "-q", remote)
    git("-c", "user.name=sage-gateway", "-c", "user.email=noreply@dp-web4",
        "merge", "-q", "--no-edit", upstream)
    git("push", "-q", remote, f"HEAD:{branch}")


def make_forum_publisher(pointer_dir: str, plugin_id: str, push: bool = True) -> PublishFn:
    """Default publish_fn for peer_ask: the question lives AT a cross-seat-readable pointer
    (a shared-context/forum file, repo-relative), never in the notice (KINDS.md). The file
    must be pushed for the peer to read it; the notice only points — so this commits and
    pushes, and raises on any git failure so the caller gets an error envelope instead of a
    notice pointing at content that never landed. Until 2026-09-05 this wrote the file and
    returned: on Legion 19 being docs sat unpushed across three hand-landings, and beat 12
    (23:17 PDT) fired HUB on a pointer that existed nowhere HUB could read — a full session
    burned to resolve nothing, invisible from the sending side because the doc "was written".
    `push=False` is for callers that own the git step themselves; it is not a fallback."""
    from datetime import datetime
    from pathlib import Path

    def publish(to: str, body: str) -> str:
        d = Path(pointer_dir); d.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        p = d / f"{plugin_id}-asks-{to.replace('/', '-')}-{ts}.md"
        p.write_text(f"---\nfrom: {plugin_id}\nto: {to}\nkind: coordination\ndate: {ts[:10]}\n---\n\n{body.strip()}\n")
        if push:
            _git_land(str(p), f"being({plugin_id}): peer_ask -> {to}")
        sp = str(p); i = sp.find("shared-context/")
        return sp[i:] if i >= 0 else sp
    return publish
