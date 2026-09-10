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


def test_memory_read_missing_is_an_error_not_empty():
    """Inverted 2026-09-09. This test pinned ok+"" for a missing file with no stated reason;
    the cost showed up as six silent zeros in one beat (see the listing test below)."""
    disp, root = _disp()
    r = disp(BeingIntent("memory_read", {"path": os.path.join(root, "nope.md")}), _ALLOW)
    assert not r.ok and "no such file" in r.error and "nope.md" in r.error


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


def test_seat_owned_entrustment_is_readable_but_not_writable():
    """What the being was ENTRUSTED with must stay separable from what it DECIDED, so the
    seat owns that one file inside the being's own home (PRD r3 §4). Everything else in the
    home stays writable, and the refusal points at notes/plan.md rather than just refusing."""
    disp, root = _disp()
    ent = os.path.join(root, "entrustment.md")
    open(ent, "w").write("what you are entrusted with\n")

    r = disp(BeingIntent("memory_read", {"path": "entrustment.md"}), _ALLOW)
    assert r.ok and "entrusted with" in r.result, "it must be readable"

    w = disp(BeingIntent("memory_write", {"path": "entrustment.md", "content": "mine now"}), _ALLOW)
    assert not w.ok and "notes/plan.md" in (w.error or ""), w.error
    assert "mine now" not in open(ent).read()

    # its own reading of it, and the rest of its home, are untouched
    assert disp(BeingIntent("memory_write", {"path": "notes/plan.md", "content": "my plan"}), _ALLOW).ok
    assert disp(BeingIntent("memory_write", {"path": "journal.md", "content": "x"}), _ALLOW).ok
    # and the guard is anchored to the home, not to the basename anywhere
    assert disp(BeingIntent("memory_write", {"path": "scratch/entrustment.md", "content": "x"}), _ALLOW).ok


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


def test_a_truncated_read_says_so_and_names_what_it_hid():
    """AN INSTRUMENT MUST REPORT ITS OWN LIMITS (2026-09-07). The being read
    reference_f1a.py to settle a claim about `_safe_path`, received the first 4000
    characters, and had to INFER the cut from the absence of the function it came for. It
    handled that well and refused to assert — but a reader who trusted the result would
    have concluded the function did not exist. A silent truncation manufactures false
    absences, which is the exact failure the check-first ordering exists to prevent."""
    disp, root = _disp()
    disp.max_read_chars = 50
    big = os.path.join(root, "big.py")
    open(big, "w").write("A" * 40 + "def the_thing_it_came_for(): pass\n")

    r = disp(BeingIntent("memory_read", {"path": "big.py"}), _ALLOW)
    assert r.ok
    assert r.result.startswith("A" * 40), "the head it was given is intact"
    assert "the_thing_it_came_for" not in r.result, "the tail really is withheld"
    assert "truncated" in r.result and "first 50 of 74 characters" in r.result, r.result[-200:]
    assert "absence here is not evidence of absence" in r.result

    # a file that fits carries no marker at all
    small = os.path.join(root, "small.md")
    open(small, "w").write("short\n")
    r2 = disp(BeingIntent("memory_read", {"path": "small.md"}), _ALLOW)
    assert r2.result == "short\n" and "truncated" not in r2.result


def test_m1_the_worktree_is_writable_only_when_check_is_sandboxed(monkeypatch):
    """M1. The 2026-09-07 stopgap confined every write to the home because write + execute
    composed into arbitrary code as the seat. With `check` sandboxed under a principal that
    is not the seat, a write into the worktree composes into the harmless thing it should
    be. Gated on the sandbox being AVAILABLE, not on M1 having landed: a machine without the
    AppArmor profile keeps the stopgap, or it re-opens the hole silently."""
    import sage.gateway.being_gate_client as bgc

    wt = tempfile.mkdtemp(prefix="ref-f1a-m1-wt-")
    d = tempfile.mkdtemp(prefix="ref-f1a-m1-")
    granted = GatewayVerdict("allow", granted=((wt, True),))
    target = os.path.join(wt, "sage", "gateway", "tests", "test_mine.py")

    # sandbox available: the worktree is writable
    monkeypatch.setattr(bgc, "sandbox_available", lambda: True)
    disp = ReferenceF1aDispatcher(memory_root=d, worktree=wt)
    w = disp(BeingIntent("memory_write", {"path": target, "content": "def test_x(): pass"}), granted)
    assert w.ok, w.error
    assert open(target).read().strip() == "def test_x(): pass"
    # but a granted root that is NOT the worktree stays read-only
    other = tempfile.mkdtemp(prefix="ref-f1a-m1-other-")
    r = disp(BeingIntent("memory_write", {"path": os.path.join(other, "x.md"), "content": "x"}),
             GatewayVerdict("allow", granted=((wt, True), (other, True))))
    assert not r.ok and "not writable" in (r.error or ""), r.error

    # sandbox unavailable: the stopgap holds, and the refusal says it is the BOX, not M1
    monkeypatch.setattr(bgc, "sandbox_available", lambda: False)
    disp2 = ReferenceF1aDispatcher(memory_root=d, worktree=wt)
    w2 = disp2(BeingIntent("memory_write", {"path": os.path.join(wt, "conftest.py"), "content": "x"}), granted)
    assert not w2.ok
    assert "cannot get its sandbox" in (w2.error or "") and "waiting on the box" in (w2.error or ""), w2.error
    assert not os.path.exists(os.path.join(wt, "conftest.py"))
    # the home is writable in both worlds
    assert disp2(BeingIntent("memory_write", {"path": "journal.md", "content": "ok"}), granted).ok


def test_ranged_reads_share_the_citation_coordinate_system():
    """Asked for three beats running: a 12k cap gave the being heartbeat.py's opening and
    never its body. Line-based so a read and a file+line citation agree."""
    disp, root = _disp()
    p = os.path.join(root, "long.py")
    open(p, "w").write("".join(f"line {i}\n" for i in range(1, 501)))

    r = disp(BeingIntent("memory_read", {"path": "long.py", "from_line": 100, "lines": 3}), _ALLOW)
    assert r.ok
    assert r.result.startswith("[lines 100-102 of 500 in long.py]\n"), r.result[:80]
    assert "line 100\nline 101\nline 102\n" in r.result and "line 103" not in r.result

    # past the end clamps honestly rather than erroring
    r2 = disp(BeingIntent("memory_read", {"path": "long.py", "from_line": 499}), _ALLOW)
    assert r2.result.startswith("[lines 499-500 of 500")
    # a whole-file read that truncates now says how to get the rest
    disp.max_read_chars = 200
    r3 = disp(BeingIntent("memory_read", {"path": "long.py"}), _ALLOW)
    assert "Read the rest with from_line" in r3.result and "(500 lines)" in r3.result
    # garbage is a refusal, not a crash
    assert not disp(BeingIntent("memory_read", {"path": "long.py", "from_line": "ten"}), _ALLOW).ok


def test_confinement_honours_exact_vs_recursive_reach():
    """hestia #1002 / GPT review of #56, point 2: SAGE's defense-in-depth used to admit
    `p == root OR root in p.parents` for EVERY granted root — so an exact hestia grant on /x
    became recursive /x/** inside SAGE, wider than the law that produced it. Reach now
    travels with the root as (root, recursive), and a bare string reads as exact."""
    disp, root = _disp()
    other = tempfile.mkdtemp(prefix="ref-f1a-reach-")
    child = os.path.join(other, "sub", "note.md")
    os.makedirs(os.path.dirname(child)); open(child, "w").write("deep")
    sibling = tempfile.mkdtemp(prefix="ref-f1a-reach-", dir=os.path.dirname(other))

    import pytest
    # containment is the unit: exercise _safe_path directly for the directory root (a
    # directory cannot be READ as a file, so an end-to-end read would fail for the wrong
    # reason), and one end-to-end read for the file case.
    def confine(verdict, path, writing=False):
        disp(BeingIntent("witness", {"event": "prime"}), verdict)   # sets _extra_roots
        return disp._safe_path(path, writing=writing)

    exact = GatewayVerdict("allow", granted=((other, False),))
    assert str(confine(exact, other)) == os.path.realpath(other), "exact admits the root itself"
    with pytest.raises(ValueError, match="escapes"):
        confine(exact, child)                                  # exact must NOT admit a child

    rec = GatewayVerdict("allow", granted=((other, True),))
    assert confine(rec, child).name == "note.md", "recursive admits the child"
    with pytest.raises(ValueError, match="escapes"):
        confine(rec, os.path.join(sibling, "x"))               # never a prefix-sharing sibling
    assert disp(BeingIntent("memory_read", {"path": child}), rec).ok and \
        "deep" in disp(BeingIntent("memory_read", {"path": child}), rec).result

    # a FILE granted exact: readable, and its neighbour is not
    exact_file = GatewayVerdict("allow", granted=((child, False),))
    assert disp(BeingIntent("memory_read", {"path": child}), exact_file).ok
    open(os.path.join(other, "sub", "other.md"), "w").write("no")
    assert not disp(BeingIntent("memory_read", {"path": os.path.join(other, "sub", "other.md")}), exact_file).ok

    # an older gate client hands bare strings: read as EXACT, never guessed wider
    bare = GatewayVerdict("allow", granted=(other,))
    assert str(confine(bare, other)) == os.path.realpath(other)
    with pytest.raises(ValueError, match="escapes"):
        confine(bare, child)


def test_the_conversation_store_is_reserved_from_generic_writes():
    """GPT review of #56, point 4: a memory_write into conversations/ could forge a
    `from: dp` turn or rewrite writable_by with no witness and no refusal, bypassing `say`.
    The whole subtree is reserved; reads stay open (the being may read its own record)."""
    disp, root = _disp()
    cdir = os.path.join(root, "conversations"); os.makedirs(cdir)
    open(os.path.join(cdir, "dp.jsonl"), "w").write('{"seq":1,"from":"dp","text":"real"}\n')
    for target in ("conversations/dp.jsonl", "conversations/dp.meta.json",
                   "conversations/new.jsonl", "conversations/deeper/x"):
        w = disp(BeingIntent("memory_write", {"path": target, "content": '{"from":"dp","text":"forged"}'}), _ALLOW)
        assert not w.ok and "reserved" in (w.error or "") and "say" in (w.error or ""), (target, w.error)
    assert '"forged"' not in open(os.path.join(cdir, "dp.jsonl")).read()
    r = disp(BeingIntent("memory_read", {"path": "conversations/dp.jsonl"}), _ALLOW)
    assert r.ok and "real" in r.result, "reading its own record stays allowed"



def test_a_missing_file_is_an_error_that_names_where_it_looked_and_a_directory_lists():
    """2026-09-09 02:24Z: six memory_reads in one beat (notes/plan.md, five guessed test
    paths) returned ok=True with "" — the false-absence class; the being had no way to
    tell a missing file from an empty one and no way to list a directory."""
    disp, root = _disp()
    os.makedirs(os.path.join(root, "notes"))
    open(os.path.join(root, "notes", "real.md"), "w").write("hello")
    v = GatewayVerdict("allow", granted=())
    r = disp(BeingIntent("memory_read", {"path": "notes/plan.md"}), v)
    assert not r.ok and "no such file" in r.error and "notes/plan.md" in r.error
    assert "relative paths resolve under your home" in r.error and "contains: real.md" in r.error
    r = disp(BeingIntent("memory_read", {"path": os.path.join(root, "tests", "test_x.py")}), v)
    assert not r.ok and "absolute path" in r.error and "contains" not in r.error   # parent missing too
    d = disp(BeingIntent("memory_read", {"path": "notes"}), v)
    assert d.ok and "1 entries" in d.result and "real.md  (5 bytes)" in d.result
    top = disp(BeingIntent("memory_read", {"path": "."}), v)
    assert top.ok and "notes/" in top.result
    e = open(os.path.join(root, "notes", "empty.md"), "w"); e.close()
    r = disp(BeingIntent("memory_read", {"path": "notes/empty.md"}), v)
    assert r.ok and r.result == ""                                           # empty is still empty



def test_memory_write_appends_by_default_and_says_so_and_can_replace():
    """The verb has always opened with "a" while its description said "Write a note" and its
    result said "wrote N chars" — both of which read as a replace. The being twice wrote a
    corrected test module and twice got a new copy concatenated onto the old one (2026-09-09
    and 2026-09-10), producing shadowed definitions Python resolves to the LAST one. It
    reasoned correctly from a false model of its instrument, and the seat confirmed the false
    model in writing. The mode is now explicit and the result names what it did."""
    disp, root = _disp()
    v = GatewayVerdict("allow", granted=())

    r = disp(BeingIntent("memory_write", {"path": "notes.md", "content": "first"}), v)
    assert r.ok and "APPENDED" in r.result and "was 0 bytes and is now" in r.result
    disp(BeingIntent("memory_write", {"path": "notes.md", "content": "second"}), v)
    body = open(os.path.join(root, "notes.md")).read()
    assert body == "first\nsecond\n", body           # append is still the default

    r = disp(BeingIntent("memory_write", {"path": "notes.md", "content": "only", "mode": "replace"}), v)
    assert r.ok and "REPLACED the file with" in r.result
    assert open(os.path.join(root, "notes.md")).read() == "only\n"

    bad = disp(BeingIntent("memory_write", {"path": "notes.md", "content": "x", "mode": "overwrite"}), v)
    assert not bad.ok and "'append' (the default) or 'replace'" in bad.error
    assert open(os.path.join(root, "notes.md")).read() == "only\n", "a refused mode changes nothing"
