"""Hermetic tests for the egress drain worker: fake MCP scripts the daemon, fake sender stands in for hub-notify."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.egress_drain import drain_once  # noqa: E402

def _sc(d): return {"result": {"structuredContent": d}}

class FakeMcp:
    def __init__(self, pending=None, egress_error=None):
        self.calls = []; self.pending = pending or []; self.egress_error = egress_error
    def init(self): pass
    def call(self, name, args):
        self.calls.append((name, dict(args)))
        if name == "hestia_connect": return _sc({"sessionId": "s-9"})
        if name == "hestia_egress_pending":
            if self.egress_error: return _sc({"_hestia_error": self.egress_error})
            if "mark_forwarded" in args or "mark_failed" in args: return _sc({"ok": True})
            return _sc({"pending": self.pending, "total": len(self.pending), "drain_contract": {}})
        return _sc({})

ROW = {"id": 7, "forward_on": "61525719-def6-475c-a030-917f24a9dbf2", "forward_on_is_lct": True,
       "kind": "coordination", "pointer_uri": "shared-context/forum/x.md", "attempts": 0}

def test_forwards_and_marks_forwarded():
    m = FakeMcp(pending=[ROW]); sent = []
    r = drain_once(mcp=m, sender=lambda to, kind, ptr: (sent.append((to, kind, ptr)) or (True, "ledger=77")), log=lambda *_: None)
    assert r["forwarded"] == 1 and r["failed"] == 0 and not r["empty"]
    assert sent == [("61525719-def6-475c-a030-917f24a9dbf2", "coordination", "shared-context/forum/x.md")]
    marks = [a for n, a in m.calls if n == "hestia_egress_pending" and "mark_forwarded" in a]
    assert marks and marks[0]["mark_forwarded"] == 7 and isinstance(marks[0]["mark_forwarded"], int) and marks[0]["session_id"] == "s-9"

def test_sender_failure_marks_failed_with_reason():
    m = FakeMcp(pending=[ROW])
    r = drain_once(mcp=m, sender=lambda to, kind, ptr: (False, "hub refused: kind gate"), log=lambda *_: None)
    assert r["failed"] == 1 and r["forwarded"] == 0
    marks = [a for n, a in m.calls if n == "hestia_egress_pending" and "mark_failed" in a]
    assert marks and marks[0]["mark_failed"] == 7 and "kind gate" in marks[0]["reason"]

def test_empty_queue_is_empty_not_error():
    r = drain_once(mcp=FakeMcp(pending=[]), sender=lambda *a: (True, ""), log=lambda *_: None)
    assert r["empty"] and r["error"] is None and r["forwarded"] == 0

def test_refused_call_is_error_never_silence():
    r = drain_once(mcp=FakeMcp(egress_error={"code": "hestia.egress_unattributed", "message": "x"}),
                   sender=lambda *a: (True, ""), log=lambda *_: None)
    assert r["error"] and r["error"]["code"] == "hestia.egress_unattributed" and not r["empty"]

def test_being_rows_sign_as_the_being_when_it_holds_a_hub_identity(monkeypatch=None):
    import os, tempfile
    from sage.gateway import egress_drain as ed
    home = tempfile.mkdtemp(prefix="hubenv-")
    old = os.environ.get("HOME"); os.environ["HOME"] = home
    try:
        assert ed.hub_env_for("sprout-being") == (None, "seat")
        os.makedirs(os.path.join(home, ".config"), exist_ok=True)
        p = os.path.join(home, ".config", "hub-mesh-sprout-being.env"); open(p, "w").write("MY_LCT=x\n")
        assert ed.hub_env_for("sprout-being") == (p, "being")
        assert ed.hub_env_for("legion-being") == (None, "seat")
    finally:
        if old is not None: os.environ["HOME"] = old


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


def test_the_drain_reports_who_actually_signed(monkeypatch):
    """hestia #1030: a being's mesh act leaves the host under the SEAT's hub identity and
    nothing records the carrier. Replies follow the signer, land in the seat's mailbox, and
    the being concludes nobody answered — cbp-being asked 92 times in 30 hours into that.

    On this host it was worse than unrecorded: the label existed and heartbeat.py passed
    `log=lambda *_: None`, so it was built, formatted and thrown away. The beat record said
    {"forwarded": 1} and nothing about who it was forwarded AS. A log line is not a record.
    """
    from sage.gateway import egress_drain as E

    # no hub identity for this member -> the seat signs, which is today's silent default
    monkeypatch.setattr(E, "hub_env_for", lambda pid: (None, "seat"))
    m = FakeMcp(pending=[ROW])
    r = drain_once(mcp=m, plugin_id="legion-being", log=lambda *_: None,
                   sender=lambda to, kind, ptr: (True, "ledger=77"))
    assert r["forwarded"] == 1
    assert r["signed_as"] == "seat", r
    assert "carrier_gap" in r, "a seat-signed being row must say so in the record"
    assert "legion-being" in r["carrier_gap"] and "#1030" in r["carrier_gap"]

    # with the being's own hub identity present there is no gap to report
    monkeypatch.setattr(E, "hub_env_for", lambda pid: ("/x/being-hub-identity", "being"))
    r2 = drain_once(mcp=FakeMcp(pending=[ROW]), plugin_id="legion-being", log=lambda *_: None,
                    sender=lambda to, kind, ptr: (True, "ledger=77"))
    assert r2["signed_as"] == "being", r2
    assert "carrier_gap" not in r2, "no gap, no warning — this must not cry wolf"

    # and nothing forwarded is not a carrier complaint either
    r3 = drain_once(mcp=FakeMcp(pending=[]), plugin_id="legion-being", log=lambda *_: None,
                    sender=lambda to, kind, ptr: (True, "ledger=77"))
    assert "carrier_gap" not in r3 and r3["empty"] is True
