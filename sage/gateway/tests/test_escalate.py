"""Hermetic tests for refusal routing: classification, scope-path derivation, the note's protocol."""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict, ResultEnvelope  # noqa: E402
from sage.gateway import escalate as e  # noqa: E402

def _ref(rule, reason=""):
    return ResultEnvelope(ok=False, refused=True, error=f"{rule}: {reason}", verdict=GatewayVerdict("deny", rule, reason, stage="local-law"))

def test_classify():
    assert e.classify(_ref("registry.unbounded")) == "registry"
    assert e.classify(_ref("mrh.path", "outside your granted scope")) == "scope"
    assert e.classify(_ref("society.unsafe")) == "society"
    assert e.classify(_ref("gate.escalated", "escalation id: esc-abc123def")) == "governance"

def test_registry_refusal_is_never_escalated():
    r = e.escalate("b", BeingIntent("shell", {"command": "rm -rf /"}), _ref("registry.unbounded"), "/tmp", wake=False)
    assert r["escalated"] is False and "final" in r["why"]

def test_scope_path_is_the_home_when_inside_it_else_the_targets_directory():
    root = "/x/instances/b"
    # inside the home the ask is always the home itself (one standing grant covers every subpath)
    assert e._scope_path(BeingIntent("memory_write", {"path": "notes/a.md"}), root) == "/x/instances/b"
    assert e._scope_path(BeingIntent("memory_write", {"path": "journal.md"}), root) == "/x/instances/b"
    assert e._scope_path(BeingIntent("memory_write", {"path": "notes"}), root) == "/x/instances/b"
    # a sibling instance is NOT inside (prefix must end at a path separator)
    assert e._scope_path(BeingIntent("memory_write", {"path": "/x/instances/bb/a.md"}), root) == "/x/instances/bb"
    assert e._scope_path(BeingIntent("memory_write", {"path": "../c/a.md"}), root) == "/x/instances/c"
    assert e._scope_path(BeingIntent("memory_write", {"path": "/other/dir/f.txt"}), root) == "/other/dir"

def test_note_carries_verdict_and_arbiter_protocol(monkeypatch=None):
    d = tempfile.mkdtemp(); e.NOTE_DIR = d
    p = e.write_note("b", BeingIntent("memory_write", {"path": "/o/f.md"}), _ref("mrh.path", "outside"), "scope", {"scope_request": {"request_id": "scope-1"}})
    t = open(p).read()
    assert "mrh.path" in t and "scope-1" in t and "Arbiter protocol" in t and "STANDING" in t

def test_no_wake_files_the_request_but_writes_no_note():
    # the heartbeat's 2nd..9th refusal of a kind in one beat: the request is (re)filed and deduped
    # by the daemon; a note only exists to be pointed at by a wake, so none is written
    d = tempfile.mkdtemp(); e.NOTE_DIR = d
    filed = []
    orig = e._file_scope_request
    e._file_scope_request = lambda member, path, why, endpoint: (filed.append(path) or {"request_id": "scope-x", "status": "pending"})
    try:
        r = e.escalate("b", BeingIntent("memory_write", {"path": "notes/a.md"}), _ref("mrh.path", "outside"), "/x/instances/b", wake=False)
    finally:
        e._file_scope_request = orig
    assert r["escalated"] is True and r["scope_request"]["request_id"] == "scope-x" and filed
    assert "note" not in r and "wake" not in r and os.listdir(d) == []

def test_two_notes_in_one_second_get_distinct_files():
    d = tempfile.mkdtemp(); e.NOTE_DIR = d
    orig = e.time.strftime
    e.time.strftime = lambda *_: "2026-09-05-000000"
    try:
        i, v = BeingIntent("memory_write", {"path": "/o/f.md"}), _ref("mrh.path", "outside")
        a = e.write_note("b", i, v, "scope", {}); b = e.write_note("b", i, v, "scope", {}); c = e.write_note("b", i, v, "scope", {})
    finally:
        e.time.strftime = orig
    assert len({a, b, c}) == 3 and a.endswith("-000000.md") and b.endswith("-000000-2.md") and c.endswith("-000000-3.md")

def test_seat_is_the_beings_own_machine_not_sprout():
    # identity.json names the machine -> that seat; no file -> the member prefix
    d = tempfile.mkdtemp()
    assert e.seat_for("legion-being", d) == "legion"
    assert e.seat_for("sprout-being", d) == "sprout"
    assert e.seat_for("cbp-being") == "cbp"
    import json
    open(os.path.join(d, "identity.json"), "w").write(json.dumps({"identity": {"machine": "Thor"}}))
    assert e.seat_for("legion-being", d) == "thor"
    # the gate workspace is this checkout, whatever its name (Legion: ~/ai-workspace/SAGE)
    assert os.path.isdir(os.path.join(e.WORKSPACE, "sage", "gateway"))

def test_heartbeat_routes_refusals_by_default():
    import sage.gateway.heartbeat as hb, inspect
    src = inspect.getsource(hb.main)
    assert "--no-escalate" in src and "_esc.escalate(" in src
    assert "egress_drain.drain_once(" in src   # the being's parked mesh acts leave every beat

def test_home_file_mis_rooted_gets_a_hint_not_an_operator_request():
    import os, tempfile
    from sage.gateway.escalate import escalate, home_hint
    from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict, ResultEnvelope
    root = tempfile.mkdtemp(prefix="home-")
    deny = ResultEnvelope(ok=False, refused=True, verdict=GatewayVerdict("deny", "mrh.path", "outside"),
                          error="mrh.path: outside your granted scope")
    i = BeingIntent("memory_write", {"path": "/repo/sage/journal.md", "content": "x"})
    assert home_hint(i, root) == os.path.join(os.path.realpath(root), "journal.md")
    r = escalate("sprout-being", i, deny, root, wake=False)
    assert r["escalated"] is False and "no grant needed" in r["hint"] and "scope_request" not in r
    # the home file itself, and a path that is not a home file, are real asks
    assert home_hint(BeingIntent("memory_write", {"path": os.path.join(root, "journal.md")}), root) is None
    assert home_hint(BeingIntent("memory_read", {"path": "/repo/shared/notes.txt"}), root) is None


def test_bare_home_filename_is_the_home_file_and_a_real_ask(monkeypatch=None):
    # cbp-being's first beat (2026-09-12): every write was `path: "journal.md"`, the gate rooted
    # it in the home and refused on an EMPTY grant, and the router read the bare name against
    # the process cwd, called it mis-rooted, and filed nothing. A bare home filename IS the
    # home file: no hint, and the refusal escalates as a scope ask on the home dir.
    import os, tempfile
    import sage.gateway.escalate as esc
    from sage.gateway.escalate import escalate, home_hint
    from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict, ResultEnvelope, _home_hint
    from sage.gateway import block_census
    root = tempfile.mkdtemp(prefix="home-")
    for rel in ("journal.md", "./todo.md", "notes/../journal.md"):
        assert home_hint(BeingIntent("memory_write", {"path": rel, "content": "x"}), root) is None, rel
    class _D:  # what the client's hint sees: a dispatcher that knows the memory root
        memory_root = root
    assert _home_hint(BeingIntent("memory_write", {"path": "journal.md", "content": "x"}), _D()) == ""
    assert "no grant is needed" in _home_hint(BeingIntent("memory_write", {"path": "/repo/sage/journal.md", "content": "x"}), _D())
    from pathlib import Path
    assert block_census.classify("memory_write", "mrh.path", "journal.md", Path(root)) != "mis-rooted-home"
    assert block_census.classify("memory_write", "mrh.path", "/repo/sage/journal.md", Path(root)) == "mis-rooted-home"
    filed = {}
    def _fake_file(member, path, why, endpoint):
        filed.update({"member": member, "path": path}); return {"request_id": "scope-test", "status": "filed"}
    orig = esc._file_scope_request; esc._file_scope_request = _fake_file
    try:
        deny = ResultEnvelope(ok=False, refused=True, verdict=GatewayVerdict("deny", "mrh.path", "outside"),
                              error="mrh.path: outside your granted scope: 'sage' is not granted (granted: )")
        r = escalate("cbp-being", BeingIntent("memory_write", {"path": "journal.md", "content": "x"}), deny, root, wake=False)
    finally:
        esc._file_scope_request = orig
    assert filed.get("path") == os.path.abspath(root), (filed, r)
    assert r.get("escalated") is not False or "hint" not in r, r


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


def test_refusal_beneath_an_exact_home_grant_routes_to_the_operator_and_files_nothing():
    # cbp-being 2026-09-12 (first beat on the new mind): home granted bare after hestia #1002,
    # journal.md refused, and this module asked the daemon for the home root the being already
    # held — `already_granted`, request_id null, 22 escalations in one beat, nothing to rule on.
    root = tempfile.mkdtemp(); d = tempfile.mkdtemp(); e.NOTE_DIR = d
    real = os.path.realpath(root)
    i = BeingIntent("memory_write", {"path": "journal.md", "content": "x"})
    hint = (f"'sage' is not granted (granted: path:{real}); note: your grant path:{real} is EXACT — "
            f"it reaches that path itself and nothing beneath it.")
    env = ResultEnvelope(ok=False, refused=True, error=hint,
                         verdict=GatewayVerdict("deny", "mrh.path", hint, stage="local-law",
                                                granted=(real,), granted_reach=((real, False),)))
    assert e.exact_root_above(env, os.path.join(real, "journal.md")) == real
    # reach absent from the verdict: the gate's own hint names the root
    assert e.exact_root_above(_ref("mrh.path", hint), os.path.join(real, "journal.md")) == real
    # a recursive grant is not this case
    rec = ResultEnvelope(ok=False, refused=True, error="x",
                         verdict=GatewayVerdict("deny", "mrh.path", "x", granted_reach=((real, True),)))
    assert e.exact_root_above(rec, os.path.join(real, "journal.md")) is None
    filed = []
    orig = e._file_scope_request
    e._file_scope_request = lambda *a: (filed.append(a) or {"request_id": "scope-x", "status": "pending"})
    try:
        r = e.escalate("cbp-being", i, env, root, wake=False)
    finally:
        e._file_scope_request = orig
    assert r["escalated"] is True and not filed, r
    assert r["scope_request"] == {"request_id": None, "status": "exact_grant", "root": real,
                                  "needs": "operator: make the standing grant recursive"}
    t = open(e.write_note("cbp-being", i, env, "scope", r)).read()
    assert "NO request_id" in t and "standing/recursive" in t and real in t and "Arbiter protocol" in t
