"""A filed scope request tells the being how IT checks the ruling, and that check works.

cbp-being, 2026-10-23: hestia's receipt said "poll hestia_scope_status", a daemon tool the being
does not have. It spent the day searching for a `hestia_scope_status` file, writing scripts to
start hestia and poll it over HTTP from a sandbox with no network, and filing asks to reach the
places it searched (47 scope requests in 12 hours). The read it needed already existed:
memory_read of `hestia://scope/<id>`.
"""
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict  # noqa: E402
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher  # noqa: E402
from sage.gateway.tests.test_hestia_dispatch import FakeMcp, _WithScopeQueue  # noqa: E402

PENDING = "scope-0fefb5f67e46"     # pending in _WithScopeQueue's queue


class _FilesThePendingOne(_WithScopeQueue):
    def call(self, name, args):
        if name == "hestia_request_scope":
            FakeMcp.calls.append((name, args))
            return {"result": {"structuredContent": {
                "request_id": PENDING, "status": "pending", "witnessEntryHash": "rs",
                "next": "poll hestia_scope_status; a human decides this, out of band",
                "on_timeout": "REFUSED"}}}
        return super().call(name, args)


def _d():
    FakeMcp.calls, FakeMcp.fail = [], {}
    return HestiaF1aDispatcher("cbp-being", tempfile.mkdtemp(prefix="sn-"),
                               mcp_factory=lambda ep, pid: _FilesThePendingOne(ep, pid))


def test_the_receipt_names_the_beings_own_read_and_never_the_daemon_tool():
    d = _d()
    env = d(BeingIntent("request_scope", {"path": "/srv/elsewhere/x", "reason": "to read a peer's note"}),
            GatewayVerdict("allow", granted=()))
    assert env.ok and env.result["request_id"] == PENDING, env
    nxt = env.result["next"]
    assert "hestia_scope_status" not in nxt, nxt
    assert f'memory_read {{"path": "hestia://scope/{PENDING}"}}' in nxt, nxt
    assert "nothing needs starting" in nxt and "do not search" in nxt


def test_the_read_the_receipt_names_answers_with_the_requests_status():
    d = _d()
    env = d(BeingIntent("request_scope", {"path": "/srv/elsewhere/x", "reason": "to read a peer's note"}),
            GatewayVerdict("allow", granted=()))
    pointer = re.search(r'"path": "(hestia://scope/[^"]+)"', env.result["next"]).group(1)
    got = d(BeingIntent("memory_read", {"path": pointer}), GatewayVerdict("allow", granted=()))
    assert got.ok and f"your scope request {PENDING}" in got.result, got
    assert "status: pending" in got.result
