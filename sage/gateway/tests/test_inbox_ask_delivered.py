"""An ask arrives with what it says (dp 2026-10-11, option (b)): the courier copies the pointed-to document
from the fleet's shared checkout into the envelope it writes in the being's home, and the beat shows an
unopened ask's words from that envelope. Measured on HUB first: hub-being peeked 17 notices a beat and made
0 memory_read calls in 328 tool calls, so a pointer alone was an ask never read.

The courier copies ONLY from shared-context, and the beat reads ONLY the being's own home."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from sage.gateway import being_inbox_drain as d  # noqa: E402
from sage.gateway import heartbeat as hb  # noqa: E402


def _ws(tmp_path):
    """<root>/sage (the workspace), <root>/shared-context, <root>/private-context, and a being home."""
    root = tmp_path / "ai"
    (root / "sage").mkdir(parents=True)
    (root / "shared-context" / "forum").mkdir(parents=True)
    (root / "private-context").mkdir()
    home = root / "sage" / "sage" / "instances" / "b-being"
    home.mkdir(parents=True)
    return root, str(root / "sage"), home


def test_the_courier_copies_a_shared_context_document(tmp_path):
    root, ws, _ = _ws(tmp_path)
    (root / "shared-context/forum/ask.md").write_text("cbp-being asks: what do you notice in your room?")
    got = d.delivered_content("shared-context/forum/ask.md#thread=x", ws)
    assert got["text"].startswith("cbp-being asks") and not got["truncated"]


def test_the_courier_copies_nothing_outside_shared_context(tmp_path):
    root, ws, _ = _ws(tmp_path)
    (root / "private-context/secret.md").write_text("private")
    (root / "shared-context/forum/tool.py").write_text("code")
    os.symlink(root / "private-context/secret.md", root / "shared-context/forum/link.md")
    for ptr in ("private-context/secret.md", "shared-context/../private-context/secret.md",
                "shared-context/forum/link.md", "https://github.com/dp-web4/SAGE/pull/1",
                "shared-context/forum/tool.py", "/etc/passwd", ""):
        got = d.delivered_content(ptr, ws)
        assert "text" not in got and got["why"], ptr
    assert "not in this machine's copy" in d.delivered_content("shared-context/forum/absent.md", ws)["why"]


def test_a_long_document_is_capped_and_says_so(tmp_path):
    root, ws, home = _ws(tmp_path)
    (root / "shared-context/forum/long.md").write_text("x" * (d.DELIVERED_CHARS + 500))
    got = d.delivered_content("shared-context/forum/long.md", ws)
    assert len(got["text"]) == d.DELIVERED_CHARS and got["truncated"]
    p = d.persist_notice(home, {"id": "n1", "kind": "coordination", "from": "u",
                                "pointer_uri": "shared-context/forum/long.md"}, "seat", workspace=ws)
    assert f"first {d.DELIVERED_CHARS} of {d.DELIVERED_CHARS + 500}" in p.read_text()


def test_the_envelope_carries_the_words_labelled_as_the_senders_or_says_why_not(tmp_path):
    root, ws, home = _ws(tmp_path)
    (root / "shared-context/forum/ask.md").write_text("Is your drain stalled?")
    p = d.persist_notice(home, {"id": "n1", "kind": "coordination", "from": "u",
                                "pointer_uri": "shared-context/forum/ask.md"}, "hub-claude", workspace=ws)
    t = p.read_text()
    assert d.DELIVERED_HEADING in t and "the sender's words" in t and "Is your drain stalled?" in t
    q = d.persist_notice(home, {"id": "n2", "kind": "reply", "from": "u",
                                "pointer_uri": "https://github.com/x/y/pull/1"}, "hub-claude", workspace=ws)
    assert d.DELIVERED_HEADING not in q.read_text() and "did not copy what it says" in q.read_text()


def _notice(i, kind, ptr):
    return {"id": i, "kind": kind, "from_plugin": "claude-code", "pointer_uri": ptr, "queued_at": "2026-10-11T10:00"}


def test_the_beat_shows_what_an_unopened_ask_says_from_the_beings_home(tmp_path):
    root, ws, home = _ws(tmp_path)
    (root / "shared-context/forum/ask.md").write_text("cbp-being asks:\n\n  is your drain stalled?")
    p = d.persist_notice(home, {"id": "n1", "kind": "coordination", "from": "u",
                                "pointer_uri": "shared-context/forum/ask.md"}, "hub-claude", workspace=ws)
    ptr = f"sage/instances/b-being/notes/inbox/{p.name}"
    out = hb.render_inbox([_notice(7, "coordination", ptr)], home=home)
    assert "It says (the sender's words" in out and "cbp-being asks: is your drain stalled?" in out
    assert f"memory_read on {ptr}" in out                       # the full text stays one read away
    # handled -> folded, nothing inlined
    assert "It says" not in hb.render_inbox([_notice(7, "coordination", ptr)], handled={7}, home=home)
    # without the home the beat reads nothing
    assert "It says" not in hb.render_inbox([_notice(7, "coordination", ptr)])


def test_at_most_two_asks_are_inlined_and_only_asks(tmp_path):
    root, ws, home = _ws(tmp_path)
    ns = []
    for i in range(4):
        (root / f"shared-context/forum/a{i}.md").write_text(f"ask number {i}")
        p = d.persist_notice(home, {"id": f"n{i}", "kind": "reply", "from": "u",
                                    "pointer_uri": f"shared-context/forum/a{i}.md"}, "s", workspace=ws)
        ns.append(_notice(10 + i, "reply", f"sage/instances/b-being/notes/inbox/{p.name}"))
    ns.append(_notice(20, "forum-note", ns[0]["pointer_uri"]))
    out = hb.render_inbox(ns, home=home)
    assert out.count("It says") == hb.INLINE_ASKS
    assert "ask number 3" in out and "ask number 2" in out      # newest first


def test_an_envelope_outside_the_beings_inbox_is_never_read(tmp_path):
    _, _, home = _ws(tmp_path)
    (tmp_path / "elsewhere.md").write_text(f"{d.DELIVERED_HEADING}\n\n~~~~\nnot yours\n~~~~\n")
    assert hb.delivered_excerpt(home, str(tmp_path / "elsewhere.md")) == ""
    assert hb.delivered_excerpt(home, "sage/instances/b-being/notes/inbox/../../../elsewhere.md") == ""


def test_the_drain_delivers_the_words_end_to_end(tmp_path):
    root, ws, home = _ws(tmp_path)
    (root / "shared-context/forum/ask.md").write_text("hello from cbp-being")
    sent = []
    out = d.drain_once(home, "unused", workspace=ws, member="b-being", relayed_by="seat",
                       fetch=lambda: [{"id": "n9", "kind": "coordination", "from": "u",
                                       "pointer_uri": "shared-context/forum/ask.md"}],
                       notify=lambda k, p: sent.append(p) or {"ok": True})
    assert out["persisted"] == 1 and out["notified"] == 1
    assert "/notes/inbox/" in sent[0]
    assert "hello from cbp-being" in hb.delivered_excerpt(home, sent[0])


def test_an_envelope_relayed_before_the_post_arrived_is_completed_on_a_later_pass(tmp_path):
    """HUB 2026-10-14: 0 of 19 inlined. The notice beat the shared-context pull, the copy ran once and lost."""
    root, ws, home = _ws(tmp_path)
    ask = {"id": "n1", "kind": "coordination", "from": "u", "pointer_uri": "shared-context/forum/late.md#thread=t"}
    out = d.drain_once(home, "unused", workspace=ws, member="b-being", relayed_by="seat",
                       fetch=lambda: [ask], notify=lambda k, p: {"ok": True})
    env = next((home / "notes/inbox").glob("*.md"))
    assert out["persisted"] == 1 and d.DELIVERED_HEADING not in env.read_text()
    again = d.drain_once(home, "unused", workspace=ws, fetch=lambda: [], notify=lambda k, p: {"ok": True})
    assert again["pending"] == 1 and again["completed"] == 0          # still not here: keeps waiting
    (root / "shared-context/forum/late.md").write_text("cbp-being asks: are you there?")
    told = []
    later = d.drain_once(home, "unused", workspace=ws, relayed_by="seat",
                         fetch=lambda: (_ for _ in ()).throw(RuntimeError("hub down")),
                         notify=lambda k, p: told.append((k, p)) or {"ok": True})
    t = env.read_text()
    assert later["completed"] == 1 and later["pending"] == 0           # even when the hub read fails
    assert later["completion_notified"] == 1 and len(told) == 1         # and the being is told again
    assert d.DELIVERED_HEADING in t and "on a later pass" in t and "did not copy" not in t
    assert t.startswith("---\nkind: coordination") and "hub_notice_id: n1" in t   # the same envelope
    assert "are you there?" in hb.delivered_excerpt(home, f"sage/instances/b-being/notes/inbox/{env.name}")
    assert d.complete_pending(home, ws, "seat") == {"completed": 0, "pending": 0, "errors": []}  # once


def test_only_the_not_yet_reason_is_retried_and_pre_424_envelopes_are_left_alone(tmp_path):
    root, ws, home = _ws(tmp_path)
    inbox = home / "notes/inbox"
    inbox.mkdir(parents=True)
    (root / "shared-context/forum/x.md").write_text("words")
    old = "---\nkind: reply\npointer: shared-context/forum/x.md\n---\n\n# A notice addressed to you on the hub\n"
    (inbox / "old.md").write_text(old)                                # pre-#424: pointer only, no reason line
    d.persist_notice(home, {"id": "n2", "kind": "reply", "from": "u",
                            "pointer_uri": "https://github.com/x/y/pull/1"}, "seat", workspace=ws)
    assert d.complete_pending(home, ws, "seat") == {"completed": 0, "pending": 0, "errors": []}
    assert (inbox / "old.md").read_text() == old


def _late_envelope(tmp_path):
    """An envelope relayed before its post arrived, its first notice already sent (and so consumed)."""
    root, ws, home = _ws(tmp_path)
    ask = {"id": "n9", "kind": "coordination", "from": "u", "pointer_uri": "shared-context/forum/l9.md"}
    first = []
    d.drain_once(home, "unused", workspace=ws, member="b-being", fetch=lambda: [ask],
                 notify=lambda k, p: first.append((k, p)) or {"ok": True})
    assert len(first) == 1
    (root / "shared-context/forum/l9.md").write_text("late words")
    return root, ws, home, first[0]


def test_a_late_completion_is_notified_exactly_once_through_the_first_notices_channel(tmp_path):
    """Nova's hold on #452: a completion after the first notice was consumed must reach the being."""
    _, ws, home, first = _late_envelope(tmp_path)
    told = []
    rec = lambda k, p: told.append((k, p)) or {"ok": True}  # noqa: E731
    out = d.drain_once(home, "unused", workspace=ws, member="b-being", fetch=lambda: [], notify=rec)
    assert out["completed"] == 1 and out["completion_notified"] == 1
    assert told == [first]                                   # same kind, same envelope pointer
    env = next((home / "notes/inbox").glob("*.md"))
    assert "completion_notified: " in env.read_text().split("\n---\n", 1)[0]
    for _ in range(2):                                       # later passes stay quiet
        again = d.drain_once(home, "unused", workspace=ws, fetch=lambda: [], notify=rec)
        assert again["completed"] == 0 and again["completion_notified"] == 0
    assert len(told) == 1
    assert "late words" in hb.delivered_excerpt(home, f"sage/instances/b-being/notes/inbox/{env.name}")


def test_a_failed_completion_notice_is_retried_and_then_sent_once(tmp_path):
    _, ws, home, _ = _late_envelope(tmp_path)
    down = d.drain_once(home, "unused", workspace=ws, fetch=lambda: [],
                        notify=lambda k, p: {"ok": False, "error": "daemon down"})
    assert down["completed"] == 1 and down["completion_notified"] == 0
    env = next((home / "notes/inbox").glob("*.md"))
    assert "completion_notified: " not in env.read_text()      # not marked: still owed
    told = []
    up = d.drain_once(home, "unused", workspace=ws, fetch=lambda: [],
                      notify=lambda k, p: told.append(p) or {"ok": True})
    assert up["completed"] == 0 and up["completion_notified"] == 1 and len(told) == 1


def test_envelopes_complete_at_relay_time_or_pre_424_get_no_completion_notice(tmp_path):
    root, ws, home = _ws(tmp_path)
    (root / "shared-context/forum/here.md").write_text("already here")
    inbox = home / "notes/inbox"
    told = []
    rec = lambda k, p: told.append(p) or {"ok": True}  # noqa: E731
    d.drain_once(home, "unused", workspace=ws, member="b-being", notify=rec,
                 fetch=lambda: [{"id": "n3", "kind": "reply", "from": "u", "pointer_uri": "shared-context/forum/here.md"}])
    (inbox / "old.md").write_text("---\nkind: reply\npointer: shared-context/forum/here.md\n---\n\n# old\n")
    assert len(told) == 1                                    # the first notice only
    out = d.drain_once(home, "unused", workspace=ws, fetch=lambda: [], notify=rec)
    assert out["completion_notified"] == 0 and len(told) == 1
