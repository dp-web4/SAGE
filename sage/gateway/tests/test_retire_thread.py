"""retire_thread: close a whole line of work at once (being_threads). dp, 2026-11-01, to cbp-being: "retire
the whole hestia thread and work on something different" -- 550 of its 584 open todo items and 29 of its
30 settled entries were on that thread, and retire_note / settle could only move one at a time."""
import base64
import builtins
import io
import json
import os
import re
import tempfile
from pathlib import Path

from sage.gateway import being_settled as st
from sage.gateway import being_threads as bt
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict, thread_paths
from sage.gateway.heartbeat import _todo_items
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
from sage.gateway.home_recall import search_home
from sage.gateway.tests.test_hestia_dispatch import FakeMcp

_ALLOW = GatewayVerdict("allow")

TODO = """2026-10-30 09:00 UTC
- [ ] Restart the widget daemon on port 9911
- [ ] Install the widget package with apt
- [x] Read the widget docs
2026-10-31 10:00 UTC
- [ ] Build a small neural net and test it on the sine data
- [ ] Ask about the widget installer again
- [ ] Explore what a living document could be
"""


def _home(tmp_path):
    (tmp_path / "todo.md").write_text(TODO)
    for q, a in (("Is the widget daemon running?", "no, port 9911 is closed"),
                 ("Why does the net overfit?", "too few samples; more data fixed it"),
                 ("How do I install the widget?", "apt, but the seat declines it")):
        assert st.settle(tmp_path, {"question": q, "answer": a}, now=0)[0]
    return tmp_path


def _go(h, args, now=None):
    """Preview with the same words and reason, then retire with the confirmation it returned (if any)."""
    ok, msg, _ = bt.retire_thread(h, dict(args, preview="true"), now=now)
    assert ok, msg
    m = re.search(r"confirmation: ([A-Za-z0-9_-]{22})", msg)
    return bt.retire_thread(h, dict(args, **({"confirmation": m.group(1)} if m else {})), now=now)


def _open(h):
    return [t for t, _ in _todo_items((h / "todo.md").read_text()).values()]


def test_a_thread_leaves_the_todo_and_the_settled_list_and_the_rest_stays(tmp_path):
    h = _home(tmp_path)
    ok, msg, changed = _go(h, {"words": "widget, daemon", "reason": "dp: drop it"}, now=0)
    assert ok and changed, msg
    assert "3 open todo item(s) and 2 settled entries" in msg and "Still open: 2" in msg
    assert _open(h) == ["Build a small neural net and test it on the sine data",
                        "Explore what a living document could be"]
    assert [e["question"] for e in st.read(h)[0]] == ["Why does the net overfit?"]
    arch = (h / bt.archive_name({"words": "widget, daemon", "reason": "dp: drop it"})).read_text()
    assert "Topic words: widget, daemon" in arch and "No longer current: dp: drop it" in arch
    assert "- [ ] Install the widget package with apt (since 2026-10-30 09:00 UTC)" in arch
    assert "Is the widget daemon running? -> no, port 9911 is closed" in arch
    assert arch.endswith(TODO), "the replaced todo.md is kept whole"
    log = [json.loads(l) for l in (h / st.SETTLED_LOG).read_text().splitlines()]
    assert log[-1]["op"] == "retire_thread" and log[-1]["ids"] == ["s1", "s3"]
    assert log[-1]["to"].startswith("todo.retired-thread-") and len(log[-1]["from"]) == 2


def test_open_items_keep_the_date_they_were_opened(tmp_path):
    h = _home(tmp_path)
    before = {t: s for t, s in _todo_items(TODO).values()}
    assert _go(h, {"words": "widget", "reason": "r"}, now=0)[0]
    after = {t: s for t, s in _todo_items((h / "todo.md").read_text()).values()}
    assert after and all(before[t] == s for t, s in after.items())


def test_recall_still_finds_what_was_retired(tmp_path):
    h = _home(tmp_path)
    assert _go(h, {"words": "widget", "reason": "r"}, now=0)[0]
    hits = search_home(h, "widget installer")
    assert any(r["source"].startswith("todo.retired-") for r in hits), hits


def test_a_preview_changes_nothing_and_says_what_would_move(tmp_path):
    h = _home(tmp_path)
    before = {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()}
    ok, msg, changed = bt.retire_thread(h, {"words": "widget", "preview": "true"}, now=0)
    assert ok and not changed and msg.startswith("PREVIEW, nothing was changed")
    assert "3 of 5 open todo item(s) and 2 of 3 settled entries would be retired" in msg
    assert "STAYS: Build a small neural net" in msg
    assert {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()} == before


def test_a_word_matches_at_the_start_of_a_word_only(tmp_path):
    hit = bt.matcher(bt.words_of("install, api, port 99"))
    assert hit("the installer") and hit("API down") and hit("on port 9911")
    assert not hit("reinstalled") and not hit("rapid growth") and not hit("support 9911")
    assert bt.matcher(["/proc"])("read /proc/1/cmdline")


def test_refusals_change_nothing(tmp_path):
    h = _home(tmp_path)
    before = {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()}
    for args, said in (({}, "needs 'words'"), ({"words": "ab, widget", "reason": "r"}, "at least 3"),
                       ({"words": "widget"}, "needs a 'reason'")):
        ok, msg, changed = bt.retire_thread(h, args, now=0)
        assert not ok and not changed and said in msg, (args, msg)
    ok, msg, changed = bt.retire_thread(h, {"words": "zebra", "reason": "r"}, now=0)
    assert ok and not changed and "Nothing names zebra" in msg
    assert {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()} == before


def test_the_archive_is_named_by_the_call_and_a_repeat_is_refused_not_renamed(tmp_path):
    """NOVA's hold on #619: the name was picked from the listing, so a retire landing between the gate's
    write set and the lock moved this one to '-2'. Now it is a function of (words, reason) only."""
    a, b = {"words": "daemon", "reason": "r"}, {"words": "widget", "reason": "r"}
    assert bt.archive_name(a) == bt.archive_name({"words": " Daemon ", "reason": "r"}) != bt.archive_name(b)
    h = _home(tmp_path)
    assert _go(h, a, now=0)[0] and _go(h, b, now=0)[0]
    assert (h / bt.archive_name(a)).exists() and (h / bt.archive_name(b)).exists()
    (h / "todo.md").write_text(TODO)            # the thread crept back; the same call again
    before = {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()}
    ok, msg, changed = _go(h, a, now=0)
    assert not ok and not changed and "Give a different reason" in msg
    assert {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()} == before


class _Writes:
    """Every path opened for writing, replaced into, or unlinked while active (reads are not writes)."""

    def __init__(self, monkeypatch):
        self.paths = set()
        real_open, real_replace, real_unlink = builtins.open, os.replace, os.unlink

        def _open(f, mode="r", *a, **k):
            if isinstance(f, (str, bytes, os.PathLike)) and any(c in mode for c in "wax+"):
                self.paths.add(os.path.realpath(f))
            return real_open(f, mode, *a, **k)

        def _replace(src, dst, *a, **k):
            self.paths.update({os.path.realpath(src), os.path.realpath(dst)})
            return real_replace(src, dst, *a, **k)

        def _unlink(p, *a, **k):
            self.paths.add(os.path.realpath(p))
            return real_unlink(p, *a, **k)

        for mod in (builtins, io):
            monkeypatch.setattr(mod, "open", _open)
        monkeypatch.setattr(os, "replace", _replace)
        monkeypatch.setattr(os, "unlink", _unlink)


def _declared(h, args):
    return set(thread_paths(args, {"memory_root": str(h)}))


def test_no_path_outside_the_declared_set_is_opened_for_writing(tmp_path, monkeypatch):
    """NOVA (1bd4fd69): the archive's atomic temp was written and undeclared. Checked on the real
    open/replace calls, not on what is left on disk (a temp file is gone by then)."""
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
    assert thread_paths({"words": "widget", "preview": "true"}, {"memory_root": str(h)}) == []
    declared = _declared(h, args)
    ok, msg, _ = bt.retire_thread(h, dict(args, preview="true"))
    token = re.search(r"confirmation: ([A-Za-z0-9_-]{22})", msg).group(1)
    w = _Writes(monkeypatch)
    assert bt.retire_thread(h, dict(args, confirmation=token))[0]
    assert os.path.realpath(h / f".{bt.archive_name(args)}.tmp") in w.paths, "the temp is exercised"
    assert w.paths and w.paths <= declared, w.paths - declared


def test_an_interleaved_retire_cannot_move_this_one_off_its_declared_paths(tmp_path, monkeypatch):
    h = _home(tmp_path)
    mine, other = {"words": "widget", "reason": "mine"}, {"words": "daemon", "reason": "other"}
    declared = _declared(h, mine)               # the gate is told, then another retire lands first
    assert _go(h, other)[0]
    w = _Writes(monkeypatch)
    assert _go(h, mine)[0]
    assert w.paths <= declared, w.paths - declared
    # the same call landing first takes the declared name: the second is refused and writes nothing
    (tmp_path / "two").mkdir()
    h2 = _home(tmp_path / "two")
    declared = _declared(h2, mine)
    monkeypatch.undo()
    assert _go(h2, mine)[0]
    (h2 / "todo.md").write_text(TODO)           # the thread crept back before the second ran
    w = _Writes(monkeypatch)
    ok, msg, _ = _go(h2, mine)
    assert not ok and "Give a different reason" in msg
    assert not (w.paths - {os.path.realpath(h2 / ".home.lock")}), w.paths


def test_a_failed_settled_commit_rolls_back_within_the_declared_paths(tmp_path, monkeypatch):
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
    declared = _declared(h, args)
    entries_before = (h / "settled.json").read_bytes()
    ok, msg, _ = bt.retire_thread(h, dict(args, preview="true"))
    token = re.search(r"confirmation: ([A-Za-z0-9_-]{22})", msg).group(1)
    monkeypatch.setattr(st, "_commit", lambda *a, **k: (False, "could not write settled.json (OSError)"))
    w = _Writes(monkeypatch)
    ok, msg, changed = bt.retire_thread(h, dict(args, confirmation=token))
    # NOVA item 3: a failure after the first write is never reported as a no-op; the archive stays as
    # recovery evidence (it holds the exact prior bytes), and the todo is restored from its exact bytes.
    assert not ok and changed and "may be partial" in msg and "todo.md was restored" in msg, msg
    assert (h / "todo.md").read_text() == TODO and (h / "settled.json").read_bytes() == entries_before
    arch = (h / bt.archive_name(args)).read_text()
    assert "## Exact prior settled.json (base64, for recovery)" in arch
    assert w.paths <= declared, w.paths - declared


def test_the_verb_retires_and_witnesses():
    FakeMcp.calls = []
    root = Path(tempfile.mkdtemp(prefix="rt-"))
    d = HestiaF1aDispatcher("sprout-being", str(root), mcp_factory=lambda ep, pid: FakeMcp(ep, pid))
    _home(root)
    pre = d(BeingIntent("retire_thread", {"words": "widget", "reason": "finished", "preview": "true"}), _ALLOW)
    token = re.search(r"confirmation: ([A-Za-z0-9_-]{22})", pre.result).group(1)
    env = d(BeingIntent("retire_thread", {"words": "widget", "reason": "finished", "confirmation": token}), _ALLOW)
    assert env.ok and env.witness_id, env.error
    assert "Build a small neural net" in (root / "todo.md").read_text()
    assert "widget" not in (root / "todo.md").read_text().split("UTC:", 1)[-1].lower()


def test_a_preview_on_a_fresh_home_writes_nothing_not_even_the_lock(tmp_path, monkeypatch):
    """NOVA on 577adb4b: thread_paths declares [] for a preview, but the preview took _home_lock, which
    opens .home.lock in append mode and so CREATES it on a home that never had one."""
    (tmp_path / "todo.md").write_text(TODO)                 # no settle: no .home.lock exists yet
    assert not (tmp_path / ".home.lock").exists()
    w = _Writes(monkeypatch)
    ok, msg, changed = bt.retire_thread(tmp_path, {"words": "widget", "preview": "true"})
    assert ok and not changed and msg.startswith("PREVIEW") and "3 of 5 open todo" in msg
    assert w.paths == set(), w.paths
    assert not (tmp_path / ".home.lock").exists()


# -- NOVA's three #619-specific items (from Codex's candidate d217a7a8) ----------------------------------

def test_evidence_alone_does_not_select_a_settled_entry(tmp_path):
    """NOVA item 1: a shared citation or tool name in evidence does not make a conclusion about the topic."""
    h = _home(tmp_path)
    assert st.settle(h, {"question": "Does the sine net generalise?", "answer": "yes, test error 0.04",
                         "evidence": "ran widget-free eval.py"}, now=0)[0]
    ok, msg, _ = bt.retire_thread(h, {"words": "widget", "preview": "true"})
    assert "Does the sine net generalise?" not in msg and "2 of 4 settled entries" in msg, msg


def test_a_broad_retire_without_confirmation_changes_nothing(tmp_path):
    h = _home(tmp_path)
    before = {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()}
    ok, msg, changed = bt.retire_thread(h, {"words": "widget", "reason": "r"})
    assert not ok and not changed and "needs the confirmation" in msg and "Nothing was changed" in msg
    assert {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()} == before


def test_a_confirmation_is_used_once_and_bound_to_what_was_previewed(tmp_path):
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
    get = lambda: re.search(r"confirmation: ([A-Za-z0-9_-]{22})",  # noqa: E731
                            bt.retire_thread(h, dict(args, preview="true"))[1]).group(1)
    tok = get()
    with open(h / "todo.md", "a") as f:                       # the source changes after the preview
        f.write("- [ ] Another widget chore\n")
    ok, msg, _ = bt.retire_thread(h, dict(args, confirmation=tok))
    assert not ok and "changed since that preview" in msg
    ok, msg, _ = bt.retire_thread(h, dict(args, confirmation=tok))
    assert not ok and "unknown, mistyped or expired" in msg, "a consumed confirmation is gone"
    tok = get()
    ok, msg, _ = bt.retire_thread(h, dict(args, reason="other", confirmation=tok))
    assert not ok and "changed since that preview" in msg, "the reason is part of what was previewed"
    assert bt.retire_thread(h, dict(args, confirmation=get()))[0]


def test_a_preview_without_a_reason_says_how_to_get_a_confirmation(tmp_path):
    h = _home(tmp_path)
    ok, msg, _ = bt.retire_thread(h, {"words": "widget", "preview": "true"})
    assert ok and "preview again WITH the reason" in msg and "confirmation:" not in msg


def test_a_narrow_retire_needs_no_confirmation(tmp_path):
    h = _home(tmp_path)
    ok, msg, changed = bt.retire_thread(h, {"words": "installer", "reason": "r"})
    assert ok and changed and "1 open todo item(s)" in msg, msg


def test_a_common_word_is_not_a_topic(tmp_path):
    h = _home(tmp_path)
    ok, msg, changed = bt.retire_thread(h, {"words": "widget, the", "reason": "r"})
    assert not ok and not changed and "common word" in msg


def test_a_todo_write_failure_is_reported_as_possibly_partial(tmp_path, monkeypatch):
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
    tok = re.search(r"confirmation: ([A-Za-z0-9_-]{22})",
                    bt.retire_thread(h, dict(args, preview="true"))[1]).group(1)
    real = bt._write_atomic

    def failing(p, text):
        if p.name == "todo.md":
            raise OSError("disk full")
        return real(p, text)
    monkeypatch.setattr(bt, "_write_atomic", failing)
    ok, msg, changed = bt.retire_thread(h, dict(args, confirmation=tok))
    assert not ok and changed and "may be partial" in msg and bt.archive_name(args) in msg
    assert (h / bt.archive_name(args)).exists() and (h / "todo.md").read_text() == TODO



def test_a_closed_line_keeps_its_reason_in_every_beat_and_its_items_stay_retired(tmp_path):
    # sprout-being 11-07 08:11Z: it retired its seat thread with a true reason; 15 settled entries left the
    # beat, and so did that reason. By 22:46Z it had settled the opposite.
    h = _home(tmp_path)
    assert bt.render_closed(h) == "", "nothing closed, no block"
    ok, msg, _ = _go(h, {"words": "widget, daemon", "reason": "The daemon is fine; it was never down."}, now=0)
    # legion on #662: not "at the start of every beat" -- it follows the settled block and rotates out
    assert ok and f"until {bt.CLOSED_SHOWN} newer closings replace it" in msg, msg
    shown = bt.render_closed(h)
    assert shown.startswith("## Lines of work you closed")
    assert "widget, daemon: The daemon is fine; it was never down." in shown
    assert "Is the widget daemon running?" not in shown, "the retired entries stay retired"
    from sage.gateway.heartbeat import own_state
    state = own_state(h, "sprout-being", body_reading={})
    assert "The daemon is fine; it was never down." in state
    assert state.index("## Lines of work you closed") > state.index("## What you have settled")


def test_the_closed_block_shows_the_newest_few_and_counts_the_rest(tmp_path):
    h = _home(tmp_path)
    reasons = []
    for i, w in enumerate(("lantern", "kettle", "compass", "teapot", "harbour")):
        assert st.settle(h, {"question": f"Where is the {w}?", "answer": "here"}, now=0)[0]
        reasons.append(f"closed number {i}")
        ok, msg, _ = _go(h, {"words": w, "reason": reasons[-1]}, now=86400 * i)
        assert ok and "1 settled entry" in msg, msg
    shown = bt.render_closed(h)
    lines = shown.splitlines()[1:]
    assert len(lines) == bt.CLOSED_SHOWN + 1 and lines[-1].startswith("- … 1 earlier")
    assert "closed number 4" in lines[0] and "closed number 0" not in shown, "newest first"


def test_a_long_reason_is_cut_and_an_unreadable_retired_file_is_skipped(tmp_path):
    h = _home(tmp_path)
    _go(h, {"words": "widget", "reason": "x" * 500}, now=0)
    (h / "todo.retired-thread-0123456789ab.md").write_text("not a retire header\n")
    shown = bt.render_closed(h)
    assert len(shown.splitlines()) == 2 and shown.endswith("…")


def test_long_topic_words_are_cut_like_the_reason(tmp_path):
    # legion on #662: cbp-being's longest topic words ran 598 chars, a whole todo sentence over its reason
    h = _home(tmp_path)
    words = "widget, " + ", ".join(f"topicword{i}" for i in range(30))
    ok, msg, _ = _go(h, {"words": words, "reason": "short reason"}, now=0)
    assert ok, msg
    line = bt.render_closed(h).splitlines()[1]
    assert "…: short reason" in line and len(line.split(": short reason")[0]) == len("- 1970-01-01 00:00Z, ") + bt.CLOSED_WORDS_CHARS, line


def test_a_closing_by_a_dotted_name_is_still_shown(tmp_path):
    # McNugget on #662: "[^.]*" before ". Topic words" hid any closing whose `by` held a dot
    h = _home(tmp_path)
    ok, msg, _ = bt.retire_thread(h, {"words": "installer", "reason": "done with it"}, by="seat.v0.3")
    assert ok, msg
    assert "installer: done with it" in bt.render_closed(h)


# --- Failure-path coverage salvaged from codex/619-failure-test (NOVA, 2026-11-01), adapted to the
# implementation that landed in dae8b2355. Each test pins one way a retire can fail part-way and checks
# that the recovery evidence survives and the failure is not reported as a no-op.

def _confirmed(h, args):
    """The retire call main requires: the same args plus the confirmation its preview returned."""
    ok, msg, _ = bt.retire_thread(h, dict(args, preview="true"))
    assert ok, msg
    m = re.search(r"confirmation: ([A-Za-z0-9_-]{22})", msg)
    return dict(args, **({"confirmation": m.group(1)} if m else {}))

def test_a_failed_settled_rollback_preserves_recovery_evidence(tmp_path, monkeypatch):
    """A failed commit can mean the settled replacement happened but its undo failed."""
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
    call = _confirmed(h, args)   # preview first, before any failure is injected
    original = (h / st.SETTLED_FILE).read_bytes()

    def commit_with_failed_undo(instance, entries, nxt, log, now, msg):
        # The documented _commit outcome: the replacement landed, logging failed, and restoring
        # the prior settled bytes failed too.
        (Path(instance) / st.SETTLED_FILE).write_text(json.dumps({"next": nxt, "entries": entries}))
        return False, "the change was made but could not be recorded and could not be undone"

    monkeypatch.setattr(st, "_commit", commit_with_failed_undo)
    ok, msg, changed = bt.retire_thread(h, call)
    assert not ok and (h / st.SETTLED_FILE).read_bytes() != original
    assert (h / bt.archive_name(args)).exists(), "partial-effect recovery evidence must survive"
    assert "nothing was retired" not in msg.lower(), "an unknown or partial effect is not a no-op"
    assert changed, "the caller must not record a partial effect as unchanged"
    archive = (h / bt.archive_name(args)).read_text()
    encoded = archive.split("## Exact prior settled.json (base64, for recovery)\n\n", 1)[1].splitlines()[0]
    assert base64.b64decode(encoded) == original


def test_real_settled_log_and_restore_failures_do_not_erase_recovery(tmp_path, monkeypatch):
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
    call = _confirmed(h, args)   # preview first, before any failure is injected
    original = (h / st.SETTLED_FILE).read_bytes()
    real_open, real_write_bytes = builtins.open, Path.write_bytes

    def fail_log(path, mode="r", *a, **kw):
        if Path(path) == h / st.SETTLED_LOG and mode == "a":
            raise OSError("synthetic audit-log failure")
        return real_open(path, mode, *a, **kw)

    def fail_settled_restore(path, data):
        if path == h / st.SETTLED_FILE:
            raise OSError("synthetic restore failure")
        return real_write_bytes(path, data)

    monkeypatch.setattr(builtins, "open", fail_log)
    monkeypatch.setattr(Path, "write_bytes", fail_settled_restore)
    ok, msg, changed = bt.retire_thread(h, call)
    assert not ok and (h / st.SETTLED_FILE).read_bytes() != original
    assert "could not be undone" in msg
    assert (h / bt.archive_name(args)).exists(), "partial-effect recovery evidence must survive"
    assert "nothing was retired" not in msg.lower()
    assert changed


def test_todo_restore_failure_preserves_archive_and_reports_partial_effect(tmp_path, monkeypatch):
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
    call = _confirmed(h, args)   # preview first, before any failure is injected
    real_write = bt._write_atomic
    todo_writes = 0

    def fail_todo_restore(path, text):
        nonlocal todo_writes
        if path == h / bt.TODO:
            todo_writes += 1
            if todo_writes == 2:
                raise OSError("synthetic todo restore failure")
        return real_write(path, text)

    monkeypatch.setattr(bt, "_write_atomic", fail_todo_restore)
    monkeypatch.setattr(st, "_commit", lambda *a, **kw: (False, "synthetic commit failure"))
    ok, msg, changed = bt.retire_thread(h, call)
    assert not ok and changed and todo_writes == 2
    assert "could NOT be restored" in msg and "may be partial" in msg
    assert (h / bt.TODO).read_text() != TODO
    archive = (h / bt.archive_name(args)).read_text()
    assert TODO in archive
