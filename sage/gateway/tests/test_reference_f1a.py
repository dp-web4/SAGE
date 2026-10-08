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


def test_a_miss_one_directory_away_names_where_the_file_is():
    """cbp-being, 2026-09-21: read `mechanism-training-script.py` from its root, was told it
    did not exist while it sat in notes/, and wrote a "verified" note about it. 28 of 76 of
    its misses were this shape. The answer must point at the file, and a true absence must
    still read as one."""
    disp, root = _disp()
    os.makedirs(os.path.join(root, "notes"), exist_ok=True)
    open(os.path.join(root, "notes", "script.py"), "w").write("print(1)")
    r = disp(BeingIntent("memory_read", {"path": "script.py"}), _ALLOW)
    assert r.ok and r.result.startswith("[no such path:")
    assert "'notes/script.py'" in r.result and "Nothing was read" in r.result
    open(os.path.join(root, "top.md"), "w").write("x")
    r = disp(BeingIntent("memory_read", {"path": "notes/top.md"}), _ALLOW)
    assert "'top.md'" in r.result, "the reverse direction: notes/ asked, root holds it"
    r = disp(BeingIntent("memory_read", {"path": "never.md"}), _ALLOW)
    assert "not an empty file" in r.result and "DOES exist" not in r.result


def test_a_miss_with_several_same_named_files_lists_them_all_and_prefers_none():
    """GPT review on #140: with notes/script.py AND scratch/script.py, the old answer listed
    both and then called the first in sort order the one the being "probably meant". Nothing
    supports that ranking, and this repair exists to stop invention after a miss. Every match
    is named the same way, none is preferred, and a count beyond the shown ones is stated."""
    disp, root = _disp()
    for d in ("notes", "scratch"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
        open(os.path.join(root, d, "script.py"), "w").write("print(1)")
    r = disp(BeingIntent("memory_read", {"path": "script.py"}), _ALLOW)
    assert r.ok and r.result.startswith("[no such path:"), r.result
    assert "'notes/script.py'" in r.result and "'scratch/script.py'" in r.result, r.result
    assert "2 files with that name" in r.result, r.result
    assert "probably" not in r.result and "meant that one" not in r.result, r.result
    # no command pre-filled for either one: that would be the same preference by other means
    assert '"path": "notes/script.py"' not in r.result, r.result
    assert "Nothing was read" in r.result
    # more than the shown cap: the rest are counted, not dropped
    for d in ("a1", "a2", "a3", "a4", "a5"):
        os.makedirs(os.path.join(root, d), exist_ok=True)
        open(os.path.join(root, d, "script.py"), "w").write("x")
    r = disp(BeingIntent("memory_read", {"path": "script.py"}), _ALLOW)
    assert "7 files with that name" in r.result and "and 2 more" in r.result, r.result


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
    # ...and it names where the copies are and the start_line door, which must then work
    assert "lines 1, 2" in r.error and "start_line" in r.error, r.error
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old": "a = 1", "new": "a = 9",
                                         "start_line": 2}), _ALLOW)
    assert r.ok, r.error
    assert (home / "notes" / "s.py").read_text() == before.replace("a = 1\na = 1", "a = 1\na = 9")
    (home / "notes" / "s.py").write_text(before)

    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old": "zzz", "new": "q"}), _ALLOW)
    assert not r.ok and "not in" in r.error, r.error
    assert (home / "notes" / "s.py").read_text() == before

    r = disp(BeingIntent("memory_edit", {"path": "notes/gone.py", "old": "a", "new": "b"}), _ALLOW)
    assert not r.ok and "does not exist" in r.error and "not a refusal" in r.error, r.error

    # and it cannot reach outside its home, exactly as memory_write cannot
    r = disp(BeingIntent("memory_edit", {"path": "/etc/hostname", "old": "a", "new": "b"}), _ALLOW)
    assert not r.ok and "outside your reach" in r.error, r.error


def test_a_long_read_names_its_window_and_the_start_line_that_reads_on():
    """Measured 2026-09-21: a 45,318-char script came back as its first 4,000 characters,
    cut mid-line, with no marker (legion's 2026-09-07 fix never reached main). The being was
    told three times to fix line 206 — never shown to it. A window must say what it hid, and
    the start_line it names must reach the rest, whole lines, all of it, nothing twice."""
    disp, root = _disp()
    body = "".join(f"line {i:04d} " + "x" * 90 + "\n" for i in range(1, 401))   # ~40k chars
    Path(root, "notes").mkdir(exist_ok=True)
    Path(root, "notes", "big.py").write_text(body)
    r = disp(BeingIntent("memory_read", {"path": "notes/big.py"}), _ALLOW)
    assert r.ok and "truncated" in r.result and "of 400" in r.result, r.result[-300:]
    assert "absence here is not evidence of absence" in r.result
    seen, start = [], 1
    for _ in range(20):
        r = disp(BeingIntent("memory_read", {"path": "notes/big.py", "start_line": str(start)}), _ALLOW)
        seen += [l for l in r.result.splitlines() if l.startswith("line ")]
        if "end of file" in r.result:
            break
        start = int(r.result.rsplit("start_line=", 1)[1].split(".")[0])
    assert seen == [f"line {i:04d} " + "x" * 90 for i in range(1, 401)], "windows skipped or repeated lines"
    # line 206 is reachable and arrives whole, so an anchor copied from it is a real line
    r = disp(BeingIntent("memory_read", {"path": "notes/big.py", "start_line": 206}), _ALLOW)
    assert r.result.startswith("[lines 206-") and "\nline 0206 " + "x" * 90 + "\n" in r.result
    # a file that fits carries no marker at all
    Path(root, "notes", "small.md").write_text("a = 1\n")
    assert disp(BeingIntent("memory_read", {"path": "notes/small.md"}), _ALLOW).result == "a = 1\n"
    r = disp(BeingIntent("memory_read", {"path": "notes/small.md", "start_line": 9}), _ALLOW)
    assert r.ok and r.result.startswith("[past the end:")


def test_memory_edit_accepts_the_names_other_edit_tools_use():
    """cbp-being's first live memory_edit (2026-09-21) sent old_text/new_text, was refused,
    read the refusal as "I forgot 'new'", and appended a fourth program with memory_write."""
    disp, root = _disp()
    disp(BeingIntent("memory_write", {"path": "notes/s.py", "content": "x = 1"}), _ALLOW)
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old_text": "x = 1", "new_text": "x = 2"}), _ALLOW)
    assert r.ok, r.error
    assert Path(root, "notes", "s.py").read_text().strip() == "x = 2"
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "before": "x = 2"}), _ALLOW)
    assert not r.ok and "You sent: before, path" in r.error, r.error


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
    # A file that EXISTS outside the home, made here: /etc/hostname was the fixture, and inside
    # the being's sandboxed `check` /etc is not mounted, so it read as absent and this failed on
    # every check the being ran (legion-being, 2026-09-29).
    outside = Path(tempfile.mkdtemp(prefix="ref-f1a-outside-")) / "exists.txt"
    outside.write_text("x")
    env = disp(BeingIntent("memory_read", {"path": str(outside)}), _ALLOW)
    assert not env.ok
    assert "does exist, so this one is a real boundary" in env.error
    assert "request_scope" in env.error, "the way forward for a boundary is to ask"
    assert "NOTHING AT THAT PATH" not in env.error


def test_absence_is_never_claimed_where_it_could_not_be_established():
    """A PermissionError must read as UNKNOWN. `Path.exists()` answers False when it may not
    look, which would print a confident false absence — the failure this guard exists to stop."""
    disp, _ = _disp()
    assert ReferenceF1aDispatcher._existence(Path("/proc/1/root/nonexistent-xyz")) in ("unknown", "absent")
    present = Path(tempfile.mkdtemp(prefix="ref-f1a-present-")) / "here.txt"
    present.write_text("x")                     # not /etc/hostname: /etc is absent in the sandbox
    assert ReferenceF1aDispatcher._existence(present) == "present"
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


def test_a_second_write_says_it_appended_and_the_way_to_start_fresh_works():
    """Measured 2026-09-21: cbp-being rewrote notes/mechanism-training-script.py whole three
    times, read "wrote N chars" as "replaced", and the file became three programs with three
    __main__ guards — only the first ever runs. A receipt must say APPENDED when it appended,
    and the remedy it names (retire_note, then write) must actually yield one clean file."""
    disp, root = _disp()
    path = "notes/script.py"
    first = disp(BeingIntent("memory_write", {"path": path, "content": "print('v1')"}), _ALLOW)
    assert first.ok and first.result.startswith("created script.py"), first.result
    second = disp(BeingIntent("memory_write", {"path": path, "content": "print('v2')"}), _ALLOW)
    assert second.ok and "appended" in second.result and "below the 1 lines" in second.result
    assert "never replaces" in second.result and "retire_note" in second.result
    assert open(os.path.join(root, path)).read() == "print('v1')\nprint('v2')\n", "still appends"
    # the named remedy, run literally
    ret = disp(BeingIntent("retire_note", {"path": path, "reason": "superseded by v3"}), _ALLOW)
    assert ret.ok, ret.error
    third = disp(BeingIntent("memory_write", {"path": path, "content": "print('v3')"}), _ALLOW)
    assert third.ok and third.result.startswith("created script.py"), third.result
    assert open(os.path.join(root, path)).read() == "print('v3')\n"


def test_appending_to_the_journal_does_not_offer_retire_note():
    """The journal and todo are meant to grow; retire_note refuses them, so suggesting it
    there would hand the being a door that is shut."""
    disp, _ = _disp()
    disp(BeingIntent("memory_write", {"path": "journal.md", "content": "one"}), _ALLOW)
    env = disp(BeingIntent("memory_write", {"path": "journal.md", "content": "two"}), _ALLOW)
    assert env.ok and "appended" in env.result and "retire_note" not in env.result


_PROGRAM = ("import numpy as np\n\n\ndef generate_data(n):\n    return np.zeros(n)\n\n\n"
            "def train(x):\n    return x.sum()\n\n\nif __name__ == \"__main__\":\n"
            "    print(train(generate_data(4)))\n")


def test_appending_a_whole_second_program_names_a_new_name_as_the_way_to_start_fresh():
    """2026-09-24 15:19Z: cbp-being chose "a new file", then wrote the new program twice to the
    old file's name; both copies were appended and retire_note refused the path. Outside notes/
    and scratch/ a fresh name is the only fresh start, so the receipt must name it — and the
    named door must actually create a file."""
    import re
    disp, root = _disp()
    disp(BeingIntent("memory_write", {"path": "train.py", "content": _PROGRAM}), _ALLOW)
    env = disp(BeingIntent("memory_write", {"path": "train.py", "content": _PROGRAM}), _ALLOW)
    assert env.ok and "appended" in env.result and "does not exist yet" in env.result, env.result
    assert "train-new.py" in env.result and "retire_note" not in env.result
    new = disp(BeingIntent("memory_write", {"path": "train-new.py", "content": "a = 3"}), _ALLOW)
    assert new.ok and new.result.startswith("created train-new.py"), new.result


def test_the_fresh_name_hint_never_names_a_file_that_exists():
    """cbp-claude's review of #197 (2026-09-28), bug 1: the hint named train-new.py even when
    that file already existed, so the door it named was another append. Bump until free, the
    rule #240 uses for the refusal."""
    import re
    from pathlib import Path
    disp, root = _disp()
    disp(BeingIntent("memory_write", {"path": "train.py", "content": _PROGRAM}), _ALLOW)
    disp(BeingIntent("memory_write", {"path": "train-new.py", "content": "a = 1"}), _ALLOW)
    disp(BeingIntent("memory_write", {"path": "train-new2.py", "content": "a = 1"}), _ALLOW)
    env = disp(BeingIntent("memory_write", {"path": "train.py", "content": _PROGRAM}), _ALLOW)
    assert env.ok and "does not exist yet" in env.result, env.result
    named = re.search(r"for example (\S+?\.py)", env.result).group(1)
    assert not (Path(root) / named).exists(), (named, env.result)
    assert named == "train-new3.py", env.result


def test_a_program_written_in_parts_gets_no_fresh_name_hint():
    """cbp-claude's review of #197, bug 2: the hint fired on every successful append to a
    top-level .py, including a program legitimately written in parts. A part that adds new
    definitions below the old ones is not a second program and is told nothing about a new file."""
    disp, root = _disp()
    part1 = "import numpy as np\n\n\ndef generate_data(n):\n    return np.zeros(n)\n"
    part2 = "def train(x):\n    return x.sum()\n"
    part3 = "if __name__ == \"__main__\":\n    print(train(generate_data(4)))\n"
    assert disp(BeingIntent("memory_write", {"path": "train.py", "content": part1}), _ALLOW).ok
    for part in (part2, part3):
        env = disp(BeingIntent("memory_write", {"path": "train.py", "content": part}), _ALLOW)
        assert env.ok and "appended" in env.result, env.result
        assert "does not exist yet" not in env.result and "train-new" not in env.result, env.result
    # and a non-program line appended to a script is not a second program either
    env = disp(BeingIntent("memory_write", {"path": "train.py", "content": "a = 2"}), _ALLOW)
    assert env.ok and "does not exist yet" not in env.result, env.result


def test_appending_to_an_existing_empty_file_does_not_say_created():
    """An existing empty file has 0 lines but this write did not create it (GPT review, #141)."""
    disp, root = _disp()
    os.makedirs(os.path.join(root, "notes"), exist_ok=True)
    open(os.path.join(root, "notes", "empty.py"), "w").close()
    env = disp(BeingIntent("memory_write", {"path": "notes/empty.py", "content": "x = 1"}), _ALLOW)
    assert env.ok and env.result.startswith("appended") and "below the 0 lines" in env.result, env.result


def test_the_append_receipt_names_memory_edit_for_a_one_line_change():
    """2026-09-21 05:47Z: a memory_write "fix" of one method landed below line 1206. The
    receipt must name the verb that changes text in place, with the argument names it takes."""
    disp, _ = _disp()
    disp(BeingIntent("memory_write", {"path": "notes/s.py", "content": "a = 1"}), _ALLOW)
    env = disp(BeingIntent("memory_write", {"path": "notes/s.py", "content": "a = 2"}), _ALLOW)
    assert "memory_edit" in env.result and "start_line and end_line" in env.result and "old (copied" in env.result
    # and the named door works with exactly those names
    ed = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old_text": "a = 1", "new_text": "a = 3"}), _ALLOW)
    assert ed.ok, ed.error


def test_a_missed_edit_anchor_says_where_it_stopped_matching():
    """cbp-being 2026-09-21: three refused edits in one beat, all told only "not in the file".
    One matched 8 of its 49 lines; two were the real block written twice. The refusal
    now names the matching span and the first differing line, and still changes nothing."""
    disp, root = _disp()
    f = Path(root) / "notes" / "s.py"
    body = ('    p.add_argument("--lr")\n    p.add_argument(\n        "--epochs", type=int\n'
            '    )\n    p.add_argument(\n        "--synthetic",\n    )')
    disp(BeingIntent("memory_write", {"path": "notes/s.py", "content": body}), _ALLOW)
    before = f.read_text()

    doubled = '    p.add_argument(\n        "--epochs", type=int\n    )\n' * 2
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old_text": doubled.rstrip("\n"),
                                         "new_text": ""}), _ALLOW)
    assert not r.ok and "not in" in r.error, r.error
    assert "first 4 lines of 6 match lines 2-5" in r.error, r.error
    assert "'        \"--synthetic\",'" in r.error, r.error
    assert f.read_text() == before

    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old": '    p.add_argument("--lr ")',
                                         "new": ""}), _ALLOW)
    assert not r.ok and "closest line is line 1" in r.error, r.error

    # Indentation does not pick the line: unindented old text, measured on cbp-being 2026-10-04.
    g = Path(root) / "notes" / "m.py"
    disp(BeingIntent("memory_write", {"path": "notes/m.py", "content":
        "                layers.append(nn.Linear(hidden_dim, input_dim))\n"
        "            layers.append(nn.Linear(prev_dim, hidden_dim))\n"}), _ALLOW)
    r = disp(BeingIntent("memory_edit", {"path": "notes/m.py",
                                         "old": "layers.append(nn.Linear(hidden_dim, hidden_dim))",
                                         "new": "q"}), _ALLOW)
    assert not r.ok and "closest line is line 1: '                layers" in r.error, r.error

    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old": "zzz", "new": "q"}), _ALLOW)
    assert not r.ok and "Not even your first line" in r.error, r.error
    assert f.read_text() == before


def test_memory_edit_by_line_number_deletes_the_lines_it_names():
    """2026-09-21 19:01Z: cbp-being called memory_edit with `old_line: "411"`, by line number,
    the way it reads files and the way every seat answer names a fix. Text mode asked it to
    copy seven indented lines exactly; across three answers it never did. The real case:
    seven stray lines after the last main() made the file unrunnable."""
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    body = "def main():\n    pass\n\nif __name__ == '__main__':\n    main()\n            noise=0.1,\n        )\n    else:\n"
    (home / "notes" / "s.py").write_text(body)
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 6, "end_line": 8, "new": ""}), _ALLOW)
    assert r.ok, r.error
    assert (home / "notes" / "s.py").read_text() == "def main():\n    pass\n\nif __name__ == '__main__':\n    main()\n"
    assert "replaced lines 6-8 (3 lines)" in r.result and "noise=0.1" in r.result, \
        "the receipt must quote what was removed, so the being can see it is the right thing"


def test_memory_edit_accepts_the_measured_old_line_spelling():
    """cbp-being's 2026-09-21 call used old_line: "411". The door should accept the spelling
    we actually observed, not only teach a preferred spelling after the fact."""
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "s.py").write_text("a = 1\nb = 2\nc = 3\n")
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "old_line": "2", "new": "b = 20"}), _ALLOW)
    assert r.ok, r.error
    assert (home / "notes" / "s.py").read_text() == "a = 1\nb = 20\nc = 3\n"


def test_memory_edit_one_line_by_number_keeps_the_line_break():
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "s.py").write_text("a = 1\ny = np.load(labels_path)\nb = 2\n")
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": "2",
                                          "new": "y = np.load(data_path.replace('.npy', '_labels.npy'))"}), _ALLOW)
    assert r.ok, r.error
    assert (home / "notes" / "s.py").read_text() == "a = 1\ny = np.load(data_path.replace('.npy', '_labels.npy'))\nb = 2\n"


def test_a_range_edit_that_drops_the_indent_names_both_space_counts():
    """cbp-being 2026-09-27 06:30Z: start_line 144, the right fix, 4 leading spaces missing.
    The parse note named line 145 and the being overwrote `return X, y, W_TRUE` there.
    The receipt must name the dropped spaces as counts, ahead of the parse note."""
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    f = home / "notes" / "s.py"
    f.write_text("def g(n):\n    y = n + 1\n    return y\n")
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": "2", "end_line": "2",
                                          "content": "y = n + 2"}), _ALLOW)
    assert r.ok, r.error
    assert "Line 2 now starts with 0 spaces; the line it replaced started with 4" in r.result, r.result
    assert r.result.index("started with 4") < r.result.index("IndentationError"), \
        "the count must come before the parse note that names the next line"
    # Same indent: no note.
    f.write_text("def g(n):\n    y = n + 1\n    return y\n")
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 2, "new": "    y = n + 2"}), _ALLOW)
    assert r.ok and "spaces" not in r.result, r.result


def test_memory_edit_by_line_refuses_lines_that_do_not_exist_and_changes_nothing():
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "s.py").write_text("a\nb\n")
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 2, "end_line": 9, "new": ""}), _ALLOW)
    assert not r.ok and "it has 2 lines" in r.error
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": "line 2", "new": ""}), _ALLOW)
    assert not r.ok and "must be line numbers" in r.error
    assert (home / "notes" / "s.py").read_text() == "a\nb\n"


def test_a_range_edit_missed_only_by_indentation_names_the_space_counts():
    """cbp-being 2026-09-24: old without the line's 4 leading spaces, refused twice with the
    line shown, then appended with memory_write instead. The refusal now gives the counts."""
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    f = home / "notes" / "s.py"
    before = "def main():\n    m = M(10)\n    run(m)\n"
    f.write_text(before)
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 2, "end_line": 2,
                                         "old": "m = M(10)", "new": "m = M(50)"}), _ALLOW)
    assert not r.ok
    assert "Line 2 in the file starts with 4 spaces; that line of your old starts with 0" in r.error, r.error
    assert "change nothing" not in r.error
    assert f.read_text() == before
    # multi-line: the count names the first line that differs
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 1, "end_line": 3,
                                         "old": "def main():\n    m = M(10)\nrun(m)", "new": "x"}), _ALLOW)
    assert not r.ok and "Line 3 in the file starts with 4 spaces" in r.error, r.error
    # A real content miss gets no indentation note: the note must not explain a wrong line.
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 3,
                                         "old": "m = M(10)", "new": "m = M(50)"}), _ALLOW)
    assert not r.ok and "spaces at the start" not in r.error
    assert f.read_text() == before
    # 2026-09-27 04:58Z: the same miss with new identical to old would be a no-op even fixed
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 2, "end_line": 2,
                                         "old": "m = M(10)", "new": "m = M(10)"}), _ALLOW)
    assert not r.ok and "Line 2 in the file starts with 4 spaces" in r.error
    assert "would change nothing" in r.error, r.error
    # with the spaces, it lands
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 2,
                                         "old": "    m = M(10)", "new": "    m = M(50)"}), _ALLOW)
    assert r.ok and f.read_text() == "def main():\n    m = M(50)\n    run(m)\n"


def test_memory_edit_with_lines_and_old_is_a_checked_edit():
    """Both given: the lines must BE the old text. A line number read before an earlier edit
    shifted the file points at different lines now; this refuses and shows what is there."""
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "s.py").write_text("a\nb\nc\n")
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 2, "old": "c", "new": "C"}), _ALLOW)
    assert not r.ok and "Those lines are now:\nb" in r.error
    assert (home / "notes" / "s.py").read_text() == "a\nb\nc\n"
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 2, "old": "b", "new": "B"}), _ALLOW)
    assert r.ok and (home / "notes" / "s.py").read_text() == "a\nB\nc\n"


def test_the_offered_schema_no_longer_requires_old():
    from sage.gateway import being_gate_client as bgc
    src = open(bgc.__file__).read()
    i = src.index('"memory_edit": ("Change part')
    block = src[i:i + 1600]
    assert '["path", "new"]' in block and '"start_line"' in block


def test_memory_edit_without_a_replacement_refuses_instead_of_deleting():
    """2026-09-22 02:30Z: cbp-being sent `new_content` to add `.reshape(-1, 1)` to line 336.
    No alias matched, the replacement defaulted to "", and line 336 was deleted under a receipt
    reading "replaced lines 336-336". An absent replacement must refuse; only a present one
    (even empty) may delete."""
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    f = home / "notes" / "s.py"
    f.write_text("a = 1\ny = load()\nb = 2\n")
    for args in ({"start_line": 2, "end_line": 2, "new_line": "y = load().reshape(-1, 1)"},
                 {"old": "y = load()", "with": "y = load().reshape(-1, 1)"}):
        r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", **args}), _ALLOW)
        assert not r.ok and "got no 'new'" in r.error and "nothing was changed" in r.error, r.error
        assert f.read_text() == "a = 1\ny = load()\nb = 2\n"
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": "2", "end_line": "2",
                                          "new_content": "y = load().reshape(-1, 1)"}), _ALLOW)
    assert r.ok, r.error
    assert f.read_text() == "a = 1\ny = load().reshape(-1, 1)\nb = 2\n"


def test_a_py_receipt_says_whether_python_can_parse_the_file_now():
    """2026-09-21: from 18:22 the being's script could not be parsed, and for two hours it
    recorded "runs correctly" and "Applied fix" while every write left it unparseable. The
    receipts never said. Parsing executes nothing; the sentence says it is not a run."""
    disp, root = _disp()
    home = Path(root)
    r = disp(BeingIntent("memory_write", {"path": "notes/s.py", "content": "def main():\n    pass\n"}), _ALLOW)
    assert r.ok and "Python can parse s.py now. That is not the same as running it." in r.result
    # a new file is not gated: its receipt carries the parse error
    r = disp(BeingIntent("memory_write", {"path": "notes/t.py",
                                          "content": "def main():\n            noise=0.1,\n        )"}), _ALLOW)
    assert r.ok and "Python cannot parse t.py now: IndentationError at line 3" in r.result, r.result
    r = disp(BeingIntent("memory_edit", {"path": "notes/t.py", "start_line": 2, "end_line": 3, "new": "    pass"}), _ALLOW)
    assert r.ok and "Python can parse t.py now" in r.result, r.result


LABELS = [  # cbp-being's real appends to mechanism-training-script-clean.py
    "[Fix #1: Removed extra closing parenthesis on line 1685 in argparse.ArgumentParser call]\n",
    "[BEAT 2026-09-23 05:18 UTC] Applying fix #1: removing extra closing parenthesis on line 1685.\n"
    "Line 1685 currently reads:\n    parser = argparse.ArgumentParser(description=\"x\"))\n",
    "[Remove lines 344-347, which are a broken duplicate of the for loop at lines 340-343]",
    "Remove lines 180-184 (orphaned docstring tail and return statement) and insert new label generation code",
]


def test_a_description_of_an_edit_is_refused_before_it_lands_in_a_py_file():
    """2026-09-21..23: 15 memory_write calls appended prose ("[Fix #1: Removed ...]") to the
    being's script where an edit was meant; every receipt said "only adds" and named
    memory_edit, and the being still reported the fixes applied. Refuse before writing."""
    disp, root = _disp()
    f = Path(root) / "s.py"
    f.write_text("def main():\n    pass\n")
    for text in LABELS:
        r = disp(BeingIntent("memory_write", {"path": "s.py", "content": text}), _ALLOW)
        assert not r.ok and "nothing was written to s.py" in r.error, r.error
        assert "memory_edit" in r.error and "journal.md" in r.error and "Python cannot read line 1 of your text as code" in r.error
        assert "Python can parse s.py now" in r.error
        assert f.read_text() == "def main():\n    pass\n"
    # also refused when the file is already broken -- that is where the labels landed
    f.write_text("x = f(1))\n")
    r = disp(BeingIntent("memory_write", {"path": "s.py", "content": LABELS[0]}), _ALLOW)
    assert not r.ok and "Python cannot parse s.py now" in r.error and f.read_text() == "x = f(1))\n"


def test_code_appended_to_a_py_file_still_lands():
    """What must stay open on a healthy file: a whole function, a real comment, and the last part
    of a program written in parts (it makes the file parse). Indented fragments used to be here
    ("dedented it parses"). Appended to a working file they make it INVALID, and the monotonic
    rule refuses that (test_a_healthy_file_is_never_made_invalid_by_an_append)."""
    disp, root = _disp()
    f = Path(root) / "s.py"
    for text in ("def g():\n    return 1\n",
                 "# TODO: tune lr\n"):
        f.write_text("import os\n")
        r = disp(BeingIntent("memory_write", {"path": "s.py", "content": text}), _ALLOW)
        assert r.ok, (text, r.error)
    f.write_text("def h(\n    a,\n")
    r = disp(BeingIntent("memory_write", {"path": "s.py", "content": "    b,\n):\n    return a + b\n"}), _ALLOW)
    assert r.ok and "Python can parse s.py now" in r.result, r.error
    # not .py, and not an existing file: ungated
    for path in ("journal.md", "notes/new.py"):
        r = disp(BeingIntent("memory_write", {"path": path, "content": LABELS[0]}), _ALLOW)
        assert r.ok, (path, r.error)


BROKEN_MID = "import os\nx = f(1))\ndef g():\n    return 1\n"     # stops at line 2, not at the end


def test_an_append_to_a_broken_file_that_leaves_the_error_in_place_is_refused():
    """GPT's review of #186: an append below the first error cannot repair it. The two measured
    forms that the grammar check alone let through, both refused, with the file unchanged:
    - seq 3405 (2026-09-23 07:15): a label written as `#` comments. Comments are Python.
    - 2026-09-24 10:31: VALID Python appended to a file stopped mid-way. The stop did not move."""
    disp, root = _disp()
    f = Path(root) / "s.py"
    for text in ("# Remove stray ']' at line 1736 ...\n# OLD (line 1736): ]\n",
                 "def train(model, X, y):\n    for epoch in range(10):\n        model.step(X, y)\n"):
        f.write_text(BROKEN_MID)
        r = disp(BeingIntent("memory_write", {"path": "s.py", "content": text}), _ALLOW)
        assert not r.ok, (text, r.result)
        assert "stops at line 2" in r.error and "Appending below it cannot fix that" in r.error
        assert "memory_edit" in r.error
        assert f.read_text() == BROKEN_MID, "nothing written"


def test_a_whole_program_refused_on_a_broken_file_names_a_new_name_that_creates_it():
    """2026-09-27 18:52Z: cbp-being wrote one whole clean program three times to a broken file's
    name; each refusal named only memory_edit. A text that is a program by itself is a fresh
    start, so the refusal names a name that does not exist yet, and that door must create it.
    A fragment or a label (not a program alone) gets no such door."""
    disp, root = _disp()
    f = Path(root) / "s.py"
    f.write_text(BROKEN_MID)
    (Path(root) / "s-new.py").write_text("taken = 1\n")
    prog = "import os\n\ndef main():\n    print(os.sep)\n\nif __name__ == '__main__':\n    main()\n"
    r = disp(BeingIntent("memory_write", {"path": "s.py", "content": prog}), _ALLOW)
    assert not r.ok and "whole program by itself" in r.error and "s-new2.py" in r.error, r.error
    assert "s.py itself stays exactly as it is" in r.error and "keep failing" in r.error, r.error
    assert f.read_text() == BROKEN_MID
    new = disp(BeingIntent("memory_write", {"path": "s-new2.py", "content": prog}), _ALLOW)
    assert new.ok and new.result.startswith("created s-new2.py"), new.result
    for frag in ("# fixed line 2\n", "    return 2\n"):
        r = disp(BeingIntent("memory_write", {"path": "s.py", "content": frag}), _ALLOW)
        assert not r.ok and "whole program" not in r.error, r.error


def test_an_append_that_repairs_or_grows_an_unfinished_program_still_lands():
    """What the invariant must keep open on a broken file: the append that makes it parse (the
    last part of a program written in parts), and code that moves an end-of-file stop later
    (an unfinished program still growing). A label that 'moves' that stop is not code, so it is
    still refused."""
    disp, root = _disp()
    f = Path(root) / "s.py"
    f.write_text("def h(\n    a,\n")                                   # stops at the end
    r = disp(BeingIntent("memory_write", {"path": "s.py", "content": "    b,\n):\n    return a + b\n"}), _ALLOW)
    assert r.ok and "Python can parse s.py now" in r.result, r.error
    f.write_text("def h(\n    a,\n")
    r = disp(BeingIntent("memory_write", {"path": "s.py", "content": "    b,\n    c,\n"}), _ALLOW)
    assert r.ok, r.error                                                 # still open, but grew
    f.write_text("def h(\n    a,\n")
    r = disp(BeingIntent("memory_write", {"path": "s.py", "content": "[Fix: closed the call on line 1]\n"}), _ALLOW)
    assert not r.ok and f.read_text() == "def h(\n    a,\n"


def test_a_healthy_file_is_never_made_invalid_by_an_append():
    """GPT's ruling on #186 (2026-09-26): healthy -> healthy. The original rule admitted these
    because each parses on its own once dedented (or as a function body), but appended to a
    working file each makes it INVALID ("unexpected indent", "'return' outside function"). The
    file is left exactly as it was."""
    disp, root = _disp()
    f = Path(root) / "s.py"
    # Ends at module level: a trailing def would make an indented fragment a legitimate
    # continuation of its body (it parses), which the rule correctly allows.
    healthy = "import os\n\nx = 1\n"
    for text in ("        X = np.load(data_path)\n        y = X[:, 0]\n",
                 "    y = X.sum()\n    return X, y\n"):
        f.write_text(healthy)
        r = disp(BeingIntent("memory_write", {"path": "s.py", "content": text}), _ALLOW)
        assert not r.ok, (text, r.result)
        assert "this text would break it" in r.error and "Python would stop at line" in r.error
        assert f.read_text() == healthy, "nothing written"
    # the same fragment continuing a trailing function body keeps the file healthy, and lands
    f.write_text("def g(X):\n    X = X * 2\n")
    r = disp(BeingIntent("memory_write", {"path": "s.py", "content": "    y = X.sum()\n    return X, y\n"}), _ALLOW)
    assert r.ok and "Python can parse s.py now" in r.result, r.error


def test_a_comment_on_a_healthy_file_is_still_a_comment():
    """The control GPT asked for: a real source comment on a file that parses is not a label
    that masks a broken stop, and it lands."""
    disp, root = _disp()
    f = Path(root) / "s.py"
    f.write_text("import os\n\ndef g():\n    return 1\n")
    r = disp(BeingIntent("memory_write", {"path": "s.py", "content": "# returns the batch size\n"}), _ALLOW)
    assert r.ok, r.error


def test_a_non_python_receipt_says_nothing_about_parsing():
    disp, root = _disp()
    r = disp(BeingIntent("memory_write", {"path": "journal.md", "content": "a note"}), _ALLOW)
    assert r.ok and "parse" not in r.result


def test_the_edit_receipt_counts_lines_the_way_memory_read_does():
    """2026-09-21: the receipt said 1637 lines while memory_read said 1636 (count+1 vs
    splitlines, for a file ending in a newline). The being edits by line number now."""
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "s.py").write_text("a = 1\nb = 2\nc = 3\n")
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 3, "end_line": 3, "new": ""}), _ALLOW)
    assert r.ok and "went from 3 to 2 lines" in r.result, r.result
    rd = disp(BeingIntent("memory_read", {"path": "notes/s.py"}), _ALLOW)
    assert rd.ok and (home / "notes" / "s.py").read_text().count("\n") == 2


def test_an_identical_replacement_says_nothing_changed():
    """2026-09-24 10:42 cbp-being replaced line 2686 with the text already on it; the receipt
    said "This changed the file on disk", and its closing note listed 2686 as fixed. Again
    2026-09-28 10:08Z at line 113 of latent-weights-holdout-test-fixed.py, followed by a
    request_run at the unchanged sha (seq 4301)."""
    disp, root = _disp()
    p = Path(root) / "s.py"
    p.write_text("def f():\n    print(1)\n")
    before = os.stat(p).st_mtime_ns
    for args in ({"start_line": "2", "end_line": "2", "new": "    print(1)"},
                 {"old": "    print(1)", "new": "    print(1)"}):
        r = disp(BeingIntent("memory_edit", {"path": "s.py", **args}), _ALLOW)
        assert not r.ok and "changed nothing" in r.error and "not in this edit" in r.error, r
    assert os.stat(p).st_mtime_ns == before


def test_an_edit_aimed_at_a_conversation_is_told_to_name_its_file():
    """Same beat: memory_edit lines 2367-2377 of conversations/cbp-claude.jsonl (the fix was
    for a .py). The refusal named only `say`; the being then said the fix was done."""
    disp, root = _disp()
    os.makedirs(os.path.join(root, "conversations"))
    r = disp(BeingIntent("memory_edit", {"path": "conversations/cbp-claude.jsonl",
                                         "old": "x", "new": "y"}), _ALLOW)
    assert not r.ok and "give that file's path" in r.error and "does not change any file" in r.error, r


def test_a_py_read_says_whether_python_can_parse_the_file_now():
    """2026-09-23: cbp-being read lines 1718-1937 of its script -- line 1721 at column 0, the
    lines under it indented four -- and concluded "syntactically valid"; Python stopped at
    1722. #162 told it on write and edit, never on the read where the verdict was formed.
    Again 2026-09-29 11:41Z: it read all 443 lines of scratch/latent-weights-holdout-test-fixed-v2.py
    in three windows (1-207, 208-427, 428-443), said "appears syntactically correct", and asked
    the seat to run it; the run (seq 4384) stopped at line 135, IndentationError, inside the
    first window it had been shown. A whole-file read has no end marker, so the note is
    prefixed with one: a bare bracket line after the last line reads as the file's last line."""
    disp, root = _disp()
    f = Path(root) / "notes" / "s.py"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("p = 1\n    q = 2\n")
    r = disp(BeingIntent("memory_read", {"path": "notes/s.py"}), _ALLOW)
    assert r.ok and r.result.endswith("\n[end of file: line 2 is the last line. Python cannot parse s.py now: "
                                      "IndentationError at line 2: unexpected indent. It cannot run until that "
                                      "line is fixed.]"), r.result
    r = disp(BeingIntent("memory_read", {"path": "notes/s.py", "start_line": 2}), _ALLOW)
    assert r.ok and r.result.startswith("[lines 2-2 of 2") and "cannot parse s.py now" in r.result, r.result
    f.write_text("p = 1\nq = 2\n")
    r = disp(BeingIntent("memory_read", {"path": "notes/s.py"}), _ALLOW)
    assert r.ok and r.result.endswith("\n[end of file: line 2 is the last line. Python can parse s.py now. "
                                      "That is not the same as running it.]"), r.result
    (Path(root) / "journal.md").write_text("a note\n")
    r = disp(BeingIntent("memory_read", {"path": "journal.md"}), _ALLOW)
    assert r.ok and r.result == "a note\n", r.result

def test_a_read_says_when_its_dated_lines_are_old_even_if_the_file_was_just_appended():
    """2026-09-29: cbp-being repeated a fifteen-day-old outage from its own inbox.md as current.
    The file had been appended that morning, so its mtime said "fresh"; the lines were not."""
    from datetime import datetime, timedelta, timezone
    from sage.gateway.reference_f1a import dated_lines_note
    now = datetime.now(timezone.utc)
    # Two minutes past fifteen days: a minute-precision stamp stands for the whole minute, so a
    # stamp written exactly fifteen days ago is only GUARANTEED 14d 23h 59m+ old, and "at least
    # 15 days" would overstate it (the precision rule, GPT re-review of #270).
    old = (now - timedelta(days=15, minutes=2)).strftime("%Y-%m-%d %H:%M")
    today = now.strftime("%Y-%m-%d %H:%M")
    disp, root = _disp()
    note = os.path.join(root, "inbox.md")
    disp(BeingIntent("memory_write", {"path": note, "content":
        f"{old} UTC — Coordination request #12529 queued. Server offline ~5 hours.\n"
        f"- [ ] verify the MCP server is running\n"
        f"{today} UTC — escalated to dp.\n"}), _ALLOW)
    r = disp(BeingIntent("memory_read", {"path": note}), _ALLOW)
    assert r.ok and r.result.startswith("[dated lines shown here run from"), r.result[:200]
    assert "2 of 3 dated lines are more than a day old" in r.result, r.result[:300]
    assert "the oldest at least 15 days ago" in r.result and "measured lines in your state" in r.result
    assert "#12529" in r.result, "the content itself is still shown whole"

    # Nothing old, nothing said: a fresh note and a code file read exactly as before.
    fresh = os.path.join(root, "fresh.md")
    disp(BeingIntent("memory_write", {"path": fresh, "content": f"{today} UTC — all quiet\n"}), _ALLOW)
    assert disp(BeingIntent("memory_read", {"path": fresh}), _ALLOW).result == f"{today} UTC — all quiet\n"
    code = os.path.join(root, "prog.py")
    disp(BeingIntent("memory_write", {"path": code, "content": "x = 1\nprint(x)\n"}), _ALLOW)
    code_read = disp(BeingIntent("memory_read", {"path": code}), _ALLOW).result
    assert code_read.startswith("x = 1\nprint(x)\n") and "dated lines" not in code_read, code_read

    # A windowed read counts only the window it shows.
    assert dated_lines_note(f"{today} UTC — new\n", now) == ""
    assert dated_lines_note(f"{old} UTC — old\nplain\n", now).startswith("[dated lines shown here")


def test_dated_lines_honour_explicit_zones_and_never_overstate_an_unzoned_age():
    """GPT review of #270: `2026-09-28 10:00 -0700` at now=2026-09-29T12:00Z is 19 h old, and the
    first cut called it more than a day old by discarding the offset and assuming UTC."""
    from datetime import datetime, timezone
    from sage.gateway.reference_f1a import dated_lines_note as note
    now = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
    # GPT's exact reproduction: 17:00Z on the 28th -> 19 h old -> NOT old.
    assert note("2026-09-28 10:00 -0700 — check succeeded\n", now) == ""
    # The same wall time in UTC is 26 h old -> old, exactly.
    assert note("2026-09-28 10:00 UTC — check succeeded\n", now).startswith("[dated lines")
    # ISO forms with an offset: 2026-09-28T13:00:00+02:00 = 11:00Z -> 25 h -> old; -05:00 = 18:00Z -> 18 h -> not.
    assert note("2026-09-28T13:00:00+02:00 did x\n", now).startswith("[dated lines")
    assert note("2026-09-28T13:00:00-05:00 did x\n", now) == ""
    # Z suffix, and the exact boundary: 24 h old is not "more than a day".
    assert note("2026-09-28T12:00Z done\n", now) == ""
    assert note("2026-09-28T11:59Z done\n", now).startswith("[dated lines")
    # A time with NO zone is placed at its latest possible instant (UTC-12): 2026-09-28 10:00 ->
    # 22:00Z at the latest -> 14 h -> not old, even though as UTC it would be 26 h.
    assert note("2026-09-28 10:00 — unzoned\n", now) == ""
    # A date with NO time is a calendar day, never midnight UTC: yesterday is not old...
    assert note("2026-09-28 — yesterday\n", now) == ""
    # ...three days back is, and the note says its ages are minimums and shows the written date.
    three = note("2026-09-26 — earlier\n", now)
    assert three.startswith("[dated lines shown here run from 2026-09-26 to 2026-09-26")
    assert "counted at the latest time" in three and "at least 2 days" in three, three
    # Fully zoned lines carry no caveat.
    assert "latest time" not in note("2026-09-20T10:00Z old\n", now)


def test_dated_lines_count_from_the_end_of_their_written_precision():
    """GPT re-review of #270 (d4ed406): the regex consumed seconds and fractions and discarded
    them, so `2026-09-28T12:00:59Z` at now=2026-09-29T12:00:30Z (23h59m31s old) was called more
    than a day old. A written time stands for every instant that truncates to it, and a line is
    old only when it is old under every such reading."""
    from datetime import datetime, timezone
    from sage.gateway.reference_f1a import dated_lines_note as note
    old = lambda s, now: note(s + " done\n", now).startswith("[dated lines")
    now = datetime(2026, 9, 29, 12, 0, 30, tzinfo=timezone.utc)
    # GPT's exact reproduction: 23h59m31s -> not old.
    assert not old("2026-09-28T12:00:59Z", now)
    # SECONDS at the boundary. 12:00:30 covers [:30, :31): at worst exactly 24 h -> not old.
    assert not old("2026-09-28T12:00:31Z", now)     # just under a day
    assert not old("2026-09-28T12:00:30Z", now)     # exact: some reading is 24 h, not more
    assert old("2026-09-28T12:00:29Z", now)         # just over: every reading is > 24 h
    assert old("2026-09-28 12:00:29 UTC", now)      # same, space form
    assert not old("2026-09-28T14:00:31+02:00", now)  # offset + seconds: = 12:00:31Z
    assert old("2026-09-28T07:00:29-05:00", now)      # = 12:00:29Z
    # FRACTIONS at the boundary: .9 covers [.9, 1.0), and fraction digits are honoured.
    assert old("2026-09-28T12:00:29.9Z", now)       # every reading in (24h, 24h+0.1s]
    assert not old("2026-09-28T12:00:30.0Z", now)   # exact 24 h is not "more than"
    assert not old("2026-09-28T12:00:30.000001Z", now)
    frac_now = datetime(2026, 9, 29, 12, 0, 29, 950000, tzinfo=timezone.utc)
    assert not old("2026-09-28T12:00:29.9Z", frac_now)    # could be 29.99 -> 23h59m59.96s
    assert old("2026-09-28T12:00:29.90Z", frac_now)   # two digits: [.90, .91) -> > 24 h, so the
                                                      # written digits, not just the value, count
    assert old("2026-09-28T12:00:29.94Z", frac_now)        # every reading < 29.95 -> > 24 h
    assert not old("2026-09-28T12:00:29.95Z", frac_now)    # exact
    # More than six fraction digits: the bound rounds UP, never down.
    assert old("2026-09-28T12:00:29.9999999Z", now)        # sup is exactly :30 -> > 24 h all
    assert not old("2026-09-28T12:00:30.0000001Z", now)
    # MINUTE precision covers the whole minute: 12:00 could be 12:00:59.
    assert not old("2026-09-28T12:00Z", now)        # 23h59m31s at its latest reading
    at_minute = datetime(2026, 9, 29, 12, 1, tzinfo=timezone.utc)
    assert old("2026-09-28T12:00Z", at_minute)      # every reading is > 24 h
    assert not old("2026-09-28T12:00Z", datetime(2026, 9, 29, 12, 0, 59, tzinfo=timezone.utc))


def test_a_record_write_stamps_when_each_named_code_file_last_changed():
    """2026-09-22: 14 of cbp-being's beats claimed a code change no beat had made, with the
    refusal in view. The receipt of the journal write now carries the named file's mtime."""
    import datetime as dt
    import os
    import time
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    (home / "experiments").mkdir(exist_ok=True)
    s = home / "mechanism.py"
    s.write_text("x = 1\n")
    old = time.time() - 7200
    os.utime(s, (old, old))
    (home / "notes" / "helper.py").write_text("y = 2\n")
    (home / "experiments" / "train.py").write_text("z = 3\n")
    r = disp(BeingIntent("memory_write", {"path": "journal.md", "content":
        "Fixed mechanism.py. Also touched helper.py and ghost.py."}), _ALLOW)
    assert r.ok
    stamp = dt.datetime.fromtimestamp(old, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
    assert f"mechanism.py was last changed at {stamp} UTC" in r.result, r.result
    assert "notes/helper.py was last changed at" in r.result, "a bare name found under notes/ says where"
    assert "ghost.py was not found at the top of your home, in notes/ or in scratch/" in r.result, r.result
    # the 09-28 review's case: a bare name that lives elsewhere must not be called absent
    r = disp(BeingIntent("memory_write", {"path": "todo.md", "content": "- [done] fix train.py"}), _ALLOW)
    assert "not a file" not in r.result and "not found at the top of your home, in notes/ or in scratch/" in r.result
    r = disp(BeingIntent("memory_write", {"path": "todo.md", "content": "- [done] fix experiments/train.py"}), _ALLOW)
    assert "experiments/train.py was last changed at" in r.result, r.result
    # 2026-10-08: request_run files live in scratch/; a bare name there was reported absent,
    # and naming it both ways stamped it once and denied it once in the same receipt
    (home / "scratch").mkdir(exist_ok=True)
    (home / "scratch" / "probe.py").write_text("w = 4\n")
    r = disp(BeingIntent("memory_write", {"path": "todo.md", "content":
        "- ran scratch/probe.py; next: edit probe.py line 3"}), _ALLOW)
    assert r.result.count("scratch/probe.py was last changed at") == 1, r.result
    assert "probe.py was not found" not in r.result, r.result


def test_a_record_write_never_stamps_a_file_outside_the_home():
    import tempfile
    disp, root = _disp()
    outside = Path(tempfile.mkdtemp()) / "secret.py"
    outside.write_text("k = 1\n")
    rel = os.path.relpath(outside, root)
    r = disp(BeingIntent("memory_write", {"path": "journal.md", "content": f"see {rel}"}), _ALLOW)
    assert r.ok and "last changed" not in r.result, r.result
    assert "was not found in your home" in r.result, r.result


def test_a_record_write_naming_no_code_file_is_unchanged():
    disp, root = _disp()
    r = disp(BeingIntent("memory_write", {"path": "journal.md", "content": "a quiet beat"}), _ALLOW)
    assert r.ok and "Files this names" not in r.result
    # a .py write gets its parse status, not stamps
    r = disp(BeingIntent("memory_write", {"path": "notes/a.py", "content": "import b  # b.py"}), _ALLOW)
    assert r.ok and "Files this names" not in r.result


def test_memory_edit_reads_delete_lines_as_the_range():
    """2026-09-24 05:57Z: cbp-being sent start_line 180, delete_lines 5, new "". Nothing read
    the 5, end_line defaulted to 180, and one line was deleted while the being journaled five."""
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    f = home / "notes" / "s.py"
    f.write_text("a\nb\nc\nd\ne\nf\ng\n")
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": "2", "delete_lines": "5", "new": ""}), _ALLOW)
    assert r.ok, r.error
    assert f.read_text() == "a\ng\n"
    assert "replaced lines 2-6 (5 lines)" in r.result, r.result


def test_memory_edit_delete_lines_agrees_with_end_line_or_refuses():
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    f = home / "notes" / "s.py"
    f.write_text("a\nb\nc\nd\n")
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 2, "end_line": 2, "delete_lines": 3, "new": ""}), _ALLOW)
    assert not r.ok and "name different ranges" in r.error, r.error
    for bad in (0, -1, "five"):
        r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 2, "delete_lines": bad, "new": ""}), _ALLOW)
        assert not r.ok and "Nothing was changed" in r.error and "delete_lines 7" in r.error, (bad, r.error)
    # a count that runs past the end is refused by the existing range check, not truncated
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 3, "delete_lines": 5, "new": ""}), _ALLOW)
    assert not r.ok and "are not all in" in r.error, r.error
    # agreeing end_line and delete_lines is fine
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 2, "end_line": 3, "delete_lines": 2, "new": ""}), _ALLOW)
    assert r.ok and f.read_text() == "a\nd\n", r.error


def test_a_missed_anchor_whose_prefix_repeats_names_every_place():
    """2026-09-21: cbp-being's refused `old` began with 3 lines of a stray block (1610-1612)
    that also occur at 330-332, the working branch. Naming only the first match says "your
    lines are at 330"; a 4B acting on that deletes code that works. Every place is named, at
    the first line where the places differ (the line right after the prefix was shared)."""
    from sage.gateway.reference_f1a import _where_it_diverged
    block = ["            noise=0.1,", "        )", "        print('gen')", "    else:"]
    have = (["# top"] + block + ["        print('Loading')", "        X, y = load()"]
            + ["# middle", "main()"] + block + ["        X = load()", "        y = load2()"])
    text = "\n".join(have)
    msg = _where_it_diverged(text, "\n".join(block[:3] + ["        print('X shape')"]))
    assert "in 2 places" in msg
    assert "lines 2-4" in msg and "lines 10-12" in msg
    assert "print('Loading')" in msg and "X = load()" in msg, "each place shown where they differ"


def test_a_missed_anchor_with_one_match_reads_as_before():
    from sage.gateway.reference_f1a import _where_it_diverged
    text = "a\nb\nc\nd"
    msg = _where_it_diverged(text, "b\nc\nX")
    assert "match lines 2-3 of the file exactly" in msg and "places" not in msg


def test_a_range_edit_whose_old_is_elsewhere_says_where():
    """cbp-being 2026-10-07 02:53Z: the seat's exact old text sent with the traceback's line
    number (148) instead of the line it was on (145), refused twice in one beat. The refusal
    now names the line where old is, when it occurs once."""
    disp, root = _disp()
    home = Path(root)
    (home / "notes").mkdir(exist_ok=True)
    f = home / "notes" / "s.py"
    before = "a = 1\nb = f(a)\nc = g(b)\nprint(c)\n"
    f.write_text(before)
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 4,
                                         "old": "b = f(a)", "new": "b = f(a).detach()"}), _ALLOW)
    assert not r.ok
    assert "Your old text IS in the file, once, at line 2, not at line 4" in r.error, r.error
    assert "with start_line 2" in r.error
    assert f.read_text() == before
    # multi-line old names its range
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 1, "end_line": 2,
                                         "old": "c = g(b)\nprint(c)", "new": "x"}), _ALLOW)
    assert not r.ok and "at lines 3-4, not at line 1" in r.error, r.error
    # old absent, or present more than once: no location is claimed
    f.write_text(before + "b = f(a)\n")
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 4,
                                         "old": "b = f(a)", "new": "y"}), _ALLOW)
    assert not r.ok and "IS in the file" not in r.error, r.error
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 4,
                                         "old": "zzz", "new": "y"}), _ALLOW)
    assert not r.ok and "IS in the file" not in r.error, r.error
