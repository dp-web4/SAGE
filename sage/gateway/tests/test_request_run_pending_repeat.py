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


def test_an_answer_before_the_scan_window_is_not_reported_as_not_answered_yet(monkeypatch):
    # #567 (cbp on #566): ask -> the seat answers -> the window scrolls -> the same ask again. The answer
    # is out of view, so "not answered yet" would be false; the notes name the window they checked.
    from sage.gateway import hestia_dispatch as hd
    monkeypatch.setattr(hd, "_PENDING_SCAN", 6)
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
