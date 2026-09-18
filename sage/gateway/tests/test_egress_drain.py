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
            if "mark_forwarded" in args or "mark_failed" in args: return _sc({"marked": args.get("mark_forwarded"), "ok": True})
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
                if "mark_forwarded" in args:   # hestia answers a settled mark; {} now reads as unsettled
                    return {"result": {"structuredContent": {"marked": args["mark_forwarded"]}}}
                return {"result": {"structuredContent": {}}}
        old_seat = os.environ.pop("HUB_MESH_ENV", None)
        try:
            out = ed.drain_once(plugin_id="sprout-being", mcp=Mcp(), sender=fake_sender, log=lambda *a: None)
            # no identity file at all: nothing to name, and the default says so
            assert out["forwarded"] == 1 and out["drainer_default_identity"]["signed_as"] == "none"
            with open(os.path.join(home, ".config", "hub-mesh-sprout-being.env"), "w") as f:
                f.write('MY_LCT="2e175714-being"\nMY_KEYPAIR=/k\n')
            out = ed.drain_once(plugin_id="sprout-being", mcp=Mcp(), sender=fake_sender, log=lambda *a: None)
            assert out["drainer_default_identity"] == {"member": "sprout-being", "signed_as": "being",
                                                       "carrier_lct": "2e175714-being"}
        finally:
            if old_seat is not None: os.environ["HUB_MESH_ENV"] = old_seat
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


ENV = "." + "env"
SEAT_ENV = "hub-mesh" + ENV
BEING_ENV = "hub-mesh-cbp-being" + ENV


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


def test_the_signer_is_chosen_for_the_rows_author_not_the_drainer():
    """SAGE #97 review, HOLD 1: A drains, the row is B's. A, B and the seat all hold identity
    files. Stamped B signs as B's carrier; unbound B follows B-then-seat, never A."""
    home = _home_with({SEAT_ENV: "seat-lct", "hub-mesh-a-being" + ENV: "a-lct", "hub-mesh-b-being" + ENV: "b-lct"})
    from sage.gateway import egress_drain as ed
    with _SwapHome(home):
        stamped = dict(ROW, from_plugin="b-being", transport={"mode": "direct", "carrier_lct": "b-lct", "version": 1})
        env_file, label, carrier, refusal = ed.signer_for(stamped, "a-being")
        assert (label, carrier, refusal) == ("being", "b-lct", None) and env_file.endswith("hub-mesh-b-being" + ENV)
        unbound = dict(ROW, from_plugin="b-being", transport=None)
        env_file, label, carrier, _ = ed.signer_for(unbound, "a-being")
        assert (label, carrier) == ("being", "b-lct"), "unbound B must not leave as the drainer A"


def test_a_relay_carrier_may_be_any_identity_on_the_host():
    home = _home_with({SEAT_ENV: "seat-lct", "hub-mesh-courier" + ENV: "courier-lct"})
    from sage.gateway import egress_drain as ed
    row = dict(ROW, from_plugin="b-being", transport={"mode": "relay", "carrier_lct": "courier-lct",
                                                      "delegation_ref": "d1", "version": 2})
    with _SwapHome(home):
        env_file, label, carrier, refusal = ed.signer_for(row, "a-being")
    assert refusal is None and carrier == "courier-lct" and label == "member:courier"


def test_the_resolver_reads_the_lct_the_shell_actually_sources():
    """HOLD 2: a prefix key, a duplicate assignment and `export` are resolved as bash resolves
    them, because the resolver sources the file the same way hub-notify does."""
    import tempfile
    from sage.gateway import egress_drain as ed
    d = tempfile.mkdtemp(prefix="envsem-")
    cases = {
        "prefix": ('MY_LCT_OLD=stamped-lct\nMY_LCT=actual-lct\n', "actual-lct"),
        "duplicate": ('MY_LCT=stamped-lct\nMY_LCT=actual-lct\n', "actual-lct"),
        "export": ('export MY_LCT="actual-lct"  # the live one\n', "actual-lct"),
        "unset": ('MY_KEYPAIR=/k\n', None),
        "broken": ('MY_LCT=x\nif then\n', None),
    }
    for name, (body, want) in cases.items():
        path = os.path.join(d, name)
        with open(path, "w") as f:
            f.write(body)
        assert ed._env_lct(path) == want, (name, ed._env_lct(path))
    old = os.environ.get("MY_LCT"); os.environ["MY_LCT"] = "inherited-lct"
    try:
        assert ed._env_lct(os.path.join(d, "unset")) is None, "an inherited MY_LCT must not stand in for the file"
    finally:
        if old is None: os.environ.pop("MY_LCT", None)
        else: os.environ["MY_LCT"] = old


def test_the_production_send_sources_the_chosen_carriers_file():
    """HOLD 3: through the real _forward path (no injected sender), hub-notify receives the
    chosen carrier's file as HUB_MESH_ENV and no inherited signer variables."""
    import tempfile
    from sage.gateway import egress_drain as ed
    home = _home_with({SEAT_ENV: "seat-lct", BEING_ENV: "being-lct"})
    fake_notify = os.path.join(tempfile.mkdtemp(prefix="notify-"), "hub-notify.sh")
    with open(fake_notify, "w") as f:
        f.write("#!/bin/sh\nexit 0\n")
    os.chmod(fake_notify, 0o755)
    seen = []
    class P:
        returncode = 0; stdout = "[hub-notify] -> legion kind=coordination ledger=42 hash=h"; stderr = ""
    real_run = ed.subprocess.run
    def fake_run(argv, **kw):
        if argv and argv[0] == fake_notify:
            seen.append(dict(kw["env"])); return P()
        return real_run(argv, **kw)
    old_notify = ed.HUB_NOTIFY
    ed.HUB_NOTIFY = fake_notify; ed.subprocess.run = fake_run
    os.environ["MY_LCT"] = "inherited-lct"
    try:
        with _SwapHome(home):
            for transport, want in (({"mode": "direct", "carrier_lct": "being-lct", "version": 1}, BEING_ENV),
                                    ({"mode": "relay", "carrier_lct": "seat-lct", "delegation_ref": "d", "version": 2}, SEAT_ENV)):
                m = FakeMcp(pending=[dict(ROW, from_plugin="cbp-being", transport=transport)])
                r = drain_once(plugin_id="cbp-being", mcp=m, log=lambda *_: None)
                assert r["forwarded"] == 1, r
                assert seen[-1]["HUB_MESH_ENV"].endswith(want), seen[-1].get("HUB_MESH_ENV")
                assert "MY_LCT" not in seen[-1], "the file decides, not the inherited environment"
                mark = [a for n, a in m.calls if "mark_forwarded" in a][0]
                assert mark["carrier_lct"] == transport["carrier_lct"] and mark["hub_receipt"] == {"ledger": "42"}
    finally:
        ed.HUB_NOTIFY = old_notify; ed.subprocess.run = real_run; os.environ.pop("MY_LCT", None)


def test_a_send_hestia_does_not_settle_is_not_a_clean_forward():
    """The seam this PR makes load-bearing: the hub took it, hestia refused the mark."""
    class Unsettled(FakeMcp):
        def call(self, name, args):
            if name == "hestia_egress_pending" and "mark_forwarded" in args:
                self.calls.append((name, dict(args)))
                return _sc({"_hestia_error": {"code": "hestia.egress_unattributed", "message": "x"}})
            return super().call(name, args)
    home = _home_with({SEAT_ENV: "seat-lct"})
    with _SwapHome(home):
        r = drain_once(plugin_id="cbp-being", mcp=Unsettled(pending=[dict(ROW, transport=None)]),
                       sender=lambda *a: (True, "ledger=5"), log=lambda *_: None)
    assert r["forwarded"] == 0 and r["unsettled"] == 1
    assert r["transport_faults"][0]["fault"] == "sent-but-unsettled"


def test_the_summary_names_each_rows_carrier_not_the_drainers():
    """SAGE #97 review round 2: A drains; B authored the row; C carries it. The returned
    summary, the thing the beat record keeps, must say C for that row and must not present
    A's identity as the carrier of anything."""
    home = _home_with({SEAT_ENV: "seat-lct", "hub-mesh-a-being" + ENV: "a-lct",
                       "hub-mesh-b-being" + ENV: "b-lct", "hub-mesh-courier" + ENV: "c-lct"})
    relay = dict(ROW, id=11, from_plugin="b-being",
                 transport={"mode": "relay", "carrier_lct": "c-lct", "delegation_ref": "d", "version": 3})
    unbound = dict(ROW, id=12, from_plugin="b-being", transport=None)
    orphan = dict(ROW, id=13, from_plugin="b-being", transport={"mode": "direct", "carrier_lct": "z-lct", "version": 3})
    with _SwapHome(home):
        r = drain_once(plugin_id="a-being", mcp=FakeMcp(pending=[relay, unbound, orphan]),
                       sender=lambda *a: (True, "ledger=77"), log=lambda *_: None)
    rows = {x["row_id"]: x for x in r["forwarded_rows"]}
    assert rows[11] == {"row_id": 11, "from_plugin": "b-being", "carrier_lct": "c-lct",
                        "signed_as": "member:courier", "hub_receipt": {"ledger": "77"}}, rows[11]
    assert rows[12]["carrier_lct"] == "b-lct" and rows[12]["signed_as"] == "being"
    fault = r["transport_faults"][0]
    assert fault["row_id"] == 13 and fault["from_plugin"] == "b-being" and fault["carrier_lct"] is None
    assert "signed_as" not in r and "carrier" not in r, "no pass-level carrier claim survives"
    assert r["drainer_default_identity"] == {"member": "a-being", "signed_as": "being", "carrier_lct": "a-lct"}


def test_a_mesh_send_failure_is_row_shaped_too():
    """GPT's post-merge note on #97: the summary promised every handled row is represented,
    and an ordinary send failure only incremented a counter."""
    home = _home_with({SEAT_ENV: "seat-lct"})
    with _SwapHome(home):
        m = FakeMcp(pending=[dict(ROW, id=5, from_plugin="cbp-being", transport=None)])
        r = drain_once(plugin_id="cbp-being", mcp=m,
                       sender=lambda *a: (False, "hub refused: unknown peer 'nobody'"), log=lambda *_: None)
    assert r["failed"] == 1 and r["forwarded"] == 0
    f = r["transport_faults"][0]
    assert f["fault"] == "send-failed" and f["row_id"] == 5 and f["from_plugin"] == "cbp-being"
    assert f["carrier_lct"] == "seat-lct" and f["signed_as"] == "seat" and "unknown peer" in f["detail"]


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

    RECONCILED 2026-09-18. This branch reported ONE label for the pass (`signed_as`, plus a
    `carrier_gap` sentence). main replaced that with a PER-ROW record, and its reasoning
    holds: the signer is chosen per row, so a pass-level label is false by construction the
    moment a drain carries a row for another member. The property this test exists for —
    the record says who carried the act, rather than a log line nobody kept — is asserted
    against the per-row fields.
    """
    from sage.gateway import egress_drain as E

    # no hub identity for this member -> the seat signs, which is today's silent default
    monkeypatch.setattr(E, "signer_for", lambda row, pid: (None, "seat", None, None))
    m = FakeMcp(pending=[ROW])
    r = drain_once(mcp=m, plugin_id="legion-being", log=lambda *_: None,
                   sender=lambda to, kind, ptr, **kw: (True, "ledger=77"))
    assert r["forwarded"] == 1
    (row,) = r["forwarded_rows"]
    assert row["signed_as"] == "seat", r          # who actually carried it, on the row
    assert row["from_plugin"] == ROW.get("from_plugin"), r
    # the default identity is resolved through the same path and is a fact about the HOST,
    # not a claim about this row: with no env for the member it signs as nothing at all.
    assert r["drainer_default_identity"]["member"] == "legion-being", r

    # with the being's own hub identity present the row says the being signed
    monkeypatch.setattr(E, "signer_for", lambda row, pid: ("/x/being-hub-identity", "being", "lct:being", None))
    r2 = drain_once(mcp=FakeMcp(pending=[ROW]), plugin_id="legion-being", log=lambda *_: None,
                    sender=lambda to, kind, ptr, **kw: (True, "ledger=77"))
    (row2,) = r2["forwarded_rows"]
    assert row2["signed_as"] == "being" and row2["carrier_lct"] == "lct:being", r2

    # and nothing forwarded reports no rows, not a carrier complaint
    r3 = drain_once(mcp=FakeMcp(pending=[]), plugin_id="legion-being", log=lambda *_: None,
                    sender=lambda to, kind, ptr, **kw: (True, "ledger=77"))
    assert r3["forwarded_rows"] == [] and r3["empty"] is True
