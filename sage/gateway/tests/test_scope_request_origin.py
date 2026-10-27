"""SAGE #572: a scope ask the dispatcher files after a gate deny says so, to a daemon that can check it.

cbp-being, 2026-10-27: 14 pending asks, all filed by escalate after an mrh.* deny, all classed member-filed by
the daemon (peers could not decide them; each was an operator card). The ask now carries origin + the deny's
chain hash, but ONLY to a daemon that advertises it reads them (hestia #1425), and only when there is a hash:
a claim nobody can check is never made, and a daemon that does not know the fields never sees them."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict, ResultEnvelope  # noqa: E402
from sage.gateway import escalate as e  # noqa: E402


class _FakeMcp:
    """Plays the daemon: records each call; scope_status advertises `supports` as the test sets it."""
    supports = []
    calls = []

    def __init__(self, endpoint, member):
        pass

    def init(self):
        pass

    def call(self, tool, args):
        _FakeMcp.calls.append((tool, dict(args)))
        if tool == "hestia_connect":
            return {"sessionId": "s1"}
        if tool == "hestia_scope_status":
            return {"requests": [], "supports": list(_FakeMcp.supports)}
        if tool == "hestia_request_scope":
            return {"request_id": "scope-1", "status": "pending"}
        return {}


def _file(monkeypatch, supports, deny_witness):
    _FakeMcp.supports, _FakeMcp.calls = supports, []
    monkeypatch.setattr(e, "_Mcp", _FakeMcp)
    monkeypatch.setattr(e, "_unwrap", lambda r: r)
    out = e._file_scope_request("b", "/x/notes", "b was refused", "http://d", deny_witness=deny_witness)
    sent = [a for t, a in _FakeMcp.calls if t == "hestia_request_scope"]
    assert len(sent) == 1
    return out, sent[0]


def test_an_auto_filed_ask_carries_its_origin_and_the_deny_to_a_daemon_that_reads_them(monkeypatch):
    out, sent = _file(monkeypatch, [e.REQUEST_ORIGIN_CAPABILITY], "a" * 64)
    assert sent["origin"] == "dispatcher_after_deny" and sent["deny_witness"] == "a" * 64
    assert out["origin"] == "dispatcher_after_deny" and out["request_id"] == "scope-1"


def test_a_daemon_that_does_not_advertise_it_never_sees_the_fields(monkeypatch):
    out, sent = _file(monkeypatch, [], "a" * 64)
    assert "origin" not in sent and "deny_witness" not in sent and "origin" not in out


def test_no_deny_hash_means_no_claim(monkeypatch):
    # the deny was not witnessed: there is nothing the daemon could check, so it stays member-filed
    for missing in (None, ""):
        out, sent = _file(monkeypatch, [e.REQUEST_ORIGIN_CAPABILITY], missing)
        assert "origin" not in sent and "deny_witness" not in sent and "origin" not in out


def _daemon_would_accept(asked: str, target: str, home: str) -> bool:
    """hestia #1425's containment rule as nomad proposed it on #573: the deny's target t (from its chain row)
    and the asked path a pass when a == t, a == dirname(t), or a is the member's home root with t under it.
    Anything broader stays member-filed, so one deny cannot carry a wide ask into the quiet tier."""
    return (asked == target or asked == os.path.dirname(target)
            or (asked == home and (target == home or target.startswith(home.rstrip("/") + "/"))))


def test_every_path_scope_path_files_is_one_the_daemon_containment_rule_accepts():
    # The contract between the halves (nomad on #573): the dispatcher files _scope_path's answer, not the deny's
    # target. Each shape it emits must pass #1425's rule against the deny it follows, or the claim silently fails.
    home = "/x/instances/b"
    shapes = [
        ("notes/a.md", "/x/instances/b/notes/a.md", home),       # inside the home -> the home root
        ("/other/dir/f.txt", "/other/dir/f.txt", "/other/dir"),  # a file elsewhere -> its directory
        ("/other/dir", "/other/dir", "/other/dir"),              # a bare directory elsewhere -> itself
    ]
    for raw, target, expected in shapes:
        asked = e._scope_path(BeingIntent("memory_read", {"path": raw}), home)
        assert asked == expected, (raw, asked)
        assert _daemon_would_accept(asked, target, home), (raw, asked, target)
    # and the rule refuses what would be laundering: an ask wider than the deny's own reach
    assert not _daemon_would_accept("/other", "/other/dir/f.txt", home)
    assert not _daemon_would_accept("/", "/x/instances/b/notes/a.md", home)


def test_route_threads_the_verdicts_witness_id(monkeypatch):
    seen = {}
    monkeypatch.setattr(e, "_file_scope_request",
                        lambda member, path, why, endpoint, **kw: (seen.update(kw) or {"request_id": "s", "status": "pending"}))
    e.NOTE_DIR = tempfile.mkdtemp()
    for wid in ("b" * 64, None):
        env = ResultEnvelope(ok=False, refused=True, error="mrh.path: outside",
                             verdict=GatewayVerdict("deny", "mrh.path", "outside", stage="local-law", witness_id=wid))
        e.escalate("b", BeingIntent("memory_write", {"path": "notes/a.md"}), env, "/x/instances/b", wake=False)
        assert seen.get("deny_witness") == wid
