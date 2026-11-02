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
from types import SimpleNamespace
from pathlib import Path

import pytest

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


def _open(h):
    return [t for t, _ in _todo_items((h / "todo.md").read_text()).values()]


def _broad_home(tmp_path):
    (tmp_path / "todo.md").write_text(
        "2026-10-30 09:00 UTC\n" + "".join(f"- [ ] widget task {n}\n" for n in range(6))
        + "- [ ] unrelated task\n")
    return tmp_path


def _preview_confirmation(h, args):
    preview = bt.retire_thread(h, {**args, "preview": "true"})
    assert preview[0] and not preview[2], preview
    assert "same beat" in preview[1] and "different worker" in preview[1]
    match = re.search(r"confirmation: ([0-9a-f]{64})", preview[1])
    assert match, preview[1]
    return match.group(1)


def _confirmed_if_broad(h, args):
    preview = bt.retire_thread(h, {**args, "preview": "true"})
    assert preview[0] and not preview[2], preview
    match = re.search(r"confirmation: ([0-9a-f]{64})", preview[1])
    return {**args, "confirmation": match.group(1)} if match else args


@pytest.mark.parametrize("word", ["the", "AND", "for"])
def test_common_stopwords_cannot_retire_or_preview_everything(tmp_path, word):
    h = _broad_home(tmp_path)
    before = (h / bt.TODO).read_bytes()
    for extra in ({"preview": "true"}, {"reason": "finished"}):
        ok, message, changed = bt.retire_thread(h, {"words": word, **extra})
        assert not ok and not changed and "stopword" in message.lower()
    assert (h / bt.TODO).read_bytes() == before
    assert not (h / ".home.lock").exists()


def test_broad_retire_requires_single_use_preview_bound_to_snapshot(tmp_path):
    h = _broad_home(tmp_path)
    args = {"words": "widget", "reason": "finished"}
    before = (h / bt.TODO).read_bytes()
    ok, message, changed = bt.retire_thread(h, args)
    assert not ok and not changed and "preview" in message.lower()
    assert (h / bt.TODO).read_bytes() == before
    token = _preview_confirmation(h, args)
    ok, message, changed = bt.retire_thread(h, {**args, "confirmation": token})
    assert ok and changed, message
    # Replay cannot authorize another act, even when the archive is removed.
    (h / bt.TODO).write_bytes(before)
    (h / bt.archive_name(args)).unlink()
    replay = bt.retire_thread(h, {**args, "confirmation": token})
    assert not replay[0] and not replay[2]


def test_confirmation_expires_and_is_not_durable(tmp_path, monkeypatch):
    h = _broad_home(tmp_path)
    args = {"words": "widget", "reason": "finished"}
    clock = SimpleNamespace(monotonic=lambda: 100.0)
    monkeypatch.setattr(bt, "time", clock)
    token = _preview_confirmation(h, args)
    clock.monotonic = lambda: 100.0 + bt._PREVIEW_TTL
    assert not bt.retire_thread(h, {**args, "confirmation": token})[0]
    token = _preview_confirmation(h, args)
    with bt._preview_lock:
        bt._previews.clear()  # process restart loses pending confirmations
    assert not bt.retire_thread(h, {**args, "confirmation": token})[0]


def test_confirmation_is_bound_to_the_home_and_preview_needs_reason(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _broad_home(first)
    _broad_home(second)
    preview = bt.retire_thread(first, {"words": "widget", "preview": "true"})
    assert preview[0] and "confirmation: " not in preview[1]
    args = {"words": "widget", "reason": "finished"}
    token = _preview_confirmation(first, args)
    ok, _, changed = bt.retire_thread(second, {**args, "confirmation": token})
    assert not ok and not changed
    assert not (second / bt.archive_name(args)).exists()


def test_broad_refusal_explains_missing_unknown_and_changed_confirmation(tmp_path):
    h = _broad_home(tmp_path)
    args = {"words": "widget", "reason": "finished"}
    missing = bt.retire_thread(h, args)
    assert not missing[0] and "no confirmation" in missing[1].lower()
    unknown = bt.retire_thread(h, {**args, "confirmation": "not-a-confirmation"})
    assert not unknown[0] and "unknown or expired" in unknown[1].lower()
    token = _preview_confirmation(h, args)
    changed = bt.retire_thread(h, {**args, "reason": "different", "confirmation": token})
    assert not changed[0] and "changed" in changed[1].lower() and "preview" in changed[1].lower()
    consumed = bt.retire_thread(h, {**args, "confirmation": token})
    assert not consumed[0] and "unknown or expired" in consumed[1].lower()


def test_one_item_is_not_classed_as_a_broad_retirement(tmp_path):
    (tmp_path / bt.TODO).write_text("2026-10-30 09:00 UTC\n- [ ] widget task\n")
    ok, _, changed = bt.retire_thread(tmp_path, {"words": "widget", "reason": "finished"})
    assert ok and changed


@pytest.mark.parametrize("changed", ["todo", "settled", "reason", "words"])
def test_broad_confirmation_refuses_changed_snapshot_or_request(tmp_path, changed):
    h = _broad_home(tmp_path)
    args = {"words": "widget", "reason": "finished"}
    token = _preview_confirmation(h, args)
    if changed == "todo":
        with (h / bt.TODO).open("a") as stream:
            stream.write("- [ ] unrelated new item\n")
    elif changed == "settled":
        assert st.settle(h, {"question": "new fact?", "answer": "yes"})[0]
    else:
        args[changed] = "different" if changed == "reason" else "unrelated"
    before = (h / bt.TODO).read_bytes()
    ok, message, applied = bt.retire_thread(h, {**args, "confirmation": token})
    assert not ok and not applied and "preview" in message.lower()
    assert (h / bt.TODO).read_bytes() == before
    assert not (h / bt.archive_name(args)).exists()


def test_settled_evidence_is_not_a_topic_selector(tmp_path):
    # Two conclusions share provenance; only one is actually about the topic.
    assert st.settle(tmp_path, {"question": "Can recall find old work?", "answer": "yes",
                                "evidence": "journal.md"}, now=0)[0]
    assert st.settle(tmp_path, {"question": "Do apple trees grow?", "answer": "yes",
                                "evidence": "recall(idx:4), journal.md"}, now=1)[0]
    before = (tmp_path / st.SETTLED_FILE).read_bytes()
    preview = bt.retire_thread(tmp_path, {"words": "recall", "preview": "true"})
    assert preview[0] and "1 of 2 settled" in preview[1]
    assert (tmp_path / st.SETTLED_FILE).read_bytes() == before
    ok, message, changed = bt.retire_thread(tmp_path, {"words": "recall", "reason": "finished"})
    assert ok and changed, message
    remaining, _, error = st.read(tmp_path)
    assert error is None and [e["question"] for e in remaining] == ["Do apple trees grow?"]


def test_a_thread_leaves_the_todo_and_the_settled_list_and_the_rest_stays(tmp_path):
    h = _home(tmp_path)
    args = {"words": "widget, daemon", "reason": "dp: drop it"}
    ok, msg, changed = bt.retire_thread(h, _confirmed_if_broad(h, args), now=0)
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
    assert bt.retire_thread(h, _confirmed_if_broad(h, {"words": "widget", "reason": "r"}), now=0)[0]
    after = {t: s for t, s in _todo_items((h / "todo.md").read_text()).values()}
    assert after and all(before[t] == s for t, s in after.items())


def test_recall_still_finds_what_was_retired(tmp_path):
    h = _home(tmp_path)
    assert bt.retire_thread(h, _confirmed_if_broad(h, {"words": "widget", "reason": "r"}), now=0)[0]
    hits = search_home(h, "widget installer")
    assert any(r["source"].startswith("todo.retired-") for r in hits), hits


def test_a_preview_changes_nothing_and_says_what_would_move(tmp_path):
    h = _home(tmp_path)
    before = {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()}
    ok, msg, changed = bt.retire_thread(h, {"words": "widget", "preview": "true"}, now=0)
    assert ok and not changed and msg.startswith("PREVIEW, no files or records were changed")
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
    assert bt.retire_thread(h, a, now=0)[0] and bt.retire_thread(h, b, now=0)[0]
    assert (h / bt.archive_name(a)).exists() and (h / bt.archive_name(b)).exists()
    (h / "todo.md").write_text(TODO)            # the thread crept back; the same call again
    before = {p.name: p.read_bytes() for p in h.iterdir() if p.is_file()}
    ok, msg, changed = bt.retire_thread(h, a, now=0)
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
    args = _confirmed_if_broad(h, {"words": "widget", "reason": "r"})
    assert thread_paths({"words": "widget", "preview": "true"}, {"memory_root": str(h)}) == []
    declared = _declared(h, args)
    w = _Writes(monkeypatch)
    assert bt.retire_thread(h, args)[0]
    assert os.path.realpath(h / f".{bt.archive_name(args)}.tmp") in w.paths, "the temp is exercised"
    assert w.paths and w.paths <= declared, w.paths - declared


def test_an_interleaved_retire_cannot_move_this_one_off_its_declared_paths(tmp_path, monkeypatch):
    h = _home(tmp_path)
    mine, other = {"words": "widget", "reason": "mine"}, {"words": "daemon", "reason": "other"}
    declared = _declared(h, mine)               # the gate is told, then another retire lands first
    assert bt.retire_thread(h, other)[0]
    mine = _confirmed_if_broad(h, mine)
    w = _Writes(monkeypatch)
    assert bt.retire_thread(h, mine)[0]
    assert w.paths <= declared, w.paths - declared
    # the same call landing first takes the declared name: the second is refused and writes nothing
    (tmp_path / "two").mkdir()
    h2 = _home(tmp_path / "two")
    declared = _declared(h2, mine)
    monkeypatch.undo()
    mine = _confirmed_if_broad(h2, {"words": "widget", "reason": "mine"})
    assert bt.retire_thread(h2, mine)[0]
    (h2 / "todo.md").write_text(TODO)           # the thread crept back before the second ran
    mine = _confirmed_if_broad(h2, {"words": "widget", "reason": "mine"})
    w = _Writes(monkeypatch)
    ok, msg, _ = bt.retire_thread(h2, mine)
    assert not ok and "Give a different reason" in msg
    assert not (w.paths - {os.path.realpath(h2 / ".home.lock")}), w.paths


def test_a_failed_settled_commit_rolls_back_within_the_declared_paths(tmp_path, monkeypatch):
    h = _home(tmp_path)
    args = _confirmed_if_broad(h, {"words": "widget", "reason": "r"})
    declared = _declared(h, args)
    entries_before = (h / "settled.json").read_bytes()
    monkeypatch.setattr(st, "_commit", lambda *a, **k: (False, "could not write settled.json (OSError)"))
    w = _Writes(monkeypatch)
    ok, msg, changed = bt.retire_thread(h, args)
    assert not ok and changed and "todo was restored" in msg and "may be partial" in msg
    assert (h / "todo.md").read_text() == TODO and (h / "settled.json").read_bytes() == entries_before
    assert (h / bt.archive_name(args)).exists()
    assert w.paths <= declared, w.paths - declared


def test_a_failed_settled_rollback_preserves_recovery_evidence(tmp_path, monkeypatch):
    """A failed commit can mean the settled replacement happened but undo failed."""
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
    original = (h / "settled.json").read_bytes()

    def commit_with_failed_undo(instance, entries, nxt, log, now, msg):
        # Model the documented _commit outcome where the replacement landed,
        # logging failed, and restoring the prior settled bytes failed too.
        (Path(instance) / st.SETTLED_FILE).write_text(json.dumps({"next": nxt, "entries": entries}))
        return False, "the change was made but could not be recorded and could not be undone"

    monkeypatch.setattr(st, "_commit", commit_with_failed_undo)
    ok, msg, changed = bt.retire_thread(h, args)
    assert not ok and (h / "settled.json").read_bytes() != original
    assert (h / bt.archive_name(args)).exists(), "partial-effect recovery evidence must survive"
    assert "nothing was retired" not in msg.lower(), "unknown or partial effect is not a no-op"
    assert changed, "caller must not record a partial effect as unchanged"
    archive = (h / bt.archive_name(args)).read_text()
    encoded = archive.split("## Original settled snapshot (base64; exact bytes)\n\n", 1)[1].splitlines()[0]
    assert base64.b64decode(encoded) == original


def test_real_settled_log_and_restore_failures_do_not_erase_recovery(tmp_path, monkeypatch):
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
    original = (h / st.SETTLED_FILE).read_bytes()
    real_open, real_write_bytes = builtins.open, Path.write_bytes

    def fail_log(path, mode="r", *args, **kwargs):
        if Path(path) == h / st.SETTLED_LOG and mode == "a":
            raise OSError("synthetic audit-log failure")
        return real_open(path, mode, *args, **kwargs)

    def fail_settled_restore(path, data):
        if path == h / st.SETTLED_FILE:
            raise OSError("synthetic restore failure")
        return real_write_bytes(path, data)

    monkeypatch.setattr(builtins, "open", fail_log)
    monkeypatch.setattr(Path, "write_bytes", fail_settled_restore)
    ok, msg, changed = bt.retire_thread(h, args)
    assert not ok and (h / st.SETTLED_FILE).read_bytes() != original
    assert "could not be undone" in msg
    assert (h / bt.archive_name(args)).exists(), "partial-effect recovery evidence must survive"
    assert "nothing was retired" not in msg.lower()
    assert changed


def test_todo_restore_failure_preserves_archive_and_reports_partial_effect(tmp_path, monkeypatch):
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
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
    ok, msg, changed = bt.retire_thread(h, args)
    assert not ok and changed and todo_writes == 2
    assert "todo restoration failed" in msg and "may be partial" in msg
    assert (h / bt.TODO).read_text() != TODO
    archive = (h / bt.archive_name(args)).read_text()
    assert TODO in archive


@pytest.mark.parametrize("stage", ["archive", "todo"])
def test_write_failure_reports_partial_and_preserves_available_evidence(tmp_path, monkeypatch, stage):
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
    original_todo, original_settled = (h / bt.TODO).read_bytes(), (h / st.SETTLED_FILE).read_bytes()
    target = h / (bt.archive_name(args) if stage == "archive" else bt.TODO)
    real_replace = os.replace

    def fail_one_replace(src, dst, *a, **kw):
        if Path(dst) == target:
            raise OSError("synthetic replace failure")
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(os, "replace", fail_one_replace)
    ok, msg, changed = bt.retire_thread(h, args)
    assert not ok and changed and "may be partial" in msg and "Do not retry blindly" in msg
    assert (h / bt.TODO).read_bytes() == original_todo
    assert (h / st.SETTLED_FILE).read_bytes() == original_settled
    # An archive replacement failure leaves the written temp for recovery; a
    # later todo replacement failure keeps the already committed archive.
    evidence = h / (bt._tmp(bt.archive_name(args)) if stage == "archive" else bt.archive_name(args))
    assert evidence.exists()


def test_the_verb_retires_and_witnesses():
    FakeMcp.calls = []
    root = Path(tempfile.mkdtemp(prefix="rt-"))
    d = HestiaF1aDispatcher("sprout-being", str(root), mcp_factory=lambda ep, pid: FakeMcp(ep, pid))
    _home(root)
    args = _confirmed_if_broad(root, {"words": "widget", "reason": "finished"})
    env = d(BeingIntent("retire_thread", args), _ALLOW)
    assert env.ok and env.witness_id, env.error
    assert "Build a small neural net" in (root / "todo.md").read_text()
    assert "widget" not in (root / "todo.md").read_text().split("UTC:", 1)[-1].lower()


def test_partial_retire_failure_is_witnessed(tmp_path, monkeypatch):
    FakeMcp.calls = []
    _home(tmp_path)
    monkeypatch.setattr(st, "_commit", lambda *a, **k: (False, "synthetic unknown outcome"))
    d = HestiaF1aDispatcher("sprout-being", str(tmp_path), mcp_factory=lambda ep, pid: FakeMcp(ep, pid))
    env = d(BeingIntent("retire_thread", {"words": "widget", "reason": "finished"}), _ALLOW)
    assert not env.ok and "may be partial" in env.error and env.witness_id


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


def test_broad_preview_with_reason_and_confirmation_writes_no_files(tmp_path, monkeypatch):
    _broad_home(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    w = _Writes(monkeypatch)
    token = _preview_confirmation(tmp_path, {"words": "widget", "reason": "finished"})
    assert token and w.paths == set()
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()} == before
    assert not (tmp_path / ".home.lock").exists()
