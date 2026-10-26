"""hestia #1345 part B, SAGE's side: the dispatcher confines by the modes the gate judged by.

A core that enforces modes exports scope_roots_with_modes(); _granted_reach passes the modes
through as a third element, and the dispatcher's own confinement requires r to read and w to
write. A run mounts every grant that holds r (`run_grant_mounts`: `--ro-bind` unless the grant
holds both w and d); the live single gate judges a run by its script path, never by that line
(hestia #1388 README, point 3)."""
import os
import sys
import tempfile
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict, _granted_reach  # noqa: E402
from sage.gateway.hestia_dispatch import _mode_has  # noqa: E402
from sage.gateway.reference_f1a import ReferenceF1aDispatcher  # noqa: E402


# CARRIER: writes outside the home reach only the being's WORKTREE (the 2026-09-07 stopgap / M1),
# so a test that writes through a grant makes the granted tree the worktree, with its sandbox
# available. The modes then decide exactly as on main (reference_f1a: a write outside the home
# needs w in the grants that cover it).
def _as_worktree(d, wt):
    d.worktree = wt
    d._wt_writable = True
    return d


def _world(modes):
    ws = os.path.realpath(tempfile.mkdtemp(prefix="modes-ws-"))
    home = os.path.join(ws, "home")
    forum = os.path.join(ws, "forum")
    os.makedirs(home)
    os.makedirs(forum)
    open(os.path.join(forum, "thread.md"), "w").write("hello\n")
    v = GatewayVerdict("allow", granted=(forum,), granted_reach=((forum, True, modes),))
    return _as_worktree(ReferenceF1aDispatcher(memory_root=home), forum), forum, v


def test_a_read_only_grant_reads_and_refuses_a_write_naming_the_mode():
    d, forum, v = _world("r")
    r = d(BeingIntent("memory_read", {"path": os.path.join(forum, "thread.md")}), v)
    assert r.ok and "hello" in (r.result or ""), r
    r = d(BeingIntent("memory_write", {"path": os.path.join(forum, "new.md"), "content": "x"}), v)
    assert not r.ok and "narrowed to r" in (r.error or "") and "writing needs w" in r.error, r
    assert not os.path.exists(os.path.join(forum, "new.md")), "nothing may be written"


def test_a_write_only_grant_appends_and_refuses_a_read():
    d, forum, v = _world("w")
    r = d(BeingIntent("memory_write", {"path": os.path.join(forum, "drop.md"), "content": "x"}), v)
    assert r.ok, r
    r = d(BeingIntent("memory_read", {"path": os.path.join(forum, "thread.md")}), v)
    assert not r.ok or "hello" not in (r.result or ""), r
    assert "narrowed to w" in (r.error or r.result or ""), r


def test_a_full_mode_or_modeless_grant_is_unchanged():
    for modes in ("rwed", None):
        ws = os.path.realpath(tempfile.mkdtemp(prefix="modes-ws-"))
        home, forum = os.path.join(ws, "home"), os.path.join(ws, "forum")
        os.makedirs(home)
        os.makedirs(forum)
        item = (forum, True, modes) if modes else (forum, True)
        v = GatewayVerdict("allow", granted=(forum,), granted_reach=(item,))
        d = _as_worktree(ReferenceF1aDispatcher(memory_root=home), forum)
        r = d(BeingIntent("memory_write", {"path": os.path.join(forum, "n.md"), "content": "x"}), v)
        assert r.ok, (modes, r)
        r = d(BeingIntent("memory_read", {"path": os.path.join(forum, "n.md")}), v)
        assert r.ok and "x" in r.result, (modes, r)


def test_the_home_is_always_all_four_modes():
    d, forum, v = _world("r")
    r = d(BeingIntent("memory_write", {"path": "notes/x.md", "content": "y"}), v)
    assert r.ok, r


def test_granted_reach_takes_the_cores_modes_when_it_has_them():
    pol = SimpleNamespace(scope=("path:/w/a/**",))
    core = SimpleNamespace(scope_roots_with_modes=lambda p, ws: (("/w/a", True, "rwed"), ("/w/f", True, "r")),
                           _scope_roots_with_reach=lambda s, ws: (("/w/a", True),))
    got = _granted_reach(core, pol, "/w")
    assert ("/w/f", True, "r") in got and ("/w/a", True, "rwed") in got, got
    # an older core without modes: today's two-element reading
    core_old = SimpleNamespace(_scope_roots_with_reach=lambda s, ws: (("/w/a", True),))
    assert _granted_reach(core_old, pol, "/w") == (("/w/a", True),)


def test_mode_has_reads_a_missing_third_element_as_full():
    assert _mode_has([], "r") and _mode_has(["r"], "r") and not _mode_has(["w"], "r")


def test_two_grants_on_one_root_union_their_modes_as_the_gate_does():
    """nomad review of #533, point 1: keyed on the root alone, a full recursive grant and an `r`
    grant on the same root collapsed to whichever came last, so a write the gate (union) admitted
    was refused here. Keyed on (root, recursive) with modes unioned, the two agree."""
    ws = os.path.realpath(tempfile.mkdtemp(prefix="modes-ws-"))
    home, forum = os.path.join(ws, "home"), os.path.join(ws, "forum")
    os.makedirs(home)
    os.makedirs(forum)
    for reach in (((forum, True, "rwed"), (forum, True, "r")),
                  ((forum, True, "r"), (forum, True, "rwed")),
                  ((forum, True, "r"), (forum, True, "w"))):
        v = GatewayVerdict("allow", granted=(forum,), granted_reach=reach)
        d = _as_worktree(ReferenceF1aDispatcher(memory_root=home), forum)
        r = d(BeingIntent("memory_write", {"path": os.path.join(forum, "u.md"), "content": "x"}), v)
        assert r.ok, (reach, r)
        r = d(BeingIntent("memory_read", {"path": os.path.join(forum, "u.md")}), v)
        assert r.ok and "x" in r.result, (reach, r)
    # An exact r grant on the root and a recursive w grant on it are different keys.
    v = GatewayVerdict("allow", granted=(forum,), granted_reach=((forum, False, "r"), (forum, True, "w")))
    d = ReferenceF1aDispatcher(memory_root=home)
    r = d(BeingIntent("memory_read", {"path": os.path.join(forum, "u.md")}), v)
    assert not r.ok or "x" not in (r.result or ""), r


# -- hestia #1386 (part C): the nearest explicit grant decides, exactly when the gate does -------

def _nested(rule, child_modes="r", parent_modes="rwed"):
    ws = os.path.realpath(tempfile.mkdtemp(prefix="near-ws-"))
    home, proj = os.path.join(ws, "home"), os.path.join(ws, "proj")
    os.makedirs(home)
    os.makedirs(os.path.join(proj, "sub"))
    os.makedirs(os.path.join(proj, "other"))
    open(os.path.join(proj, "sub", "t.md"), "w").write("child\n")
    reach = ((proj, True, parent_modes), (os.path.join(proj, "sub"), True, child_modes))
    v = GatewayVerdict("allow", granted=(proj, os.path.join(proj, "sub")), granted_reach=reach,
                       reach_rule=rule)
    return _as_worktree(ReferenceF1aDispatcher(memory_root=home), proj), proj, v


def test_under_the_union_rule_a_nested_narrowed_grant_is_part_b_parity():
    """Part B's gate admits a write under an `r` child of a full parent; so must this."""
    d, proj, v = _nested("union")
    r = d(BeingIntent("memory_write", {"path": os.path.join(proj, "sub", "n.md"), "content": "x"}), v)
    assert r.ok, r


def test_under_the_nearest_rule_the_nearer_narrowed_grant_decides():
    d, proj, v = _nested("nearest")
    r = d(BeingIntent("memory_write", {"path": os.path.join(proj, "sub", "n.md"), "content": "x"}), v)
    assert not r.ok and "nearest grant covering" in (r.error or "") and "#1386" in r.error, r
    assert not os.path.exists(os.path.join(proj, "sub", "n.md"))
    r = d(BeingIntent("memory_read", {"path": os.path.join(proj, "sub", "t.md")}), v)
    assert r.ok and "child" in (r.result or ""), r
    r = d(BeingIntent("memory_write", {"path": os.path.join(proj, "other", "n.md"), "content": "x"}), v)
    assert r.ok, r


def test_under_the_nearest_rule_a_write_only_child_cannot_be_read_through_its_parent():
    d, proj, v = _nested("nearest", child_modes="w", parent_modes="r")
    r = d(BeingIntent("memory_read", {"path": os.path.join(proj, "sub", "t.md")}), v)
    assert not r.ok or "child" not in (r.result or ""), r
    assert "narrowed to w" in (r.error or r.result or ""), r


def test_the_rule_comes_from_the_core_the_verdict_was_judged_with():
    from sage.gateway.being_gate_client import BeingGateClient
    c = BeingGateClient.__new__(BeingGateClient)
    c._core = SimpleNamespace()
    assert c._reach_rule() == "union"
    c._core = SimpleNamespace(nearest_grant_modes=lambda *a, **k: None)
    assert c._reach_rule() == "nearest"


def test_run_mounts_keep_a_stricter_child_and_mask_an_unreadable_one_under_the_nearest_rule():
    from sage.gateway.being_gate_client import run_grant_mounts
    ws = os.path.realpath(tempfile.mkdtemp(prefix="near-mnt-"))
    home, proj = os.path.join(ws, "home"), os.path.join(ws, "proj")
    for dd in (home, os.path.join(proj, "ro"), os.path.join(proj, "hidden")):
        os.makedirs(dd)
    reach = ((proj, True, "rwed"), (os.path.join(proj, "ro"), True, "r"),
             (os.path.join(proj, "hidden"), True, "w"))
    union, _s, _m = run_grant_mounts({"memory_root": home, "granted_reach": reach})
    assert union == [(proj, "dir", "rw")], union
    near, _s, _m = run_grant_mounts({"memory_root": home, "granted_reach": reach,
                                     "reach_rule": "nearest"})
    assert (proj, "dir", "rw") in near and (os.path.join(proj, "ro"), "dir", "ro") in near, near
    assert (os.path.join(proj, "hidden"), "mask", "ro") in near, near
    assert near.index((proj, "dir", "rw")) < near.index((os.path.join(proj, "ro"), "dir", "ro")), \
        "a child's bind must come after its parent's, or the parent's bind hides it"


# -- the read-only floor reaches the dispatcher (dp, 2026-10-25: forum on the floor, modes rw) ----

def _core_with_modes():
    def _roots(entries, ws):
        out = []
        for e in entries:
            if isinstance(e, str) and e.startswith("path:"):
                raw = e[len("path:"):]
                rec = raw.endswith("/**")
                out.append((raw[:-3] if rec else raw, rec))
        return tuple(out)

    def _with_modes(policy, ws):
        return tuple((r, rec, "rwed") for r, rec in _roots(policy.scope, ws))
    return SimpleNamespace(scope_roots_with_modes=_with_modes, _scope_roots_with_reach=_roots,
                           _scope_parts=lambda s, w: ((), ()))


def test_a_read_only_floor_entry_is_reach_for_reading_and_never_for_writing():
    ws = os.path.realpath(tempfile.mkdtemp(prefix="floor-ws-"))
    home, forum = os.path.join(ws, "home"), os.path.join(ws, "shared-context", "forum")
    os.makedirs(home)
    os.makedirs(forum)
    open(os.path.join(forum, "note.md"), "w").write("from sprout\n")
    policy = SimpleNamespace(scope=(), read_scope=(f"path:{forum}/**",))
    reach = _granted_reach(_core_with_modes(), policy, ws)
    assert (forum, True, "r") in reach, reach
    d = ReferenceF1aDispatcher(memory_root=home)
    v = GatewayVerdict("allow", granted=tuple(r for r, *_ in reach), granted_reach=reach)
    r = d(BeingIntent("memory_read", {"path": os.path.join(forum, "note.md")}), v)
    assert r.ok and "from sprout" in (r.result or ""), r
    r = d(BeingIntent("memory_write", {"path": os.path.join(forum, "x.md"), "content": "x"}), v)
    assert not r.ok and not os.path.exists(os.path.join(forum, "x.md")), r


def test_the_floor_steps_aside_where_an_own_grant_reaches():
    ws = os.path.realpath(tempfile.mkdtemp(prefix="floor-ws-"))
    sc = os.path.join(ws, "shared-context")
    forum = os.path.join(sc, "forum")
    os.makedirs(forum)
    policy = SimpleNamespace(scope=(f"path:{sc}/**",), read_scope=(f"path:{forum}/**",))
    reach = _granted_reach(_core_with_modes(), policy, ws)
    assert (sc, True, "rwed") in reach and not [x for x in reach if x[0] == forum], reach


def test_an_older_core_adds_no_floor_it_could_only_express_as_all_modes():
    ws = os.path.realpath(tempfile.mkdtemp(prefix="floor-ws-"))
    forum = os.path.join(ws, "forum")
    core = SimpleNamespace(_scope_roots_with_reach=lambda e, w: (), _scope_parts=lambda s, w: ((), ()))
    policy = SimpleNamespace(scope=(), read_scope=(f"path:{forum}/**",))
    assert _granted_reach(core, policy, ws) == ()


def _floor_world():
    ws = os.path.realpath(tempfile.mkdtemp(prefix="floor-ws-"))
    home, forum = os.path.join(ws, "home"), os.path.join(ws, "shared-context", "forum")
    os.makedirs(home)
    os.makedirs(forum)
    open(os.path.join(forum, "note.md"), "w").write("from sprout\n")
    return ws, home, forum


def _dispatch_read_and_write(home, forum, reach):
    d = _as_worktree(ReferenceF1aDispatcher(memory_root=home), forum)
    v = GatewayVerdict("allow", granted=tuple(r for r, *_ in reach), granted_reach=reach)
    read = d(BeingIntent("memory_read", {"path": os.path.join(forum, "note.md")}), v)
    write = d(BeingIntent("memory_write", {"path": os.path.join(forum, "x.md"), "content": "x"}), v)
    return read, write


def test_an_exact_own_grant_never_suppresses_a_recursive_floor_beneath_it():
    """nomad's counterexample (Nova HOLD on #533): an EXACT own grant on /f does not reach /f/child,
    so it must not drop a RECURSIVE read floor on /f/** -- the gate admits that read."""
    ws, home, forum = _floor_world()
    policy = SimpleNamespace(scope=(f"path:{forum}",), read_scope=(f"path:{forum}/**",))
    reach = _granted_reach(_core_with_modes(), policy, ws)
    assert (forum, True, "r") in reach, reach
    read, write = _dispatch_read_and_write(home, forum, reach)
    assert read.ok and "from sprout" in (read.result or ""), read
    assert not write.ok and not os.path.exists(os.path.join(forum, "x.md")), write


def test_a_recursive_own_grant_covers_the_floor_and_decides_there():
    ws, home, forum = _floor_world()
    sc = os.path.dirname(forum)
    policy = SimpleNamespace(scope=(f"path:{sc}/**",), read_scope=(f"path:{forum}/**",))
    reach = _granted_reach(_core_with_modes(), policy, ws)
    assert not [x for x in reach if x[0] == forum], f"the own grant covers the floor's subtree: {reach}"
    read, write = _dispatch_read_and_write(home, forum, reach)
    assert read.ok and write.ok, (read, write)


def test_an_exact_own_grant_suppresses_only_an_exact_floor_on_the_same_path():
    ws, home, forum = _floor_world()
    policy = SimpleNamespace(scope=(f"path:{forum}",), read_scope=(f"path:{forum}",))
    reach = _granted_reach(_core_with_modes(), policy, ws)
    assert not [x for x in reach if x[0] == forum and len(x) > 2 and x[2] == "r"], reach
