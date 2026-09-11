"""Hermetic tests for the reference F1a dispatcher. Uses a temp dir as the being's
memory root; no gate/model needed. Runnable under pytest or directly."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict  # noqa: E402
from sage.gateway.reference_f1a import ReferenceF1aDispatcher  # noqa: E402

_ALLOW = GatewayVerdict("allow")


def _disp():
    d = tempfile.mkdtemp(prefix="ref-f1a-")
    return ReferenceF1aDispatcher(memory_root=d), d


def test_witness_returns_id_and_logs():
    disp, root = _disp()
    env = disp(BeingIntent("witness", {"event": "I noticed the light change"}), _ALLOW)
    assert env.ok and env.witness_id and len(env.witness_id) == 12
    log = os.path.join(root, "witness_log.jsonl")
    assert os.path.exists(log) and "light change" in open(log).read()


def test_memory_write_then_read_roundtrips():
    disp, root = _disp()
    note = os.path.join(root, "notes.md")
    w = disp(BeingIntent("memory_write", {"path": note, "content": "a promise to myself"}), _ALLOW)
    assert w.ok and w.witness_id
    r = disp(BeingIntent("memory_read", {"path": note}), _ALLOW)
    assert r.ok and "a promise to myself" in r.result


def test_memory_read_missing_is_empty_not_error():
    disp, root = _disp()
    r = disp(BeingIntent("memory_read", {"path": os.path.join(root, "nope.md")}), _ALLOW)
    assert r.ok and r.result == ""


def test_path_escape_is_error():
    disp, _ = _disp()
    env = disp(BeingIntent("memory_write", {"path": "/etc/cron.d/x", "content": "x"}), _ALLOW)
    assert not env.ok and "escapes" in (env.error or "")


def test_network_act_deferred_to_f1a():
    disp, _ = _disp()
    env = disp(BeingIntent("peer_ask", {"to": "legion", "body": "hi"}), _ALLOW)
    assert not env.ok and env.pending and "awaits hestia F1a" in env.note


def test_empty_witness_event_rejected():
    disp, _ = _disp()
    env = disp(BeingIntent("witness", {"event": "  "}), _ALLOW)
    assert not env.ok and "event" in (env.error or "")


def test_injected_witness_fn_is_used():
    d = tempfile.mkdtemp(prefix="ref-f1a-")
    disp = ReferenceF1aDispatcher(memory_root=d, witness_fn=lambda e: "hestia-w-42")
    env = disp(BeingIntent("witness", {"event": "x"}), _ALLOW)
    assert env.ok and env.witness_id == "hestia-w-42"




def test_relative_memory_path_roots_at_memory_root_not_cwd():
    """A being names its notes relative to its own memory ("notes/x.md"). That must
    land under memory_root regardless of the process cwd (2026-09-03, Legion: the
    first governed turn on legion resolved "notes/first-governed-turn.md" against
    the repo root, so the being could never reach its own memory by name)."""
    disp, root = _disp()
    cwd = os.getcwd()
    other = tempfile.mkdtemp(prefix="ref-f1a-cwd-")
    os.chdir(other)
    try:
        w = disp(BeingIntent("memory_write", {"path": "notes/x.md", "content": "rooted"}), _ALLOW)
        assert w.ok, w.error
        assert os.path.exists(os.path.join(root, "notes", "x.md"))
        assert not os.path.exists(os.path.join(other, "notes", "x.md"))
        r = disp(BeingIntent("memory_read", {"path": "notes/x.md"}), _ALLOW)
        assert r.ok and "rooted" in r.result
        # a relative path cannot climb out of the root either
        e = disp(BeingIntent("memory_write", {"path": "../../escape.md", "content": "x"}), _ALLOW)
        assert not e.ok and "escapes" in (e.error or "")
    finally:
        os.chdir(cwd)

def test_confinement_follows_the_verdicts_granted_roots():
    """A path outside the home is reachable when the verdict names its root as granted
    (Legion 2026-09-05: a forum read grant 'cannot be used at all' when the dispatcher
    confines to the home before the law is consulted); without that root it still escapes."""
    disp, root = _disp()
    other = tempfile.mkdtemp(prefix="ref-f1a-granted-")
    target = os.path.join(other, "forum", "note.md")
    os.makedirs(os.path.dirname(target)); open(target, "w").write("a note from a peer")
    r = disp(BeingIntent("memory_read", {"path": target}), GatewayVerdict("allow", granted=((other, True),)))
    assert r.ok and "a note from a peer" in r.result
    r = disp(BeingIntent("memory_read", {"path": target}), _ALLOW)
    assert not r.ok and "escapes" in (r.error or "")
    # a granted root never widens to its parent or a sibling
    r = disp(BeingIntent("memory_read", {"path": os.path.join(os.path.dirname(other), "x.md")}),
             GatewayVerdict("allow", granted=((other, True),)))
    assert not r.ok and "escapes" in (r.error or "")


def test_a_granted_root_is_readable_but_never_writable():
    """THE TREE `check` EXECUTES IS NOT A TREE THE BEING CAN WRITE (2026-09-07).

    Measured live: with a standing grant on its worktree, the being could memory_write
    `<worktree>/conftest.py` — which pytest imports from the rootdir `check` runs against.
    A gated write plus a gated execute compose into ungated arbitrary code as the seat's
    user. Nothing malfunctioned; two correct grants were enough. Reads still follow the
    law; writes stay home.
    """
    disp, root = _disp()
    other = tempfile.mkdtemp(prefix="ref-f1a-worktree-")
    conftest = os.path.join(other, "conftest.py")
    open(conftest, "w").write("# a tree check would execute\n")
    granted = GatewayVerdict("allow", granted=((other, True),))

    r = disp(BeingIntent("memory_read", {"path": conftest}), granted)
    assert r.ok and "check would execute" in r.result, "a granted root must stay readable"

    w = disp(BeingIntent("memory_write", {"path": conftest, "content": "import os"}), granted)
    assert not w.ok, "a granted root must NOT be writable"
    assert "writes stay inside your own home" in (w.error or ""), w.error
    assert "import os" not in open(conftest).read(), "the write must not have landed"

    # the being's own home is unaffected
    ok = disp(BeingIntent("memory_write", {"path": "journal.md", "content": "mine"}), granted)
    assert ok.ok, ok.error


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


def test_confinement_honours_exact_vs_recursive_reach():
    """hestia #1002: SAGE's defense-in-depth used to admit `p == root OR root in p.parents`
    for EVERY granted root — an exact hestia grant on /x became recursive /x/** inside SAGE,
    wider than the law that produced it. Reach travels with the root as (root, recursive);
    a bare string reads as exact."""
    import pytest
    disp, root = _disp()
    other = tempfile.mkdtemp(prefix="ref-f1a-reach-")
    child = os.path.join(other, "sub", "note.md")
    os.makedirs(os.path.dirname(child)); open(child, "w").write("deep")
    sibling = tempfile.mkdtemp(prefix="ref-f1a-reach-", dir=os.path.dirname(other))

    def confine(verdict, path):
        disp(BeingIntent("witness", {"event": "prime"}), verdict)
        return disp._safe_path(path)

    exact = GatewayVerdict("allow", granted=((other, False),))
    assert str(confine(exact, other)) == os.path.realpath(other)
    with pytest.raises(ValueError, match="escapes"):
        confine(exact, child)
    rec = GatewayVerdict("allow", granted=((other, True),))
    assert confine(rec, child).name == "note.md"
    with pytest.raises(ValueError, match="escapes"):
        confine(rec, os.path.join(sibling, "x"))
    assert "deep" in disp(BeingIntent("memory_read", {"path": child}), rec).result
    bare = GatewayVerdict("allow", granted=(other,))
    with pytest.raises(ValueError, match="escapes"):
        confine(bare, child)
