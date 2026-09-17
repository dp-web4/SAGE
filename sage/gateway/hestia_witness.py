"""
Real hestia witness for the reference F1a dispatcher's witness_fn.

Emits a witnessed action to the local hestia daemon over MCP — the begin_action ->
record_outcome pair the claude-code witness hook uses — and returns the daemon's
actionId as the witness id.

FAIL-SAFE by contract: any error, refusal, or unreachable daemon returns None, so the
caller (ReferenceF1aDispatcher) falls back to its local witness_log.jsonl. Witnessing
must never break the being's turn, and a witness must never be silently dropped — worst
case it lands in the local log instead of the chain.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Optional

_ENDPOINT = "http://127.0.0.1:7711/mcp"
_PROTOCOL = "2024-11-05"
_TIMEOUT = 4.0


def _parse(text: str) -> dict:
    """Hestia returns plain JSON-RPC or an SSE stream carrying it — handle both."""
    text = text.strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("data:"):
            body = line[5:].strip()
            if body.startswith("{"):
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    continue
    return {}


def _unwrap(resp: dict) -> dict:
    result = resp.get("result") or {}
    sc = result.get("structuredContent")
    if isinstance(sc, dict):
        return sc
    for blk in result.get("content") or []:
        if isinstance(blk, dict) and blk.get("type") == "text":
            try:
                return json.loads(blk.get("text", ""))
            except json.JSONDecodeError:
                pass
    return {}


class _Mcp:
    def __init__(self, endpoint: str, plugin_id: str):
        self.endpoint = endpoint
        self.plugin_id = plugin_id
        self.sid: Optional[str] = None
        self._n = 0

    def _id(self) -> int:
        self._n += 1
        return self._n

    def _req(self, body: dict, notify: bool = False) -> Optional[dict]:
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.sid:
            headers["mcp-session-id"] = self.sid
        req = urllib.request.Request(self.endpoint, data=json.dumps(body).encode(),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                if not self.sid:
                    sid = r.headers.get("mcp-session-id")
                    if sid:
                        self.sid = sid
                if notify:
                    return None
                return _parse(r.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            # An HTTP failure here reached the being as a bare "HTTPError: HTTP Error 404:
            # Not Found" with no URL, no method and no tool — so four peer_ask refusals on
            # 2026-09-06 22:50-22:58Z could not be attributed to any endpoint, and the same
            # call succeeded from a fresh process minutes later. Name what was called, or
            # the next occurrence is equally unfindable.
            method = body.get("method", "?")
            tool = (body.get("params") or {}).get("name")
            where = f"{method}{f' {tool}' if tool else ''}"
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            raise RuntimeError(
                f"MCP {where} -> HTTP {e.code} at {self.endpoint} (as {self.plugin_id})"
                + (f": {detail}" if detail else "")
            ) from e
        except urllib.error.URLError as e:
            method = body.get("method", "?")
            tool = (body.get("params") or {}).get("name")
            where = f"{method}{f' {tool}' if tool else ''}"
            raise RuntimeError(
                f"MCP {where} -> unreachable at {self.endpoint} (as {self.plugin_id}): {e.reason}"
            ) from e

    def init(self) -> None:
        self._req({"jsonrpc": "2.0", "id": self._id(), "method": "initialize",
                   "params": {"protocolVersion": _PROTOCOL, "capabilities": {},
                              "clientInfo": {"name": self.plugin_id, "version": "1"}}})
        self._req({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                  notify=True)

    def call(self, name: str, args: dict) -> dict:
        return self._req({"jsonrpc": "2.0", "id": self._id(), "method": "tools/call",
                          "params": {"name": name, "arguments": args}}) or {}

    def read_resource(self, uri: str) -> dict:
        """Dereference a `hestia://` resource (MCP `resources/read`).

        Tools are not the only surface: escalations, chain entries and adjudications are
        addressed as RESOURCES, and a client with only `call` cannot open the pointer a
        notice hands it. Measured 2026-09-17: every `hestia://escalation/<id>` invitation
        cbp-being received fell through to a file read and answered "no such path", and the
        being concluded the seat had fabricated them (SAGE #109)."""
        return self._req({"jsonrpc": "2.0", "id": self._id(), "method": "resources/read",
                          "params": {"uri": uri}}) or {}


def make_hestia_witness_fn(plugin_id: str, endpoint: str = _ENDPOINT,
                           host_agent: str = "sage-raising") -> Callable[[str], Optional[str]]:
    """Return a witness_fn(event) -> actionId|None that records via the real daemon.

    plugin_id is the member the act is attributed to (e.g. 'sprout-being'). If the
    daemon does not recognise it or refuses, we return None and the caller witnesses
    locally instead — the being is never blocked, and the record is never lost.
    """
    def witness_fn(event: str) -> Optional[str]:
        try:
            c = _Mcp(endpoint, plugin_id)
            c.init()
            # Attribute the act to a LIVE session (Legion 2026-09-02: "the sender is the live
            # session_id from hestia_connect — attribution is proven, not inherited"). Without
            # this, the 2026-09-01 build recorded the being's witnesses under a synthetic
            # member "anonymous" (chain #3905/#3906) — the "anonymous agent" dp found in the
            # registry. A failed connect is a failed witness here (None -> local log), never
            # an unattributed one.
            conn = _unwrap(c.call("hestia_connect", {
                "plugin_id": plugin_id, "host_agent": host_agent,
                "host_agent_version": "sage", "requested_role": "citizen"}))
            session_id = conn.get("sessionId") or conn.get("session_id")
            if "_hestia_error" in conn or not session_id:
                return None
            begin = _unwrap(c.call("hestia_begin_action",
                                   {"tool_name": "witness", "target": (event or "")[:200],
                                    "session_id": session_id}))
            if "_hestia_error" in begin:
                return None
            action_id = begin.get("actionId")
            if not action_id:
                return None
            # Best-effort completion; the act is already recorded by begin_action, so we
            # return the id even if record_outcome hiccups.
            try:
                c.call("hestia_record_outcome",
                       {"action_id": action_id, "success": True, "magnitude": 0.0,
                        "session_id": session_id})
            except Exception:
                pass
            return action_id
        except Exception:
            return None
    return witness_fn
