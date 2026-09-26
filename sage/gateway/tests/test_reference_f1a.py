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
    # The reach is SAID, not implied: a bare root is exact since hestia #1002, and this test
    # wants the subtree (reconciliation 2026-09-22).
    r = disp(BeingIntent("memory_read", {"path": target}), GatewayVerdict("allow", granted=(other,), granted_reach=((other, True),)))
    assert r.ok and "a note from a peer" in r.result
    r = disp(BeingIntent("memory_read", {"path": target}), _ALLOW)
    assert not r.ok and "outside your reach" in (r.error or "")
    # a granted root never widens to its parent or a sibling
    r = disp(BeingIntent("memory_read", {"path": os.path.join(os.path.dirname(other), "x.md")}),
             GatewayVerdict("allow", granted=(other,), granted_reach=((other, True),)))
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


# ---- carried from legion/mission-artifact in the 2026-09-22 reconciliation ----
def test_memory_read_missing_is_never_a_silent_zero():
    """Inverted twice, and the second inversion is the reconciliation of 2026-09-18.

    It first pinned ok+"" for a missing file, which cost six silent zeros in one beat
    (2026-09-09), and was changed to ok=False. main fixed the same class the other way —
    ok=True with a result that names itself — after cbp-being read "" as an empty daemon log
    and wrote an outage that was not happening. MAIN'S CONVENTION WINS here: the law refused
    nothing, and the renderer labels a not-ok envelope "[dispatch error]", which is a false
    label for a path that simply is not there. What must never happen either way is silence."""
    disp, root = _disp()
    r = disp(BeingIntent("memory_read", {"path": os.path.join(root, "nope.md")}), _ALLOW)
    assert r.ok and "no such path" in r.result and "nope.md" in r.result
    assert "not an empty file" in r.result, r.result


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
    assert "truncated" in r.result and "were NOT shown" in r.result, r.result[-200:]   # main's line-window marker (2026-09-22 reconciliation)
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
    assert "start_line=" in r3.result and "of 500" in r3.result   # main's window marker names the way on
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
    with pytest.raises(ValueError, match="escapes|outside your reach"):
        confine(exact, child)                                  # exact must NOT admit a child

    rec = GatewayVerdict("allow", granted=((other, True),))
    assert confine(rec, child).name == "note.md", "recursive admits the child"
    with pytest.raises(ValueError, match="escapes|outside your reach"):
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
    with pytest.raises(ValueError, match="escapes|outside your reach"):
        confine(bare, child)


def test_a_missing_file_names_where_it_looked_and_a_directory_lists():
    """2026-09-09 02:24Z: six memory_reads in one beat (notes/plan.md, five guessed test
    paths) returned ok=True with "" — the false-absence class; the being had no way to
    tell a missing file from an empty one and no way to list a directory.

    Reconciled 2026-09-18: each case still names itself, and each is an ANSWER rather than a
    "[dispatch error]" (main's convention). The empty file, which this branch's version left
    silent, now says it is empty."""
    disp, root = _disp()
    os.makedirs(os.path.join(root, "notes"))
    open(os.path.join(root, "notes", "real.md"), "w").write("hello")
    v = GatewayVerdict("allow", granted=())
    r = disp(BeingIntent("memory_read", {"path": "notes/plan.md"}), v)
    assert r.ok and "no such path" in r.result and "notes/plan.md" in r.result
    assert "relative paths resolve under your home" in r.result and "contains: real.md" in r.result
    r = disp(BeingIntent("memory_read", {"path": os.path.join(root, "tests", "test_x.py")}), v)
    assert r.ok and "absolute path" in r.result and "contains" not in r.result   # parent missing too
    d = disp(BeingIntent("memory_read", {"path": "notes"}), v)
    assert d.ok and "1 entry" in d.result and "real.md  (5 bytes)" in d.result
    top = disp(BeingIntent("memory_read", {"path": "."}), v)
    assert top.ok and "notes/" in top.result
    e = open(os.path.join(root, "notes", "empty.md"), "w"); e.close()
    r = disp(BeingIntent("memory_read", {"path": "notes/empty.md"}), v)
    assert r.ok and "empty file" in r.result, r.result       # empty SAYS it is empty


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
    assert r.ok and "created" in r.result and "was 0 bytes, now" in r.result   # main's wording: created/appended, lowercase
    disp(BeingIntent("memory_write", {"path": "notes.md", "content": "second"}), v)
    body = open(os.path.join(root, "notes.md")).read()
    assert body == "first\nsecond\n", body           # append is still the default

    r = disp(BeingIntent("memory_write", {"path": "notes.md", "content": "only", "mode": "replace"}), v)
    assert r.ok and "REPLACED the file with" in r.result
    assert open(os.path.join(root, "notes.md")).read() == "only\n"

    bad = disp(BeingIntent("memory_write", {"path": "notes.md", "content": "x", "mode": "overwrite"}), v)
    assert not bad.ok and "'append' (the default) or 'replace'" in bad.error
    assert open(os.path.join(root, "notes.md")).read() == "only\n", "a refused mode changes nothing"


def test_memory_write_names_the_path_it_actually_wrote():
    """2026-09-11: the being wrote three correct chunks to
    "being-worktrees/legion-being/sage/gateway/tests/x.py" — RELATIVE, so it resolved inside
    its home, created that whole tree there, and left the real worktree file untouched. The
    result said "x.py was 0 bytes", and the basename is identical in both places, so the one
    clue available was invisible. Name the resolved path."""
    disp, root = _disp()
    v = GatewayVerdict("allow", granted=())
    r = disp(BeingIntent("memory_write", {"path": "sub/dir/note.md", "content": "x"}), v)
    assert r.ok
    assert os.path.join(root, "sub", "dir", "note.md") in r.result, r.result
    assert "relative paths resolve inside your home" in r.result
    assert root in r.result


def test_memory_write_says_when_the_content_is_already_there():
    """A being twenty steps into a beat cannot see what it wrote at step three — the earlier
    result has been elided. legion-being appended to one file 28 times in a 42-step beat,
    several chunks byte-identical. Not fatal and not worth refusing (deliberate repetition is
    legitimate), but it must not be invisible."""
    disp, root = _disp()
    v = GatewayVerdict("allow", granted=())
    disp(BeingIntent("memory_write", {"path": "n.md", "content": "alpha"}), v)
    again = disp(BeingIntent("memory_write", {"path": "n.md", "content": "alpha"}), v)
    assert again.ok, "a repeat is noted, never refused"
    assert "already" in again.result and "earlier step of this beat" in again.result
    assert open(os.path.join(root, "n.md")).read() == "alpha\nalpha\n"   # still appended

    fresh = disp(BeingIntent("memory_write", {"path": "n.md", "content": "beta"}), v)
    assert "NOTE:" not in fresh.result
    # replace never carries the note: overwriting with the same text is not a duplicate
    same = disp(BeingIntent("memory_write", {"path": "n.md", "content": "beta", "mode": "replace"}), v)
    assert "NOTE:" not in same.result


def test_a_write_refusal_names_the_verb_that_does_reach_the_forum():
    """A boundary that says only what is forbidden makes the being guess at what is allowed.

    legion-being hit this refusal twice on 2026-09-13 trying to answer a peer on the fleet
    forum — `memory_write` is the intuitive verb, and the message named no other. It already
    had `peer_ask`, which files to the forum in its name, and reached for it only after
    spending a step on the refusal each time."""
    import tempfile
    from pathlib import Path
    from sage.gateway.reference_f1a import ReferenceF1aDispatcher

    home = Path(tempfile.mkdtemp(prefix="hint-home-"))
    shared = Path("/home/dp/ai-workspace/shared-context")
    d = ReferenceF1aDispatcher(memory_root=home, worktree=None, witness_fn=None)
    d._extra_roots = [(shared, True)]

    try:
        d._safe_path(str(shared / "forum" / "x.md"), writing=True)
        assert False, "a write into the forum must be refused"
    except ValueError as e:
        msg = str(e)
    assert "peer_ask" in msg and "mesh" in msg          # the doors that work, by name
    assert "not a workaround" in msg                     # ... and that they are not second best
    assert "not a missing grant" in msg                  # the grant is not the thing missing

    # a shared path that is NOT the forum gets no forum hint, and does not dangle a
    # "none of those" clause referring to options it never listed
    try:
        d._safe_path(str(shared / "plans" / "y.md"), writing=True)
        assert False, "a write into shared plans must be refused"
    except ValueError as e:
        other = str(e)
    assert "peer_ask" not in other and "none of those" not in other
    assert "appeal for the affordance" in other


def _edit_tree(tmp_path, body):
    """A being home + worktree with one file, wired as the dispatcher sees them."""
    from pathlib import Path
    from sage.gateway.reference_f1a import ReferenceF1aDispatcher
    home = tmp_path / "home"; home.mkdir()
    wt = tmp_path / "wt"; (wt / "pkg").mkdir(parents=True)
    f = wt / "pkg" / "mod.py"; f.write_text(body)
    d = ReferenceF1aDispatcher(memory_root=home, worktree=str(wt), witness_fn=lambda e: "w")
    d._extra_roots = [(wt, True)]
    d._wt_writable = True
    return d, f


def test_edit_changes_one_located_occurrence_inside_a_file(tmp_path):
    """The verb that made production code reachable at all.

    2026-09-13: `memory_write` had two modes — append, or replace the WHOLE file. To change
    three lines inside compose(), legion-being would have had to resend all 63,645 chars of
    heartbeat.py: ~25,458 tokens against ~6,500 of working room. So it appended a wrapper
    that shadowed the function instead. The semantics were right; the shape was the only one
    its instruments allowed. Every merged PR it had until then added a NEW file — which read
    as preference and was structure."""
    from sage.gateway.being_gate_client import BeingIntent

    d, f = _edit_tree(tmp_path, "def a():\n    return 1\n\n\ndef b():\n    return 2\n")
    env = d._do_edit(BeingIntent("edit", {"path": str(f),
                                          "old": "def a():\n    return 1",
                                          "new": "def a():\n    return 99"}))
    assert env.ok, env.error
    assert f.read_text() == "def a():\n    return 99\n\n\ndef b():\n    return 2\n"
    assert "one occurrence" in env.result.lower()
    assert env.witness_id, "an edit is a write and must be witnessed"

    # an empty `new` is a deletion, not a refusal
    env2 = d._do_edit(BeingIntent("edit", {"path": str(f), "old": "\n\n\ndef b():\n    return 2\n", "new": ""}))
    assert env2.ok and f.read_text() == "def a():\n    return 99"


def test_edit_refuses_zero_and_multiple_matches_and_says_the_count(tmp_path):
    """Zero means the anchor is remembered rather than read. Several means it has not said
    which site it means, and choosing for it would be the harness guessing at intent."""
    from sage.gateway.being_gate_client import BeingIntent

    d, f = _edit_tree(tmp_path, "x = 1\ny = 1\nz = 1\n")
    before = f.read_text()

    miss = d._do_edit(BeingIntent("edit", {"path": str(f), "old": "q = 9", "new": "q = 8"}))
    assert miss.ok is False and "no occurrence" in miss.error and "BYTE FOR BYTE" in miss.error

    many = d._do_edit(BeingIntent("edit", {"path": str(f), "old": " = 1", "new": " = 2"}))
    assert many.ok is False and "3 occurrences" in many.error, many.error
    assert "unique" in many.error                      # it says HOW to fix it

    assert f.read_text() == before, "a refused edit must not touch the file"

    same = d._do_edit(BeingIntent("edit", {"path": str(f), "old": "x = 1", "new": "x = 1"}))
    assert same.ok is False and "identical" in same.error

    gone = d._do_edit(BeingIntent("edit", {"path": str(f.parent / "nope.py"), "old": "a", "new": "b"}))
    assert gone.ok is False and "no such file" in gone.error


def test_edit_obeys_the_same_write_confinement_as_every_other_write(tmp_path):
    """An edit IS a write. It is registered as the same gate tool and it goes through
    _safe_path(writing=True), so it cannot reach anywhere memory_write cannot."""
    from pathlib import Path
    from sage.gateway.being_gate_client import BeingIntent

    d, f = _edit_tree(tmp_path, "hello\n")
    outside = tmp_path / "elsewhere.py"; outside.write_text("hello\n")
    d._extra_roots = list(d._extra_roots) + [(tmp_path, True)]   # readable, not writable

    try:
        d._do_edit(BeingIntent("edit", {"path": str(outside), "old": "hello", "new": "bye"}))
        assert False, "an edit outside the writable roots must be refused"
    except ValueError as e:
        assert "not writable" in str(e) or "stay inside" in str(e), e
    assert outside.read_text() == "hello\n"


def test_a_missed_read_names_where_the_file_actually_is(tmp_path):
    """legion-being lost the `scratch/game/` prefix four times on 2026-09-17/18 — moves.md,
    current.md, board.txt — each miss costing a verb and a compaction, with the right path
    sitting in a note its window had eaten. The refusal now names the remedy."""
    from sage.gateway.reference_f1a import ReferenceF1aDispatcher as R
    from sage.gateway.being_gate_client import BeingIntent
    home = tmp_path / "inst"; (home / "scratch" / "game").mkdir(parents=True)
    (home / "scratch" / "game" / "moves.md").write_text("  1  ACTION6 1,2   0   0 x0-1 y0-1 (4)  0\n")
    d = R(memory_root=str(home))          # the real constructor, like every other test here

    r = d._do_memory_read(BeingIntent("memory_read", {"path": "moves.md"}))
    assert r.ok is True                                   # an answer, not a "[dispatch error]"
    assert "A file called 'moves.md' IS in your home, at: scratch/game/moves.md" in r.result, r.result
    assert "read it by that path" in r.result
    # a name that genuinely does not exist says so without inventing a hint
    n = d._do_memory_read(BeingIntent("memory_read", {"path": "nowhere.md"}))
    assert n.ok is True and "IS in your home" not in n.result
    # and the real path still reads
    ok = d._do_memory_read(BeingIntent("memory_read", {"path": "scratch/game/moves.md"}))
    assert ok.ok and "ACTION6" in ok.result
