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

import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import subprocess

from sage.gateway.being_gate_client import (BeingIntent, GatewayVerdict, ResultEnvelope,
                                           camera_command)
from sage.gateway.hestia_witness import _ENDPOINT, _Mcp, _unwrap, make_hestia_witness_fn
from sage.gateway.reference_f1a import ReferenceF1aDispatcher

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


def _session_lost(exc: Exception) -> bool:
    """Whether this failure means the session is gone rather than the act refused.

    Narrow on purpose: only the shapes a restarted or recycled server produces. A broad
    match would retry real refusals, and a retried refusal reads as flakiness."""
    m = str(exc).lower()
    return ("session not found" in m or "404" in m
            or "session terminated" in m or "no valid session" in m)


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
                 # the being's OWN git worktree: where `check` runs and where it may
                 # edit code. Never the shared checkout (PRD M1).
                 worktree: Optional[str] = None):
        self.plugin_id = plugin_id
        self.worktree = worktree
        # the being's own home, and the name it speaks under in a conversation. plugin_id
        # IS the member name here (build_client passes the member), but bind it explicitly
        # rather than relying on that staying true.
        self.memory_root = memory_root
        self.member = plugin_id
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
        self.endpoint = endpoint
        self._publish = publish_fn
        self.remote_member_default = remote_member_default
        self.local_members = set(local_members or ())
        self.host_session_id = host_session_id
        self._mcp_factory = mcp_factory or _Mcp
        self._local = ReferenceF1aDispatcher(
            memory_root=memory_root,
            worktree=worktree,
            witness_fn=make_hestia_witness_fn(plugin_id, endpoint) if mcp_factory is None else None)
        self._c = None
        self._session_id: Optional[str] = None

    # -- the Dispatcher contract ---------------------------------------------
    def __call__(self, intent: BeingIntent, verdict: GatewayVerdict) -> ResultEnvelope:
        handler = getattr(self, f"_do_{intent.effector}", None)
        if handler is None:
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

    # A lost session arrives in TWO shapes and only one of them was handled.
    _SESSION_LOST = ("session not found", "session_not_found", "session expired", "no session")

    @classmethod
    def _is_session_loss(cls, text: str) -> bool:
        t = (text or "").lower()
        return any(m in t for m in cls._SESSION_LOST)

    def _call(self, name: str, args: dict) -> dict:
        """One hestia call, with a single reconnect if the session went away underneath it.

        A LOST SESSION ARRIVES IN TWO SHAPES. The daemon can answer with an error envelope
        (`_hestia_error.code` naming session), or the MCP transport can fail the request
        outright — `HTTP 404 ... Not Found: Session not found` — which `call` RAISES. The
        original reconnect only inspected the returned envelope, so for the raising path the
        retry existed and was dead code.

        Measured 2026-09-07, and it cost the being a milestone. Seven minutes into a beat it
        called `check` twice; the gate ALLOWED both, and both died on hestia_begin_action
        with that 404 before pytest ever ran. From inside, an expired transport is
        indistinguishable from a refusal — which is the opaque-404 defect the being itself
        reported as SAGE#52, landing on the first organ it was given.

        Both shapes now drop the client and reconnect once. A second failure is reported as
        it is: an expired session is a fact about the transport, never a verdict on the act,
        and the being must not be left to read one as the other."""
        sid = self._connect()
        try:
            out = _unwrap(self._c.call(name, {**args, "session_id": sid}))
        except Exception as e:
            if not self._is_session_loss(f"{type(e).__name__}: {e}"):
                raise
            self._c, self._session_id = None, None
            sid = self._connect()
            return _unwrap(self._c.call(name, {**args, "session_id": sid}))
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

    # -- mesh: THE primitive -------------------------------------------------
    def _do_mesh(self, intent: BeingIntent) -> ResultEnvelope:
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
        pointer = self._publish(to, body)
        if not pointer:
            return ResultEnvelope(ok=False, error="peer_ask: publisher returned no pointer")
        env = self._do_mesh(BeingIntent("mesh", {"to": to, "kind": "coordination", "pointer": pointer}))
        if env.ok and isinstance(env.result, dict):
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
    # MEMBOT REPORTS ITS FAILURES AS ORDINARY TEXT, and that cost the being its memory.
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
    # REQUIRE SUCCESS, DO NOT ENUMERATE FAILURE. The first cut listed the refusals it knew
    # about — and yesterday I wrote the lesson for the fleet in those words ("a guard
    # written against an enumerated list of failures treats every unenumerated failure as a
    # pass") and then built this as an enumerated list anyway. The one it did not know:
    # membot rate-limits at 60 requests/60s and says "Rate limited." as ordinary text, so a
    # rate-limited MOUNT read as success and the next recall reported no cartridge. The
    # being hit exactly that on 2026-09-11 and reported it rather than inferring its memory
    # was gone. A successful mount says "Mounted '<name>': N memories, ..."; nothing else
    # counts, whatever it says.
    _MOUNT_OK = "Mounted"
    _MOUNT_REFUSED = ("SECURITY:", "Refusing to mount", "failed integrity check",
                      "not found. Available:", "Cartridge too large", "Failed to fetch",
                      "must be a UUID", "Rate limited")
    _STORE_CONFIRMED = ("Stored memory #", "Duplicate — already stored")
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
            if self._MOUNT_OK not in reply or any(m in reply for m in self._MOUNT_REFUSED):
                # do NOT cache the session: the next act re-mounts rather than inheriting
                # a cartridge-less session that would report success while storing nothing
                raise RuntimeError(f"membot refused to mount {self.membot_cartridge!r}: {reply[:200]}")
            self._mb = c
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

    def _membot_call(self, name: str, args: dict, _remounted: bool = False) -> str:
        """One membot tool call, unwrapped to its text. RAISES on a JSON-RPC `error` or a
        tool-level `isError` result: both handlers turn the exception into ok=False, so a
        membot that says "Error calling tool save_cartridge" is never witnessed as a
        memory the being kept (Sprout's review of #36, reproduced against a fake membot).

        A LAPSED MOUNT IS RECOVERED HERE, ONCE. The mount is per MCP session and was
        checked only when the session was CREATED, then cached — so a session the server
        later forgot kept answering "No cartridge mounted" forever while `_membot()`
        happily returned it. Measured 2026-09-13: legion-being lost `remember` for two
        consecutive beats and reasoned, correctly, that it was "a stable state of this
        machine". The cartridge was fine the whole time (332 memories, integrity verified);
        only the session was gone. This is the same shape as SAGE#52, which the being
        itself diagnosed: a recovery that exists, is correct, and is dead code for the
        commoner form of the failure it was written for.

        Dropping `_mb` forces `_membot()` to re-mount AND re-check, so a genuinely refused
        mount still raises rather than being retried into a cartridge-less session. The
        retry cannot manufacture a false success: `_do_remember` still requires a confirmed
        store before it will save, so a second failure ends as a refusal with the file on
        disk untouched."""
        try:
            text = self._unwrap(self._membot().call(name, args), name)
        except RuntimeError as e:
            # A DEAD SESSION IS A HARD FAILURE, NOT A SOFT ONE, and the remount below only
            # covered the soft shape. When the membot process RESTARTS, the cached session
            # is gone and the server answers HTTP 404 "Session not found" as a JSON-RPC
            # error — which `_unwrap` raises, so it never reaches the text check. Measured
            # 2026-09-14: the seat restarted membot mid-beat and the being lost that beat's
            # `remember` to exactly this, while the cartridge was intact (344 memories).
            #
            # This is the SAGE#52 shape a second time, in code written to fix the first: a
            # recovery that exists, is correct, and is dead for the commoner form of its own
            # failure. One retry on a fresh session; a second failure is reported as-is.
            if _remounted or not _session_lost(e):
                raise
            self._mb = None
            return self._membot_call(name, args, _remounted=True)
        if self._NOT_MOUNTED in text and not _remounted:
            self._mb = None
            return self._membot_call(name, args, _remounted=True)
        return text

    def _do_recall(self, intent: BeingIntent) -> ResultEnvelope:
        q = str(intent.args.get("query", "")).strip()
        if not q:
            return ResultEnvelope(ok=False, error="recall needs a 'query'")
        try:
            k = int(intent.args.get("top_k") or 5)
        except (TypeError, ValueError):
            k = 5
        try:
            text = self._membot_call("memory_search", {"query": q, "top_k": max(1, min(k, 20))})
        except Exception as e:
            return ResultEnvelope(ok=False, error=f"membot ({type(e).__name__}): {e}")
        if self._NOT_MOUNTED in text:
            # "no cartridge" is not "nothing remembered": a silent empty answer here would
            # teach the being its past is gone when the store is merely unreachable.
            return ResultEnvelope(ok=False,
                                  error=f"membot has no cartridge mounted for {self.membot_cartridge!r}; "
                                        f"your memory was NOT searched: {text[:160]}")
        return ResultEnvelope(ok=True, result=text,
                              witness_id=self._local._witness(f"recall {q[:80]}"))

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
        try:
            saved = self._membot_call("save_cartridge", {"name": self.membot_cartridge})
        except Exception as e:
            return ResultEnvelope(ok=False, error=f"membot ({type(e).__name__}): {e}")
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
        # A GRANT ON A PATH THAT DOES NOT EXIST REACHES NOTHING, and nobody finds out.
        #
        # Measured 2026-09-14, twelve hours after the fact. legion-being could not tell where
        # its own worktree was, because the escape refusals did not say (fixed for search and
        # git_read in SAGE#90, still not for memory_read, which is how it happened). It
        # guessed `/home/dp/ai-worktrees/legion-being/sage/gateway`, asked for scope on the
        # guess, and the operator granted it verbatim at 00:34Z. The grant is live in the
        # being's scope list right now and points at a directory that has never existed. The
        # being still cannot read the harness it actually wanted, still says "that is your
        # claim, not mine" about every fix, and had no way to see why.
        #
        # So: refuse before filing, and name the deepest ancestor that DOES exist, which is
        # the fastest route from a wrong guess to a right one. The cost of refusing a real
        # request is one more beat; the cost of filing a phantom one is an operator decision
        # spent, a dead grant that looks like reach, and a being that cannot tell.
        if not _os.path.exists(rp):
            probe = rp
            while probe != "/" and not _os.path.exists(probe):
                probe = _os.path.dirname(probe)
            return ResultEnvelope(ok=False, error=(
                f"request_scope refused: {path!r} does not exist, so a grant on it would "
                f"reach nothing and you would not be able to tell. The deepest part of that "
                f"path that DOES exist is {probe!r}. Check the spelling against a path you "
                f"have actually reached — a `search` or `check` refusal names your worktree "
                f"root — and ask again for a path that is there. Nothing was filed, so no "
                f"operator attention was spent on it."))
        for root in (getattr(getattr(self, "_verdict", None), "granted", ()) or ()):
            r = _os.path.realpath(str(root))
            if rp == r or rp.startswith(r + "/"):
                # "You already hold reach here; read or write it directly" was TRUE at the
                # gate and FALSE in practice for every path outside the being's home: the
                # harness confines writes regardless of any grant, because write + execute
                # compose into arbitrary code as the seat (reference_f1a._safe_path). On
                # 2026-09-13 legion-being asked for the fleet forum to answer a peer, was
                # told already_granted, and was then refused the write — it had to read the
                # harness source to find out which of the two answers was real. A grant
                # that is live at one layer and inert at the next must SAY so.
                return ResultEnvelope(ok=True, result={
                    "status": "already_granted", "path": path, "within": r,
                    "writable": self._writable_by_harness(rp),
                    "next": ("you already hold reach here; read or write it directly"
                             if self._writable_by_harness(rp) else
                             "you already hold READ reach here. Writes are a separate "
                             "boundary and this path is outside it: the harness confines "
                             "every write to your own home and worktree whatever the gate "
                             "grants, because a tree you can write and `check` can execute "
                             "is arbitrary code running as the seat. To put something in a "
                             "shared place, use the verb built for it — `peer_ask` and "
                             "`mesh` file to the forum on your behalf — or appeal for the "
                             "affordance, naming what you would write")})
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

    def _writable_by_harness(self, real_path: str) -> bool:
        """Would a `memory_write` to this path survive the harness's own confinement?

        Deliberately asks the SAME question `_safe_path(writing=True)` answers, rather than
        re-deriving the rule: two copies of a security boundary drift, and the copy that
        drifts is always the one in the friendly message."""
        try:
            f1a = getattr(self, "_local", None)
            if f1a is None or not hasattr(f1a, "_safe_path"):
                return True          # cannot tell: do not manufacture a refusal
            f1a._safe_path(real_path, writing=True)
            return True
        except ValueError:
            return False
        except Exception:
            return True              # an unexpected failure is not evidence of a boundary

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
        try:
            proc = subprocess.run(shlex.split(cmd), cwd=self.worktree, text=True,
                                  capture_output=True, timeout=60)
        except Exception as e:
            return ResultEnvelope(ok=False, error=f"search could not run: {type(e).__name__}: {e}")
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
            # "NOT IN THAT FILE" AND "NO SUCH FILE" ARE THE SAME EXIT CODE (SAGE#89). git
            # grep returns 1 for both, so a search whose pathspec matched nothing came back
            # as a confident bounded absence about a file that does not exist. Measured on
            # this being's own todo.md, which lives in its INSTANCE home and not in the
            # worktree search runs inside. ls-files answers over the same universe git grep
            # searches (tracked files), using the pathspec the law actually judged.
            missing = None
            if intent.args.get("path"):
                argv_probe = shlex.split(cmd)
                spec = argv_probe[argv_probe.index("--") + 1] if "--" in argv_probe else None
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
                return ResultEnvelope(ok=False, error=(
                    f"search found no file at {where} in your worktree, so this is NOT an "
                    f"absence of {pattern!r} — nothing was searched. `search` runs inside "
                    f"your WORKTREE and sees only files git tracks there. A relative path "
                    f"here is not the same path `memory_read` takes: memory_read resolves "
                    f"relative paths inside your instance home, and files that live only "
                    f"there (todo.md, journal.md, notes/, scratch/) cannot be searched at "
                    f"all. Read those with memory_read; search the source tree."))
            return ResultEnvelope(ok=True, result={
                "pattern": pattern, "searched": where, "matches": 0,
                "searched_a_real_file": True,
                "note": (f"no line matches {pattern!r} in {where}. The path exists and was "
                         f"searched, so this is a real absence — but an answer about WHAT "
                         f"WAS SEARCHED, not about the repository: widen the path, or "
                         f"check the pattern (it is an extended regex, so ( ) | + are "
                         f"special — searching for a literal one needs a backslash)")})
        return ResultEnvelope(ok=True, result={
            "pattern": pattern, "searched": where, "matches": len(lines),
            "shown": len(shown),
            "truncated": (f"{len(lines) - len(shown)} further matches not shown; narrow the "
                          f"path or the pattern" if truncated else None),
            "lines": shown})

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
        captured = proc.returncode == 0 and os.path.exists(full_out)
        try:
            self._call("hestia_record_outcome",
                       {"action_id": action_id, "success": captured, "magnitude": 0.0})
        except Exception:
            pass
        if captured:
            return ResultEnvelope(ok=True, witness_id=action_id, result={
                "device": device, "out_path": out_rel,
                "bytes": os.path.getsize(full_out),
                "note": ("one frame captured. It is a JPEG, so memory_read will hand you "
                         "binary, not a picture — it returns ok and you learn nothing. "
                         "Seeing it needs a vision-capable reader, which is not wired yet. "
                         "Nothing persists across beats.")})
        if proc.returncode != 0:
            # THREE CAUSES, not two. "the node exists, therefore the device is busy" was a
            # false dichotomy: it also fires when the device is fine and the OUTPUT is the
            # problem. ffmpeg says which on stderr, so read it rather than inferring.
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
                "note": (f"ffmpeg exited {proc.returncode} and no frame was written — "
                         f"{kind}. The previous file at the path, if any, is untouched. "
                         f"`stderr` above is ffmpeg's own account; the kind is my reading "
                         f"of it.")})
        return ResultEnvelope(ok=False, witness_id=action_id, result={
            "device": device, "out_path": out_rel,
            "note": ("ffmpeg exited 0 but wrote no readable frame — capture anomaly; do "
                     "not treat a missing file as a captured one")})

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
        stable = (tree_after.get("head") == tree_before.get("head")
                  and source_after == source_before)
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
                                          "state": "pinned" if stable else "tree_changed_during_check",
                                      },
                                      "action_id": action_id})

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
            paths = sorted(p for p in root.rglob("test_*.py")) if root.is_dir() else (
                [root] if root.exists() else [])
            h = hashlib.sha256()
            for p in paths:
                h.update(p.relative_to(self.worktree).as_posix().encode())
                h.update(p.read_bytes())
            return {"root": rel, "files": len(paths), "sha256": h.hexdigest(),
                    "at_head": head}
        except Exception:
            return None

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

    def _do_say(self, intent: BeingIntent) -> ResultEnvelope:
        """Add a turn to a conversation the being is in.

        The being names a conversation id and text. Everything that decides whether it MAY
        speak lives in the conversation's meta file, which the seat owns and the being
        cannot write — so this reach is fixed by construction rather than by the argument,
        the same property that makes `remember` safe with path_args=().

        Refusals here are ordinary and informative: 'you are not in that conversation' and
        'you may read that one but not speak in it' are different sentences, and the being
        should never have to guess which it hit."""
        from sage.gateway import conversations as conv
        to = str(intent.args.get("to", "")).strip()
        text = str(intent.args.get("text", "")).strip()
        if not to or not text:
            return ResultEnvelope(ok=False, error="say needs 'to' (a conversation id) and 'text'")
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
        return ResultEnvelope(ok=True, witness_id=action_id,
                              result={"conversation": to, "seq": turn["seq"],
                                      "said": turn["text"][:200], "action_id": action_id})

    def _do_pr_open(self, intent: BeingIntent) -> ResultEnvelope:
        """The being's worktree changes become a pull request, attributed to it.

        Order: begin_action -> branch -> add -> commit (message over stdin, trailers the
        being cannot alter) -> push -> `gh pr create` (the command the gate judged) ->
        record_outcome. Every failure short of the push leaves the worktree on its new
        branch with the commit intact, so nothing the being wrote is lost by a failed act.

        The seat's git identity authors the commit; the trailers attribute it (PRD r3 §7.2).
        That is the legibility form — §6 says a being-signed tree hash comes at M3 — and the
        PR body says so rather than letting a trailer pass for a signature."""
        import shlex
        import subprocess
        from sage.gateway.being_gate_client import pr_open_command, pr_attribution
        if not self.worktree or not os.path.isdir(self.worktree):
            return ResultEnvelope(ok=False, pending=True,
                                  note="pr_open needs a worktree of your own; none is configured")
        try:
            cmd = pr_open_command(intent.args, {"worktree": self.worktree})
        except ValueError as e:
            return ResultEnvelope(ok=False, error=str(e))
        slug = str(intent.args["slug"]).strip()
        title = " ".join(str(intent.args["title"]).split())
        body = str(intent.args["body"]).rstrip()
        branch = f"legion-being/{slug}"

        def git(*a, inp=None):
            return subprocess.run(["git", *a], cwd=self.worktree, text=True, input=inp,
                                  capture_output=True, timeout=120)

        # nothing to propose is a refusal with a reason, not an empty PR
        st = git("status", "--porcelain")
        if st.returncode != 0:
            return ResultEnvelope(ok=False, error=f"git status failed: {st.stderr[:200]}")
        if not st.stdout.strip():
            return ResultEnvelope(ok=False, error="pr_open: your worktree has no changes to "
                                                  "propose. Write the change first, then open the PR")
        if git("rev-parse", "--verify", "--quiet", branch).returncode == 0:
            return ResultEnvelope(ok=False, error=f"pr_open: branch {branch} already exists; "
                                                  "pick another slug")

        begin = self._call("hestia_begin_action", {"tool_name": "pr_open", "target": branch})
        err = _hestia_error(begin)
        if err:
            return ResultEnvelope(ok=False, error=err)
        action_id = begin.get("actionId")

        steps = []
        def fail(stage, proc):
            detail = (proc.stderr or proc.stdout or "").strip()[:400]
            try:
                self._call("hestia_record_outcome", {"action_id": action_id, "success": False,
                                                     "magnitude": 0.0, "error": f"{stage}: {detail[:200]}"})
            except Exception:
                pass
            return ResultEnvelope(ok=False, witness_id=action_id,
                                  error=f"pr_open failed at {stage}: {detail}",
                                  result={"steps": steps, "branch": branch})

        r = git("checkout", "-b", branch)
        if r.returncode != 0:
            return fail("branch", r)
        steps.append(f"branch {branch}")
        r = git("add", "-A")
        if r.returncode != 0:
            return fail("add", r)
        steps.append("add")
        trailers = pr_attribution(self.plugin_id, action_id, self.being_lct)
        message = f"{title}\n\n{body}\n\n{trailers}\n"
        r = git("commit", "-q", "-F", "-", inp=message)
        if r.returncode != 0:
            return fail("commit", r)
        sha = git("rev-parse", "--short=9", "HEAD").stdout.strip()
        steps.append(f"commit {sha}")
        r = git("push", "-q", "-u", "origin", branch)
        if r.returncode != 0:
            return fail("push", r)
        steps.append("push")

        pr_body = (body + "\n\n---\n"
                   f"Authored by **{self.plugin_id}**, a SAGE being, from its own worktree; "
                   f"the seat composed the outward act. Commit `{sha}` carries `Being` / "
                   f"`Being-LCT` / `Witness` / `Seat` trailers — attribution, not yet a "
                   f"signature (PRD r3 §6). The being cannot merge this; a NOT-SAME reviewer "
                   f"decides.\n"
                   + (f"LCT: `{self.being_lct}`\n" if self.being_lct else "")
                   + f"hestia witness action: `{action_id}`\n")
        try:
            proc = subprocess.run(shlex.split(cmd), input=pr_body, text=True,
                                  cwd=self.worktree, capture_output=True, timeout=120)
        except Exception as e:
            proc = subprocess.CompletedProcess(cmd, 1, "", f"{type(e).__name__}: {e}")
        if proc.returncode != 0:
            return fail("gh pr create", proc)
        url = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
        steps.append("pr")
        try:
            self._call("hestia_record_outcome", {"action_id": action_id, "success": True, "magnitude": 0.0})
        except Exception:
            pass
        # THE REVIEW TRIGGER. dp, 2026-09-09: "we don't want being's prs sitting unreviewed."
        # A being's PR is opened by a governed act that no human watched, so nothing else
        # would announce it. The queue file is the durable half of the trigger — a seat is a
        # session and may not be running — and the sweep timer reads it. Failure to queue
        # never fails the PR: the PR is real either way, and a lost queue entry is caught by
        # the sweep, which lists open PRs directly.
        queued = None
        try:
            queued = _queue_for_review(self.memory_root, member=self.member, url=url,
                                       branch=branch, commit=sha, action_id=action_id)
        except Exception as e:
            queued = f"not queued ({type(e).__name__}: {e}) — the sweep will still find it"
        return ResultEnvelope(ok=True, witness_id=action_id,
                              result={"pr": url, "branch": branch, "commit": sha,
                                      "steps": steps, "action_id": action_id,
                                      "review_queued": queued,
                                      "note": "your worktree is now on this branch; a reviewer "
                                              "who is not you decides. You cannot merge it."})

    def _do_git_restore(self, intent: BeingIntent) -> ResultEnvelope:
        """Put one file back to a committed state. Same composed shape as check/git_read:
        the being names a rev and a path, the SEAT builds the command, the law judges that
        string, and the being never holds a flag.

        The result reports the file's size before and after, because "it worked" and "it
        changed nothing" are different answers and only one of them is progress."""
        import shlex
        import subprocess
        from sage.gateway.being_gate_client import git_restore_command
        if not self.worktree or not os.path.isdir(self.worktree):
            return ResultEnvelope(ok=False, pending=True,
                                  note="git_restore needs a worktree of your own; none is configured")
        try:
            cmd = git_restore_command(intent.args, {"worktree": self.worktree})
        except ValueError as e:
            return ResultEnvelope(ok=False, error=str(e))
        target = os.path.realpath(os.path.join(self.worktree, str(intent.args["path"])))
        before = os.path.getsize(target) if os.path.exists(target) else 0
        try:
            proc = subprocess.run(shlex.split(cmd), cwd=self.worktree, text=True,
                                  capture_output=True, timeout=120)
        except Exception as e:
            return ResultEnvelope(ok=False, error=f"git_restore could not run: {type(e).__name__}: {e}")
        if proc.returncode != 0:
            return ResultEnvelope(ok=False,
                                  error=f"git_restore failed: {(proc.stderr or proc.stdout).strip()[:300]}")
        after = os.path.getsize(target) if os.path.exists(target) else 0
        rev = str(intent.args["rev"])
        return ResultEnvelope(
            ok=True,
            result=(f"RESTORED {os.path.basename(target)} to its content at {rev}. "
                    f"It was {before} bytes and is now {after} bytes. Any uncommitted edits you "
                    f"had made to this one file are gone; nothing else was touched."),
            witness_id=self._local._witness(f"git_restore {os.path.basename(target)} @ {rev}"))

    def _do_pr_amend(self, intent: BeingIntent) -> ResultEnvelope:
        """Revise a proposal already open: commit onto the same branch, push, optionally
        replace the PR body. Same witnessed shape as pr_open.

        WHY IT EXISTS: pr_open claims a slug once and refuses it thereafter, so a being whose
        PR got "changes requested" could not deliver them — measured on SAGE#63, where the
        review asked for a corrected body and a green suite and the author had no verb that
        could reach either. A review loop whose author cannot answer the review is not a loop.

        The being names neither branch nor PR number; both are read from the worktree, so this
        can only ever revise its own open proposal. It still cannot merge."""
        import shlex
        import subprocess
        from sage.gateway.being_gate_client import pr_amend_command, pr_attribution
        if not self.worktree or not os.path.isdir(self.worktree):
            return ResultEnvelope(ok=False, pending=True,
                                  note="pr_amend needs a worktree of your own; none is configured")
        try:
            cmd = pr_amend_command(intent.args, {"worktree": self.worktree})
        except ValueError as e:
            return ResultEnvelope(ok=False, error=str(e))
        title = " ".join(str(intent.args["title"]).split())
        message = str(intent.args["message"]).rstrip()
        new_body = str(intent.args.get("body", "") or "").rstrip()

        def git(*a, inp=None):
            return subprocess.run(["git", *a], cwd=self.worktree, text=True, input=inp,
                                  capture_output=True, timeout=120)

        branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        st = git("status", "--porcelain")
        if st.returncode != 0:
            return ResultEnvelope(ok=False, error=f"git status failed: {st.stderr[:200]}")
        if not st.stdout.strip() and not new_body:
            return ResultEnvelope(ok=False,
                                  error="pr_amend: nothing to revise — the worktree is clean and "
                                        "you supplied no new body. Change the code or the body first")

        begin = self._call("hestia_begin_action", {"tool_name": "pr_amend", "target": branch})
        err = _hestia_error(begin)
        if err:
            return ResultEnvelope(ok=False, error=err)
        action_id = begin.get("actionId")
        steps = []

        def fail(stage, proc):
            detail = (getattr(proc, "stderr", "") or getattr(proc, "stdout", "") or "").strip()[:400]
            try:
                self._call("hestia_record_outcome", {"action_id": action_id, "success": False,
                                                     "magnitude": 0.0, "error": f"{stage}: {detail[:200]}"})
            except Exception:
                pass
            return ResultEnvelope(ok=False, witness_id=action_id,
                                  error=f"pr_amend failed at {stage}: {detail}",
                                  result={"steps": steps, "branch": branch})

        sha = git("rev-parse", "--short=9", "HEAD").stdout.strip()
        if st.stdout.strip():
            r = git("add", "-A")
            if r.returncode != 0:
                return fail("add", r)
            steps.append("add")
            trailers = pr_attribution(self.plugin_id, action_id, self.being_lct)
            r = git("commit", "-q", "-F", "-", inp=f"{title}\n\n{message}\n\n{trailers}\n")
            if r.returncode != 0:
                return fail("commit", r)
            sha = git("rev-parse", "--short=9", "HEAD").stdout.strip()
            steps.append(f"commit {sha}")
            r = git("push", "-q", "origin", branch)
            if r.returncode != 0:
                return fail("push", r)
            steps.append("push")

        edited = False
        if new_body:
            body_out = (new_body + "\n\n---\n"
                        f"Revised by **{self.plugin_id}** via pr_amend; commit `{sha}` carries the "
                        f"`Being` / `Being-LCT` / `Witness` / `Seat` trailers. Still attribution "
                        f"rather than a signature (PRD r3 §6), and the being still cannot merge.\n"
                        f"hestia witness action: `{action_id}`\n")
            try:
                proc = subprocess.run(shlex.split(cmd), input=body_out, text=True,
                                      cwd=self.worktree, capture_output=True, timeout=120)
            except Exception as e:
                proc = subprocess.CompletedProcess(cmd, 1, "", f"{type(e).__name__}: {e}")
            if proc.returncode != 0:
                return fail("gh pr edit", proc)
            steps.append("body")
            edited = True
        try:
            self._call("hestia_record_outcome", {"action_id": action_id, "success": True, "magnitude": 0.0})
        except Exception:
            pass
        return ResultEnvelope(ok=True, witness_id=action_id,
                              result={"branch": branch, "commit": sha, "body_replaced": edited,
                                      "steps": steps, "action_id": action_id,
                                      "note": "the reviewer sees the revision; they decide. "
                                              "You still cannot merge it."})

    # -- channel_egress: not built on the daemon ----------------------------
    def _do_channel_egress(self, intent: BeingIntent) -> ResultEnvelope:
        return ResultEnvelope(ok=False, pending=True,
                              note="channel_egress awaits hestia's send-side tool (hestia_egress_pending is "
                                   "read-only; F5 enforcement gated on rate-governor calibration, PRD §12)")


REVIEW_QUEUE = "review_queue.jsonl"


def _queue_for_review(memory_root, *, member: str, url: str, branch: str,
                      commit: str, action_id) -> str:
    """Record that a being opened a PR and it is waiting on a reviewer.

    Append-only beside the being's own records, because that is what survives a seat
    session ending. The sweep (scripts/being_pr_sweep.sh) reads GitHub directly and does
    not depend on this file — the queue exists so the wait is visible from the being's own
    directory too, and so a review can be tied back to the witnessed act that opened it."""
    import json as _json
    from datetime import datetime, timezone
    from pathlib import Path as _P
    q = _P(memory_root) / REVIEW_QUEUE
    row = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "member": member, "pr": url, "branch": branch, "commit": commit,
           "action_id": action_id, "state": "awaiting_review"}
    with open(q, "a", encoding="utf-8") as f:
        f.write(_json.dumps(row) + "\n")
    return f"queued in {q.name} at {row['ts']}"


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
    git("fetch", "-q", remote)
    git("rebase", "-q", upstream)                # no autostash: a dirty sibling tree fails loud, not silently stashed
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
