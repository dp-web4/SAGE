"""A bare repo-name scope reaches the dispatcher only when it IS an operator's recursive grant.

Nova's hold on #516 at 77f7137c: "`_repo_name_roots` converts *every* bare policy name into a
recursively readable/writable filesystem root, not just grants minted by the recursive-directory
mapping." Reach in the dispatcher is read AND write, so a declarative repo scope must not become
one. These run the REAL hestia gate core (isolated, no daemon) on an injected policy snapshot, then
the real dispatcher on the verdict it returns, so the gate's answer and the last mile are checked
together.

The reach matrix (dispatcher outcome for a read and a write under <ws>/<name>):

  snapshot                                         before #516   #516@77f7137c   now
  recursive grant ws/governance/** (bare name)     refused       reaches         reaches
  declarative bare name, no grant behind it        refused       REACHES         refused
  bare name for a symlinked ws child (-> outside)  refused       REACHES target  refused
  exact grant ws/governance (path: form)           exact only    exact only      exact only
  nothing                                          refused       refused         refused

Run: python3 -m pytest sage/gateway/tests/test_repo_name_grant_reach.py
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

def _need_core():
    if B.BeingGateClient("probe-being", os.path.join(tempfile.mkdtemp(), "identity.json"),
                         tempfile.mkdtemp())._core is None:
        pytest.skip("no hestia gate core on this machine")


def _world():
    root = os.path.realpath(tempfile.mkdtemp(prefix="repo-name-reach-"))
    ws = os.path.join(root, "ws")
    outside = os.path.join(root, "outside")
    for d in (os.path.join(ws, "governance", "hestia"), os.path.join(ws, "SAGE"), outside):
        os.makedirs(d)
    open(os.path.join(ws, "governance", "hestia", "closure.py"), "w").write("CLOSURE = 1\n")
    open(os.path.join(ws, "SAGE", "code.py"), "w").write("CODE = 1\n")
    open(os.path.join(outside, "secret.txt"), "w").write("SECRET\n")
    os.symlink(outside, os.path.join(ws, "linked"))
    home = os.path.join(root, "home")
    os.makedirs(home)
    return ws, home


def _client(ws, snapshot):
    c = B.BeingGateClient("probe-being", os.path.join(os.path.dirname(ws), "identity.json"), ws)
    c._mech = SimpleNamespace(
        fetch_policy_snapshot=lambda *a, **k: snapshot,
        query_society_safety=lambda *a, **k: SimpleNamespace(allow=True, decided=True, message="ok"))
    c._single_gate = None   # the local-law stage: the same core law, fed this snapshot
    return c


def _act(c, home, effector, args):
    """(gate decision, dispatcher envelope) for one intent through the real gate and dispatcher."""
    intent = B.BeingIntent(effector, args)
    v = c.gate(intent)
    if v.decision == "deny":
        return v.decision, None
    return v.decision, ReferenceF1aDispatcher(home)(intent, v)


def _refused(env):
    return env is None or (not env.ok and "outside your reach" in str(env.error))


def test_a_recursive_grant_on_a_workspace_directory_reads_and_writes_through_gate_and_dispatcher():
    _need_core()
    ws, home = _world()
    gov = os.path.join(ws, "governance")
    c = _client(ws, {"in_scope": ["governance"], "scope_grants": [gov + "/**"]})
    dec, env = _act(c, home, "memory_read", {"path": os.path.join(gov, "hestia", "closure.py")})
    assert dec != "deny" and env.ok and "CLOSURE = 1" in str(env.result), (dec, env and env.error)
    granted, reach = c._policy_grants()     # the single-gate path's reading agrees
    assert granted == (gov,) and reach == ((gov, True),)


def test_a_declarative_bare_name_with_no_grant_behind_it_opens_no_file_surface():
    """The authorization boundary Nova asked for: a role's bare repo scope (here `SAGE`, a real
    directory under the workspace) gives the dispatcher no read and no write there, whatever the
    gate's own segment model says about the name."""
    _need_core()
    ws, home = _world()
    sage = os.path.join(ws, "SAGE")
    for snap in ({"in_scope": ["SAGE"]},
                 {"in_scope": ["SAGE"], "scope_grants": []},
                 {"in_scope": ["SAGE", "governance"], "scope_grants": [os.path.join(ws, "governance")]}):
        c = _client(ws, snap)
        _, env = _act(c, home, "memory_read", {"path": os.path.join(sage, "code.py")})
        assert _refused(env), (snap, env and (env.ok, env.result, env.error))
        _, env = _act(c, home, "memory_write", {"path": os.path.join(sage, "new.py"), "content": "x = 1\n"})
        assert _refused(env), (snap, env and (env.ok, env.result, env.error))
        assert not os.path.exists(os.path.join(sage, "new.py"))
        assert sage not in B._granted_roots(c._core, c._core.resolve_agent_policy(
            c._profile, vault_reader=lambda _m: snap), ws, B._snapshot_grant_paths(snap))


def test_a_bare_name_for_a_symlinked_workspace_child_never_reaches_the_link_target():
    """hestia's mapping realpaths a grant path before naming it, so it never mints a bare name for
    a link; were one to arrive (a grant made when `linked` was a directory, later swapped for a
    link), the root would be the link's TARGET. Refused, with or without a grant naming it."""
    _need_core()
    ws, home = _world()
    linked = os.path.join(ws, "linked")
    for grants in ([linked + "/**"], [linked], [os.path.realpath(linked) + "/**"]):
        c = _client(ws, {"in_scope": ["linked"], "scope_grants": grants})
        _, env = _act(c, home, "memory_read", {"path": os.path.join(linked, "secret.txt")})
        assert _refused(env), (grants, env and (env.ok, env.result, env.error))
        _, env = _act(c, home, "memory_read", {"path": os.path.join(os.path.realpath(linked), "secret.txt")})
        assert _refused(env), (grants, env and (env.ok, env.result, env.error))


def test_an_exact_grant_on_the_same_directory_mints_no_bare_name_root_and_stays_exact():
    """An exact grant on a workspace child keeps hestia's `path:` form, so this change adds
    nothing for it: the reach is recorded exact and no bare-name root appears. (What the reference
    dispatcher then does with a `path:` root is untouched here: it confines to `granted` by
    prefix, the same on main; reported separately rather than changed under this PR.)"""
    _need_core()
    ws, home = _world()
    gov = os.path.join(ws, "governance")
    snap = {"in_scope": ["path:" + gov], "scope_grants": [gov]}
    c = _client(ws, snap)
    policy = c._core.resolve_agent_policy(c._profile, vault_reader=lambda _m: snap)
    assert B._repo_name_roots(c._core, list(policy.scope), ws, B._snapshot_grant_paths(snap)) == ()
    assert c._policy_grants() == ((gov,), ((gov, False),))
    assert (B._granted_roots(c._core, policy, ws, B._snapshot_grant_paths(snap))
            == B._granted_roots(c._core, policy, ws))


def test_the_beats_layout_names_the_grant_against_hestias_root_not_the_sage_checkout(monkeypatch):
    """A being's beat builds its client with the SAGE checkout as `workspace` (heartbeat.py:
    `parents[2]`), while hestia mapped `<ws>/governance/**` to `governance` against <ws>, the
    root its core detects. Measured on cbp-being after #516 merged (2026-10-23 00:41Z): the
    snapshot held the grant and the reach list still omitted it, because the name was read as
    `<ws>/SAGE/governance`. The recursive grant reads; a declarative `SAGE` still reaches
    nothing; a grant on a same-named directory under the checkout is not the one named."""
    _need_core()
    ws, home = _world()
    monkeypatch.setenv("HESTIA_WORKSPACE", ws)
    sage = os.path.join(ws, "SAGE")
    gov = os.path.join(ws, "governance")
    c = _client(ws, {"in_scope": ["governance"], "scope_grants": [gov + "/**"]})
    c.workspace = sage
    dec, env = _act(c, home, "memory_read", {"path": os.path.join(gov, "hestia", "closure.py")})
    assert dec != "deny" and env.ok and "CLOSURE = 1" in str(env.result), (dec, env and env.error)
    assert c._policy_grants() == ((gov,), ((gov, True),))

    c = _client(ws, {"in_scope": ["SAGE"], "scope_grants": [gov + "/**"]})
    c.workspace = sage
    _, env = _act(c, home, "memory_read", {"path": os.path.join(sage, "code.py")})
    assert _refused(env), env and (env.ok, env.result, env.error)

    inner = os.path.join(sage, "governance")
    os.makedirs(inner)
    c = _client(ws, {"in_scope": ["governance"], "scope_grants": [gov + "/**"]})
    c.workspace = sage
    assert c._policy_grants()[0] == (gov,)


def test_no_grant_no_reach():
    _need_core()
    ws, home = _world()
    c = _client(ws, {"in_scope": []})
    _, env = _act(c, home, "memory_read", {"path": os.path.join(ws, "governance", "hestia", "closure.py")})
    assert _refused(env)
