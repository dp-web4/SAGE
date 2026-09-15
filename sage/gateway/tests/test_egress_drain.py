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


def test_the_drain_summary_names_the_carrier_that_signed(monkeypatch=None):
    """hestia #1030: the chain says the being forwarded, the hub says the seat signed, and the
    carrier lived only in a detail string the summary discarded."""
    import os, tempfile
    from sage.gateway import egress_drain as ed
    home = tempfile.mkdtemp(prefix="carrier-"); old = os.environ.get("HOME")
    os.environ["HOME"] = home
    try:
        os.makedirs(os.path.join(home, ".config"))
        sent = []
        def fake_sender(to, kind, ptr):
            sent.append((to, kind, ptr)); return True, "ledger=1 ok"
        class Mcp:
            def init(self): pass
            def call(self, name, args):
                if name == "hestia_connect":
                    return {"result": {"structuredContent": {"sessionId": "s1"}}}
                if name == "hestia_egress_pending" and "mark_forwarded" not in args and "mark_failed" not in args:
                    return {"result": {"structuredContent": {"pending": [{"id": 1, "forward_on": "legion",
                                                                          "kind": "coordination", "pointer_uri": "p"}]}}}
                return {"result": {"structuredContent": {}}}
        out = ed.drain_once(plugin_id="sprout-being", mcp=Mcp(), sender=fake_sender, log=lambda *a: None)
        assert out["forwarded"] == 1 and out["signed_as"] == "seat" and out["carrier"] is None
        with open(os.path.join(home, ".config", "hub-mesh-sprout-being.env"), "w") as f:
            f.write('MY_LCT="2e175714-being"\nMY_KEYPAIR=/k\n')
        out = ed.drain_once(plugin_id="sprout-being", mcp=Mcp(), sender=fake_sender, log=lambda *a: None)
        assert out["signed_as"] == "being" and out["carrier"] == "2e175714-being"
    finally:
        if old is not None: os.environ["HOME"] = old


def _home_with(files):
    import tempfile
    home = tempfile.mkdtemp(prefix="stamp-")
    os.makedirs(os.path.join(home, ".config"))
    for name, lct in files.items():
        with open(os.path.join(home, ".config", name), "w") as f:
            f.write(f'MY_LCT="{lct}"\nMY_KEYPAIR=/k\n')
    return home


class _SwapHome:
    def __init__(self, home): self.home = home
    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in ("HOME", "HUB_MESH_ENV")}
        os.environ["HOME"] = self.home; os.environ.pop("HUB_MESH_ENV", None)
    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v


SEAT_ENV = "hub-mesh" + ".env"
BEING_ENV = "hub-mesh-cbp-being" + ".env"


def test_a_stamped_row_is_signed_by_its_carrier_and_the_mark_names_it():
    """hestia #1030: the drain consumes the stamp. The being's identity signs because the
    stamp names it, not because a file happens to exist, and the mark carries the carrier
    and the hub's ledger id."""
    home = _home_with({SEAT_ENV: "seat-lct", BEING_ENV: "being-lct"})
    row = dict(ROW, transport={"mode": "direct", "carrier_lct": "BEING-LCT", "version": 3})
    with _SwapHome(home):
        m = FakeMcp(pending=[row])
        r = drain_once(plugin_id="cbp-being", mcp=m,
                       sender=lambda to, kind, ptr: (True, "[hub-notify] -> legion kind=coordination ledger=1588 hash=h"),
                       log=lambda *_: None)
    assert r["forwarded"] == 1 and r["transport_faults"] == []
    mark = [a for n, a in m.calls if "mark_forwarded" in a][0]
    assert mark["carrier_lct"] == "being-lct" and mark["hub_receipt"] == {"ledger": "1588"}


def test_a_stamped_row_with_no_key_for_its_carrier_is_never_sent_under_another():
    """Falsifier 2 at the drain: the seat's key is RIGHT THERE and must not be used."""
    home = _home_with({SEAT_ENV: "seat-lct"})
    row = dict(ROW, transport={"mode": "direct", "carrier_lct": "being-lct", "version": 3})
    sent = []
    with _SwapHome(home):
        m = FakeMcp(pending=[row])
        r = drain_once(plugin_id="cbp-being", mcp=m,
                       sender=lambda to, kind, ptr: (sent.append(to) or (True, "ledger=1")), log=lambda *_: None)
    assert sent == [], "nothing may leave under the seat's key"
    assert r["failed"] == 1 and r["transport_faults"][0]["fault"] == "carrier-unavailable"
    fail = [a for n, a in m.calls if "mark_failed" in a][0]
    assert fail["fault"] == "carrier_unavailable" and "being-lct" in fail["reason"]


def test_a_relay_stamp_signs_with_the_seat_it_names():
    home = _home_with({SEAT_ENV: "seat-lct", BEING_ENV: "being-lct"})
    row = dict(ROW, transport={"mode": "relay", "carrier_lct": "seat-lct", "delegation_ref": "d1", "version": 4})
    with _SwapHome(home):
        from sage.gateway import egress_drain as ed
        env_file, label, carrier, refusal = ed.signer_for(row, "cbp-being")
    assert (label, carrier, refusal) == ("seat", "seat-lct", None) and env_file.endswith(SEAT_ENV)


def test_an_unbound_row_reports_the_carrier_it_chose():
    home = _home_with({SEAT_ENV: "seat-lct"})
    with _SwapHome(home):
        m = FakeMcp(pending=[dict(ROW, transport=None)])
        drain_once(plugin_id="cbp-being", mcp=m, sender=lambda *a: (True, "ledger=9"), log=lambda *_: None)
    mark = [a for n, a in m.calls if "mark_forwarded" in a][0]
    assert mark["carrier_lct"] == "seat-lct", "an unbound send still names who signed"


def test_daemon_refusals_reach_the_summary():
    class Refusing(FakeMcp):
        def call(self, name, args):
            if name == "hestia_egress_pending" and "mark_forwarded" not in args and "mark_failed" not in args:
                self.calls.append((name, dict(args)))
                return _sc({"pending": [], "transport_refused": [{"row_id": 3, "fault": "transport-stale",
                                                                  "reported_to": "cbp-being"}]})
            return super().call(name, args)
    r = drain_once(plugin_id="cbp-being", mcp=Refusing(), sender=lambda *a: (True, ""), log=lambda *_: None)
    assert r["empty"] is False and r["transport_faults"][0]["fault"] == "transport-stale"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")
