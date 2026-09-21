"""Hermetic tests for the reference F1a dispatcher. Uses a temp dir as the being's
memory root; no gate/model needed. Runnable under pytest or directly."""
import os
import sys
import tempfile
from pathlib import Path

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


def test_memory_read_says_missing_empty_or_directory_never_a_silent_zero():
    """A missing path used to read as "" and was taken for an empty log (cbp-being,
    2026-09-15). Not an error, but never silent: each case names itself."""
    disp, root = _disp()
    r = disp(BeingIntent("memory_read", {"path": os.path.join(root, "nope.md")}), _ALLOW)
    assert r.ok and r.result.startswith("[no such path:") and "not an empty file" in r.result
    open(os.path.join(root, "blank.md"), "w").close()
    r = disp(BeingIntent("memory_read", {"path": os.path.join(root, "blank.md")}), _ALLOW)
    assert r.ok and r.result.startswith("[empty file:")
    os.makedirs(os.path.join(root, "notes"), exist_ok=True)
    open(os.path.join(root, "notes", "a.md"), "w").write("x")
    r = disp(BeingIntent("memory_read", {"path": os.path.join(root, "notes")}), _ALLOW)
    assert r.ok and r.result.startswith("[directory:") and "- a.md" in r.result


def test_path_escape_is_error():
    disp, _ = _disp()
    env = disp(BeingIntent("memory_write", {"path": "/etc/cron.d/x", "content": "x"}), _ALLOW)
    assert not env.ok and "outside your reach" in (env.error or "")
    assert "memory_write creates a file inside your home" in env.error, "a way forward, not just a wall"


def test_memory_edit_changes_the_file_where_memory_write_only_appends():
    """memory_write opens with mode "a", so until 2026-09-21 the being could not alter a byte
    of anything it had written. Measured consequence: notes/mechanism-training-script.py is
    THREE programs concatenated with three __main__ guards — each "rewrite" was an append, so
    only the first ever runs — and twice it reported an edit it had not made, because writing
    a note describing the fix was the only thing it could do."""
    disp, root = _disp()
    home = Path(root)
    w = disp(BeingIntent("memory_write", {"path": "notes/s.py", "content": "x = 1\nprint(x)"}), _ALLOW)
    assert w.ok, w.error
    # the defect, pinned: a second write APPENDS, it does not replace
    disp(BeingIntent("memory_write", {"path": "notes/s.py", "content": "x = 2"}), _ALLOW)
    body = (home / "notes" / "s.py").read_text()
    assert "x = 1" in body and "x = 2" in body, "memory_write is append-only by design"

    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old": "x = 1", "new": "x = 42"}), _ALLOW)
    assert r.ok, r.error
    body = (home / "notes" / "s.py").read_text()
    assert "x = 42" in body and "x = 1" not in body, "the edit did not take: " + body
    assert "not an append" in r.result


def test_memory_edit_survives_a_crash_mid_write_with_the_file_intact():
    """GPT's review of 15c2f6d9b: "the current write_text() mutation is non-atomic;
    crash/kill can truncate the being's work."

    `Path.write_text` truncates and THEN writes, so a kill between the two leaves the file
    empty or half-written — and silently, because the receipt is written after the damage.
    This being spent a week unable to change its own files; destroying one while changing it
    is the worst available regression.

    The falsifier kills the write at the moment the old version would already have truncated
    the target, and asserts the original is byte-identical. Against the pre-fix code the
    target would be empty here."""
    import os as _os
    disp, root = _disp()
    home = Path(root)
    disp(BeingIntent("memory_write", {"path": "notes/s.py", "content": "line one\nline two"}), _ALLOW)
    target = home / "notes" / "s.py"
    original = target.read_bytes()

    real_replace = _os.replace
    def die(src, dst):            # the write landed in tmp; the machine dies before the swap
        raise OSError("simulated crash between write and replace")
    _os.replace = die
    try:
        r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old": "line one", "new": "X"}), _ALLOW)
    finally:
        _os.replace = real_replace

    assert not r.ok, "a failed write must not report success"
    assert "unchanged" in r.error and "Nothing was lost" in r.error, r.error
    assert target.read_bytes() == original, "the being's file was damaged by a failed edit"
    leftovers = [q.name for q in (home / "notes").iterdir() if q.name.endswith(".edit.tmp")]
    assert not leftovers, f"a temp file was left behind: {leftovers}"


def test_memory_edit_refuses_an_ambiguous_or_absent_anchor_and_changes_nothing():
    """A unique anchor is how the being says WHICH line it meant. Replacing the first of
    several would silently edit somewhere it was not looking, and it cannot cheaply re-read
    the file to notice. Both refusals must leave the file byte-identical."""
    disp, root = _disp()
    home = Path(root)
    disp(BeingIntent("memory_write", {"path": "notes/s.py", "content": "a = 1\na = 1\nb = 2"}), _ALLOW)
    before = (home / "notes" / "s.py").read_text()

    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old": "a = 1", "new": "a = 9"}), _ALLOW)
    assert not r.ok and "appears 2 times" in r.error, r.error
    assert (home / "notes" / "s.py").read_text() == before, "an ambiguous edit changed the file"

    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old": "zzz", "new": "q"}), _ALLOW)
    assert not r.ok and "not in" in r.error, r.error
    assert (home / "notes" / "s.py").read_text() == before

    r = disp(BeingIntent("memory_edit", {"path": "notes/gone.py", "old": "a", "new": "b"}), _ALLOW)
    assert not r.ok and "does not exist" in r.error and "not a refusal" in r.error, r.error

    # and it cannot reach outside its home, exactly as memory_write cannot
    r = disp(BeingIntent("memory_edit", {"path": "/etc/hostname", "old": "a", "new": "b"}), _ALLOW)
    assert not r.ok and "outside your reach" in r.error, r.error


def test_an_out_of_reach_path_that_does_not_exist_says_so_rather_than_implying_a_boundary():
    """cbp-being read `/home/dp/ai-workspace/SAGE/126-being.md` — outside its root AND absent —
    and was told only that the path "escapes the being's memory root and its grants". It spent
    two days asking dp what the boundary was protecting (conversation `dp`, seq 68-70). Nothing
    was: the file had never existed. dp, 2026-09-20: "the refusal was because what you were
    trying to reach wasn't there. the system needs to do a better job of explaining this." """
    disp, _ = _disp()
    env = disp(BeingIntent("memory_read", {"path": "/home/dp/ai-workspace/SAGE/126-being.md"}), _ALLOW)
    assert not env.ok
    assert "THERE IS NOTHING AT THAT PATH" in env.error, "absence is the useful fact here"
    assert "not a boundary" in env.error
    assert "Do not ask for a grant on it" in env.error, "a grant cannot conjure a file (legibility 1.11)"


def test_an_out_of_reach_path_that_DOES_exist_is_still_named_a_real_boundary():
    """CONTROL. Without this the fix could be 'call every refusal an absence', which would teach
    the being to discount real boundaries."""
    disp, _ = _disp()
    env = disp(BeingIntent("memory_read", {"path": "/etc/hostname"}), _ALLOW)
    assert not env.ok
    assert "does exist, so this one is a real boundary" in env.error
    assert "request_scope" in env.error, "the way forward for a boundary is to ask"
    assert "NOTHING AT THAT PATH" not in env.error


def test_absence_is_never_claimed_where_it_could_not_be_established():
    """A PermissionError must read as UNKNOWN. `Path.exists()` answers False when it may not
    look, which would print a confident false absence — the failure this guard exists to stop."""
    disp, _ = _disp()
    assert ReferenceF1aDispatcher._existence(Path("/proc/1/root/nonexistent-xyz")) in ("unknown", "absent")
    assert ReferenceF1aDispatcher._existence(Path("/etc/hostname")) == "present"
    assert ReferenceF1aDispatcher._existence(Path("/definitely-not-here-9f3a")) == "absent"


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
        assert not e.ok and "outside your reach" in (e.error or "")
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
    r = disp(BeingIntent("memory_read", {"path": target}), GatewayVerdict("allow", granted=(other,)))
    assert r.ok and "a note from a peer" in r.result
    r = disp(BeingIntent("memory_read", {"path": target}), _ALLOW)
    assert not r.ok and "outside your reach" in (r.error or "")
    # a granted root never widens to its parent or a sibling
    r = disp(BeingIntent("memory_read", {"path": os.path.join(os.path.dirname(other), "x.md")}),
             GatewayVerdict("allow", granted=(other,)))
    assert not r.ok and "outside your reach" in (r.error or "")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


def test_the_conversation_store_is_reserved_from_generic_writes():
    """GPT review of #56, point 4 (ported with the conversations slice): a memory_write into
    conversations/ could forge a `from: dp` turn or rewrite writable_by with no witness and no
    refusal, bypassing `say`. The whole subtree is reserved; reads stay open (the being may
    read its own record)."""
    disp, root = _disp()
    cdir = os.path.join(root, "conversations"); os.makedirs(cdir)
    open(os.path.join(cdir, "dp.jsonl"), "w").write('{"seq":1,"from":"dp","text":"real"}\n')
    for target in ("conversations/dp.jsonl", "conversations/dp.meta.json",
                   "conversations/new.jsonl", "conversations/deeper/x",
                   os.path.join(root, "conversations", "dp.jsonl")):
        w = disp(BeingIntent("memory_write", {"path": target, "content": '{"from":"dp","text":"forged"}'}), _ALLOW)
        assert not w.ok and "reserved" in (w.error or "") and "say" in (w.error or ""), (target, w.error)
    assert '"forged"' not in open(os.path.join(cdir, "dp.jsonl")).read()
    r = disp(BeingIntent("memory_read", {"path": "conversations/dp.jsonl"}), _ALLOW)
    assert r.ok and "real" in r.result, "reading its own record stays allowed"


def test_what_was_said_to_the_being_is_readable_and_not_writable():
    """notes/from-dp.md (the dp console's note channel) and notes/from-the-seat.md are what
    was said TO the being. It reads them every beat; an append would make its words
    indistinguishable from the operator's in the record. Its own notes stay writable."""
    disp, root = _disp()
    os.makedirs(os.path.join(root, "notes"))
    for name in ("from-dp.md", "from-the-seat.md"):
        open(os.path.join(root, "notes", name), "w").write("said to you\n")
        w = disp(BeingIntent("memory_write", {"path": f"notes/{name}", "content": "i said this"}), _ALLOW)
        assert not w.ok and "said TO you" in (w.error or ""), (name, w.error)
        assert open(os.path.join(root, "notes", name)).read() == "said to you\n"
        r = disp(BeingIntent("memory_read", {"path": f"notes/{name}"}), _ALLOW)
        assert r.ok and "said to you" in r.result
    w = disp(BeingIntent("memory_write", {"path": "notes/plan.md", "content": "mine"}), _ALLOW)
    assert w.ok, w.error


def test_the_ask_record_is_reserved_so_a_being_cannot_reset_its_own_limit():
    """asks_sent.jsonl is what the ask limit counts (SAGE #92); writing it is refused, reading it is not."""
    disp, root = _disp()
    open(os.path.join(root, "asks_sent.jsonl"), "w").write('{"t": 1, "peer": "hub"}\n')
    w = disp(BeingIntent("memory_write", {"path": "asks_sent.jsonl", "content": ""}), _ALLOW)
    assert not w.ok and "reserved" in (w.error or ""), w.error
    r = disp(BeingIntent("memory_read", {"path": "asks_sent.jsonl"}), _ALLOW)
    assert r.ok and "hub" in r.result
