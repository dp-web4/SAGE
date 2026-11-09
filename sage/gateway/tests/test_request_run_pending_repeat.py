"""request_run: a repeat of a request the seat has not answered yet says so (sprout-being, 2026-10-24..27:
21 of 83 request_runs repeated one still waiting; seqs 1878-1881 asked for one file four times in 12 min)."""
from pathlib import Path

from sage.gateway import conversations as conv
from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_hestia_dispatch import _ALLOW, _disp


def _seat_home():
    d, root = _disp()
    home = Path(root)
    conv.create(home, "seat", title="seat", participants=["seat", "sprout-being"],
                writable_by=["seat", "sprout-being"])
    meta = conv.get_meta(home, "seat"); meta["notify"] = {"seat": "claude-code"}
    conv._write_meta(home, "seat", meta)
    (home / "notes").mkdir(exist_ok=True)
    (home / "notes" / "probe.py").write_text("print('a')\n")
    return d, home


def test_a_repeat_while_waiting_names_the_first_ask_and_is_marked_for_the_seat():
    d, home = _seat_home()
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    assert r.ok and "already_asked" not in r.result
    first = conv.recent(home, "seat", limit=1)[-1]["seq"]
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    assert r.ok and f"seq {first}" in r.result["already_asked"] and "not answered" in r.result["already_asked"]
    assert "minute" in r.result["already_asked"] and "unchanged" not in r.result
    assert f"SAME AS the request at seq {first}" in conv.recent(home, "seat", limit=1)[-1]["text"]
    # a third ask still points at the first one, and counts
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "and again"}), _ALLOW)
    assert f"seq {first}" in r.result["already_asked"] and "1 more time" in r.result["already_asked"]
    assert "asked 3 times" in conv.recent(home, "seat", limit=1)[-1]["text"]


def test_the_annotation_does_not_change_what_the_request_is():
    a = "[request_run] notes/probe.py\nwhy: x\n(11 bytes, sha256:abcdefabcdef; the seat decides)"
    assert conv._request_key(a) == conv._request_key(a + "\nSAME AS the request at seq 4, not yet answered.")


def test_after_the_seat_answers_it_is_unchanged_not_pending():
    d, home = _seat_home()
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    asked = conv.recent(home, "seat", limit=1)[-1]["seq"]
    conv.append(home, "seat", speaker="seat", via="seat",
                text=f"[request_run] Ran notes/probe.py: prints a.\n\nAnswers your request seq {asked}.")
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "third"}), _ALLOW)
    assert "unchanged" in r.result and "already_asked" not in r.result


def test_an_answer_older_than_the_quiet_window_still_answers_the_repeat(monkeypatch):
    # sprout-being 11-09: the seat declined these bytes at seq 2677; 91 turns later each repeat said "not
    # answered in the last 80 turns (asked 10 times now)" and the being concluded the seat was dead. The
    # answer scan reaches past the seat-quiet window, so the old answer is found and carried.
    from sage.gateway import hestia_dispatch as hd
    monkeypatch.setattr(hd, "_PENDING_SCAN", 6)
    d, home = _seat_home()
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    asked = conv.recent(home, "seat", limit=1)[-1]["seq"]
    conv.append(home, "seat", speaker="seat", via="seat",
                text=f"[request_run] I did not run notes/probe.py. It restarts things.\n\nAnswers your request seq {asked}.")
    for i in range(6):
        conv.append(home, "seat", speaker="seat", via="seat", text=f"unrelated {i}")
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    assert "already_asked" not in r.result, r.result
    assert f"the seat answered that at seq {asked + 1}: it did not run it" in r.result["unchanged"]
    assert "It restarts things." in r.result["unchanged"], "the reason is carried, not pointed at"
    assert "not answered" not in conv.recent(home, "seat", limit=1)[-1]["text"]


def test_an_answer_before_the_answer_scan_is_not_reported_as_not_answered_yet(monkeypatch):
    # #567 (cbp on #566): ask -> the seat answers -> the window scrolls -> the same ask again. The answer
    # is out of view, so "not answered yet" would be false; the notes name the window they checked.
    from sage.gateway import hestia_dispatch as hd
    monkeypatch.setattr(hd, "_PENDING_SCAN", 6)
    monkeypatch.setattr(hd, "_ANSWER_SCAN", 6)
    d, home = _seat_home()
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    asked = conv.recent(home, "seat", limit=1)[-1]["seq"]
    conv.append(home, "seat", speaker="seat", via="seat",
                text=f"[request_run] Ran notes/probe.py: prints a.\n\nAnswers your request seq {asked}.")
    for i in range(6):
        conv.append(home, "seat", speaker="seat", via="seat", text=f"unrelated {i}")
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    second = conv.recent(home, "seat", limit=1)[-1]["seq"]
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "and again"}), _ALLOW)
    said = r.result["already_asked"]
    assert f"seq {second}" in said and "not answered it yet" not in said
    assert "in the last 6 turns of 'seat'" in said and "older turns were not checked" in said
    assert "not answered in the last 6 turns" in conv.recent(home, "seat", limit=1)[-1]["text"]


def test_a_short_conversation_still_says_not_yet():
    # the whole conversation is inside the window: nothing older exists, so "yet" is true
    d, home = _seat_home()
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    assert "has not answered it yet" in r.result["already_asked"] and "last 80" not in r.result["already_asked"]


def test_a_different_file_or_an_edit_is_a_new_request():
    d, home = _seat_home()
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    (home / "notes" / "probe.py").write_text("print('b')\n")
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "edited"}), _ALLOW)
    assert "already_asked" not in r.result


def test_a_seat_quiet_through_the_beings_asks_is_named_on_the_receipt(monkeypatch):
    """Hours of seat silence with only "asked" on every receipt reads as a stuck seat. The receipt says how
    long the seat has been quiet, and what that does and does not mean."""
    from sage.gateway import hestia_dispatch as hd
    d, home = _seat_home()
    conv.append(home, "seat", speaker="seat", via="seat", text="hello from the seat")
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    assert "seat_quiet" not in r.result, "minutes of quiet is not news"
    monkeypatch.setattr(hd, "SEAT_QUIET_S", 0)
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "and again"}), _ALLOW)
    q = r.result["seat_quiet"]
    assert "has said nothing in this conversation since" in q and "through 2 of your requests" in q
    assert "away, not stuck" in q and "nothing for you to restart" in q
    assert "wake was sent" in r.result["note"] and "asked and woken" not in r.result["note"]
    assert "can answer" in r.result["note"] and "it answers them" not in q
    assert "no seat answer" not in r.result["note"], "an earlier seat turn is in view; the note may not deny it"


def test_the_quiet_fact_counts_only_since_the_seats_last_word():
    from datetime import datetime, timezone
    from sage.gateway.hestia_dispatch import _seat_quiet
    now = datetime(2026, 11, 3, 6, 0, tzinfo=timezone.utc)
    seat = {"from": "seat", "ts": "2026-11-01T06:00:00Z", "text": "ran it"}
    ask = {"from": "b", "ts": "2026-11-02T00:00:00Z", "text": "[request_run] notes/x.py\nwhy: y"}
    assert "(48 hours), through 2 of your requests" in _seat_quiet([seat, ask, ask], "b", "seat", False, now)
    assert _seat_quiet([seat], "b", "seat", False, now) is None                       # quiet, but nobody asked
    assert _seat_quiet([ask, seat], "b", "seat", False, now) is None                  # it answered after the ask
    fresh = dict(seat, ts="2026-11-03T05:00:00Z")
    assert _seat_quiet([fresh, ask], "b", "seat", False, now) is None                  # an hour is not quiet
    assert _seat_quiet([ask, ask], "b", "seat", False, now) is None                    # a conversation with no seat turn yet
    assert "last 3 turns" in _seat_quiet([ask, ask, ask], "b", "seat", True, now)     # silent through the whole window


def test_operator_message_does_not_reset_seat_silence_clock():
    from datetime import datetime, timezone
    from sage.gateway.hestia_dispatch import _seat_quiet
    now = datetime(2026, 11, 3, 6, 0, tzinfo=timezone.utc)
    seat = {"from": "seat", "ts": "2026-11-01T06:00:00Z", "text": "last seat answer"}
    ask = {"from": "b", "ts": "2026-11-02T00:00:00Z", "text": "[request_run] notes/x.py\\nwhy: y"}
    operator = {"from": "dp", "ts": "2026-11-03T05:59:00Z", "text": "operator check in"}
    q = _seat_quiet([seat, ask, operator, ask], "b", "seat", False, now)
    assert q is not None and "(48 hours)" in q and "through 2 of your requests" in q
    assert _seat_quiet([seat, ask, operator, seat, ask], "b", "seat", False, now) is not None
    assert _seat_quiet([seat, ask, operator, seat], "b", "seat", False, now) is None


def test_quiet_after_an_answer_keeps_that_answer_and_does_not_deny_it(monkeypatch):
    # Codex on #628: the seat answered this file earlier, then went quiet through later, unrelated asks.
    # The receipt carries the earlier answer (unchanged) and the quiet period; the note denies neither.
    from sage.gateway import hestia_dispatch as hd
    d, home = _seat_home()
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    asked = conv.recent(home, "seat", limit=1)[-1]["seq"]
    conv.append(home, "seat", speaker="seat", via="seat",
                text=f"[request_run] Ran notes/probe.py: prints a.\n\nAnswers your request seq {asked}.")
    (home / "notes" / "other.py").write_text("print('o')\n")
    d(BeingIntent("request_run", {"path": "notes/other.py", "why": "unrelated"}), _ALLOW)
    monkeypatch.setattr(hd, "SEAT_QUIET_S", 0)
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    assert "unchanged" in r.result and f"seq {asked}" in r.result["unchanged"]
    assert "through 1 of your requests" in r.result["seat_quiet"]
    assert "no seat answer" not in r.result["note"] and "not answered" not in r.result["note"]
