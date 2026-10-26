"""An exact grant reaches its own path in the reference dispatcher, not the subtree under it.

Found writing SAGE #516's exact-grant test (2026-10-22): ReferenceF1aDispatcher confined to
`verdict.granted` by prefix and never read `granted_reach`, so an EXACT grant on a directory let
memory_read and memory_write reach every file beneath it, and the gate did not deny the read
either. hestia_dispatch has honoured exact vs recursive since #1002; this is the last mile that
did not. These run the REAL hestia gate core (isolated, no daemon) on an injected snapshot, then
the real dispatcher on the verdict it returns.

Run: python3 -m pytest sage/gateway/tests/test_exact_grant_reach.py
"""
import os
import sys
import tempfile
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))
import _isolate_hestia  # noqa: E402,F401  (never the live daemon: no chain record in a being's name)
from sage.gateway import being_gate_client as B  # noqa: E402
from sage.gateway.reference_f1a import ReferenceF1aDispatcher  # noqa: E402


def _full(reach):
    """Reach as (root, recursive), each entry checked to be a full-mode grant. A core with hestia
    #1383 (`scope_roots_with_modes`) adds the modes as a third element; an older one does not."""
    for e in reach:
        assert len(e) == 2 or e[2] == "rwed", e
    return tuple(tuple(e[:2]) for e in reach)


def _need_core():
    if B.BeingGateClient("probe-being", os.path.join(tempfile.mkdtemp(), "identity.json"),
                         tempfile.mkdtemp())._core is None:
        pytest.skip("no hestia gate core on this machine")


def _world():
    root = os.path.realpath(tempfile.mkdtemp(prefix="exact-grant-reach-"))
    ws = os.path.join(root, "ws")
    gov = os.path.join(ws, "governance", "hestia")
    os.makedirs(os.path.join(gov, "core"))
    open(os.path.join(gov, "closure.py"), "w").write("CLOSURE = 1\n")
    open(os.path.join(gov, "core", "http.rs"), "w").write("fn http() {}\n")
    open(os.path.join(gov, "core", "state_lock.rs"), "w").write("fn lock() {}\n")
    home = os.path.join(root, "home")
    os.makedirs(home)
    return ws, gov, home


def _client(ws, snapshot):
    c = B.BeingGateClient("probe-being", os.path.join(os.path.dirname(ws), "identity.json"), ws)
    c._mech = SimpleNamespace(
        fetch_policy_snapshot=lambda *a, **k: snapshot,
        query_society_safety=lambda *a, **k: SimpleNamespace(allow=True, decided=True, message="ok"))
    c._single_gate = None   # the local-law stage: the same core law, fed this snapshot
    return c


def _act(c, home, effector, args):
    intent = B.BeingIntent(effector, args)
    v = c.gate(intent)
    if v.decision == "deny":
        return v, None
    return v, ReferenceF1aDispatcher(home)(intent, v)


def _refused(env):
    return env is None or (not env.ok and "outside your reach" in str(env.error))


def test_an_exact_grant_on_a_directory_reaches_nothing_beneath_it():
    _need_core()
    ws, gov, home = _world()
    c = _client(ws, {"in_scope": ["path:" + gov], "scope_grants": [gov]})
    v, env = _act(c, home, "memory_read", {"path": os.path.join(gov, "closure.py")})
    assert _full(v.granted_reach) == ((gov, False),), v.granted_reach
    assert _refused(env), env and (env.ok, env.result, env.error)
    _, env = _act(c, home, "memory_write", {"path": os.path.join(gov, "new.py"), "content": "x = 1\n"})
    assert _refused(env), env and (env.ok, env.result, env.error)
    assert not os.path.exists(os.path.join(gov, "new.py"))
    _, env = _act(c, home, "memory_read", {"path": os.path.join(gov, "core", "http.rs")})
    assert _refused(env), env and (env.ok, env.result, env.error)


def test_the_refusal_names_an_exact_root_as_exact():
    _need_core()
    ws, gov, home = _world()
    c = _client(ws, {"in_scope": ["path:" + gov], "scope_grants": [gov]})
    _, env = _act(c, home, "memory_read", {"path": os.path.join(gov, "closure.py")})
    if env is not None:
        assert f"{gov} (exactly this path, nothing under it)" in str(env.error), env.error


def test_exact_file_grants_read_and_reach_no_sibling():
    """The being's real shape: exact grants on single files (http.rs, state_lock.rs)."""
    _need_core()
    ws, gov, home = _world()
    http = os.path.join(gov, "core", "http.rs")
    lock = os.path.join(gov, "core", "state_lock.rs")
    c = _client(ws, {"in_scope": ["path:" + http], "scope_grants": [http]})
    dec, env = _act(c, home, "memory_read", {"path": http})
    assert dec.decision != "deny" and env.ok and "fn http" in str(env.result), (dec, env and env.error)
    _, env = _act(c, home, "memory_read", {"path": lock})
    assert _refused(env), env and (env.ok, env.result, env.error)


def test_a_recursive_grant_still_reaches_its_subtree():
    _need_core()
    ws, gov, home = _world()
    c = _client(ws, {"in_scope": ["path:" + gov + "/**"], "scope_grants": [gov]})
    v, env = _act(c, home, "memory_read", {"path": os.path.join(gov, "core", "http.rs")})
    assert _full(v.granted_reach) == ((gov, True),), v.granted_reach
    assert env.ok and "fn http" in str(env.result), env.error
    # Carrier: a grant is READ reach; writes stay in the being's home and worktree whatever the
    # gate grants (write + check would be code running as the seat). Main lets this write land.
    _, env = _act(c, home, "memory_write", {"path": os.path.join(gov, "new.py"), "content": "x = 1\n"})
    assert not env.ok and "writes stay inside your own home" in str(env.error), env.error


def test_the_home_is_always_recursive():
    _need_core()
    ws, gov, home = _world()
    os.makedirs(os.path.join(home, "notes"))
    open(os.path.join(home, "notes", "plan.md"), "w").write("the plan\n")
    c = _client(ws, {"in_scope": ["path:" + gov], "scope_grants": [gov]})
    _, env = _act(c, home, "memory_read", {"path": "notes/plan.md"})
    assert env.ok and "the plan" in str(env.result), env.error


def test_a_verdict_without_reach_keeps_the_prefix_reading():
    """An older client or a hand-made verdict carries `granted` alone. Carrier: a bare entry is read
    as EXACT (fail closed, reconciliation 2026-09-22); main reads it by prefix. The root itself
    still reaches; what is under it does not."""
    ws, gov, home = _world()
    v = SimpleNamespace(decision="allow", granted=(gov,), granted_reach=())
    env = ReferenceF1aDispatcher(home)(B.BeingIntent("memory_read", {"path": os.path.join(gov, "closure.py")}), v)
    assert not env.ok and "exactly this path, nothing under it" in str(env.error), env.error
