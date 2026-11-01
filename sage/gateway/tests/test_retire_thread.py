"""retire_thread: close a whole line of work at once (being_threads). dp, 2026-11-01, to cbp-being: "retire
the whole hestia thread and work on something different" -- 550 of its 584 open todo items and 29 of its
30 settled entries were on that thread, and retire_note / settle could only move one at a time."""
import builtins
import io
import json
import os
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


def _open(h):
    return [t for t, _ in _todo_items((h / "todo.md").read_text()).values()]


def test_a_thread_leaves_the_todo_and_the_settled_list_and_the_rest_stays(tmp_path):
    h = _home(tmp_path)
    ok, msg, changed = bt.retire_thread(h, {"words": "widget, daemon", "reason": "dp: drop it"}, now=0)
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
    bt.retire_thread(h, {"words": "widget", "reason": "r"}, now=0)
    after = {t: s for t, s in _todo_items((h / "todo.md").read_text()).values()}
    assert after and all(before[t] == s for t, s in after.items())


def test_recall_still_finds_what_was_retired(tmp_path):
    h = _home(tmp_path)
    bt.retire_thread(h, {"words": "widget", "reason": "r"}, now=0)
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
    args = {"words": "widget", "reason": "r"}
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
    w = _Writes(monkeypatch)
    assert bt.retire_thread(h, mine)[0]
    assert w.paths <= declared, w.paths - declared
    # the same call landing first takes the declared name: the second is refused and writes nothing
    (tmp_path / "two").mkdir()
    h2 = _home(tmp_path / "two")
    declared = _declared(h2, mine)
    monkeypatch.undo()
    assert bt.retire_thread(h2, mine)[0]
    (h2 / "todo.md").write_text(TODO)           # the thread crept back before the second ran
    w = _Writes(monkeypatch)
    ok, msg, _ = bt.retire_thread(h2, mine)
    assert not ok and "Give a different reason" in msg
    assert not (w.paths - {os.path.realpath(h2 / ".home.lock")}), w.paths


def test_a_failed_settled_commit_rolls_back_within_the_declared_paths(tmp_path, monkeypatch):
    h = _home(tmp_path)
    args = {"words": "widget", "reason": "r"}
    declared = _declared(h, args)
    entries_before = (h / "settled.json").read_bytes()
    monkeypatch.setattr(st, "_commit", lambda *a, **k: (False, "could not write settled.json (OSError)"))
    w = _Writes(monkeypatch)
    ok, msg, changed = bt.retire_thread(h, args)
    assert not ok and not changed and "put back as it was" in msg
    assert (h / "todo.md").read_text() == TODO and (h / "settled.json").read_bytes() == entries_before
    assert not (h / bt.archive_name(args)).exists()
    assert w.paths <= declared, w.paths - declared


def test_the_verb_retires_and_witnesses():
    FakeMcp.calls = []
    root = Path(tempfile.mkdtemp(prefix="rt-"))
    d = HestiaF1aDispatcher("sprout-being", str(root), mcp_factory=lambda ep, pid: FakeMcp(ep, pid))
    _home(root)
    env = d(BeingIntent("retire_thread", {"words": "widget", "reason": "finished"}), _ALLOW)
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
