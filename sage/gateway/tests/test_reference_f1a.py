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
    Path(root, "notes", "small.py").write_text("a = 1\n")
    assert disp(BeingIntent("memory_read", {"path": "notes/small.py"}), _ALLOW).result == "a = 1\n"
    r = disp(BeingIntent("memory_read", {"path": "notes/small.py", "start_line": 9}), _ALLOW)
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


def test_a_py_receipt_says_whether_python_can_parse_the_file_now():
    """2026-09-21: from 18:22 the being's script could not be parsed, and for two hours it
    recorded "runs correctly" and "Applied fix" while every write left it unparseable. The
    receipts never said. Parsing executes nothing; the sentence says it is not a run."""
    disp, root = _disp()
    home = Path(root)
    r = disp(BeingIntent("memory_write", {"path": "notes/s.py", "content": "def main():\n    pass\n"}), _ALLOW)
    assert r.ok and "Python can parse s.py now. That is not the same as running it." in r.result
    # the being's real 20:18 write: a bracketed description appended where an edit was meant
    r = disp(BeingIntent("memory_write", {"path": "notes/s.py",
                                          "content": "            noise=0.1,\n        )"}), _ALLOW)
    assert r.ok and "Python cannot parse s.py now: IndentationError at line 3" in r.result, r.result
    r = disp(BeingIntent("memory_edit", {"path": "notes/s.py", "start_line": 3, "end_line": 4, "new": ""}), _ALLOW)
    assert r.ok and "Python can parse s.py now" in r.result, r.result


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
