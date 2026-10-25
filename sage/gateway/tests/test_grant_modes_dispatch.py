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


def _world(modes):
    ws = os.path.realpath(tempfile.mkdtemp(prefix="modes-ws-"))
    home = os.path.join(ws, "home")
    forum = os.path.join(ws, "forum")
    os.makedirs(home)
    os.makedirs(forum)
    open(os.path.join(forum, "thread.md"), "w").write("hello\n")
    v = GatewayVerdict("allow", granted=(forum,), granted_reach=((forum, True, modes),))
    return ReferenceF1aDispatcher(memory_root=home), forum, v


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
        d = ReferenceF1aDispatcher(memory_root=home)
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
        d = ReferenceF1aDispatcher(memory_root=home)
        r = d(BeingIntent("memory_write", {"path": os.path.join(forum, "u.md"), "content": "x"}), v)
        assert r.ok, (reach, r)
        r = d(BeingIntent("memory_read", {"path": os.path.join(forum, "u.md")}), v)
        assert r.ok and "x" in r.result, (reach, r)
    # An exact r grant on the root and a recursive w grant on it are different keys.
    v = GatewayVerdict("allow", granted=(forum,), granted_reach=((forum, False, "r"), (forum, True, "w")))
    d = ReferenceF1aDispatcher(memory_root=home)
    r = d(BeingIntent("memory_read", {"path": os.path.join(forum, "u.md")}), v)
    assert not r.ok or "x" not in (r.result or ""), r
