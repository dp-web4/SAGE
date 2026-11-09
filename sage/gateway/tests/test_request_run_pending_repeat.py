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
    assert r.ok and "same_request_note" not in r.result
    first = conv.recent(home, "seat", limit=1)[-1]["seq"]
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    assert r.ok and f"seq {first}" in r.result["same_request_note"] and "not answered" in r.result["same_request_note"]
    assert "minute" in r.result["same_request_note"] and "unchanged" not in r.result
    assert f"SAME AS the request at seq {first}" in conv.recent(home, "seat", limit=1)[-1]["text"]
    # a third ask still points at the first one, and counts
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "and again"}), _ALLOW)
    assert f"seq {first}" in r.result["same_request_note"] and "1 more time" in r.result["same_request_note"]
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
    assert "unchanged" in r.result and "same_request_note" not in r.result


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
    assert "same_request_note" not in r.result, r.result
    assert f"the seat answered that at seq {asked + 1} (" in r.result["unchanged"]
    assert " ago): it did not run it" in r.result["unchanged"], "the answer's age is shown"
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
    said = r.result["same_request_note"]
    assert f"seq {second}" in said and "not answered it yet" not in said
    assert "in the last 6 turns of 'seat'" in said and "older turns were not checked" in said
    assert "not answered in the last 6 turns" in conv.recent(home, "seat", limit=1)[-1]["text"]


def test_a_short_conversation_still_says_not_yet():
    # the whole conversation is inside the window: nothing older exists, so "yet" is true
    d, home = _seat_home()
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    assert "has not answered it yet" in r.result["same_request_note"] and "last 80" not in r.result["same_request_note"]


def test_a_different_file_or_an_edit_is_a_new_request():
    d, home = _seat_home()
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    (home / "notes" / "probe.py").write_text("print('b')\n")
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "edited"}), _ALLOW)
    assert "same_request_note" not in r.result


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
    # this repeat woke nobody (its run was already woken for): the note says so, and still points at the quiet
    assert "no wake was sent" in r.result["note"] and "asked and woken" not in r.result["note"]
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


def test_the_note_says_whether_a_wake_left_on_a_default_instance():
    # a hub-fired sprout session's probe on #664: on a default instance (answered_run_wake unset) the note said
    # "asked and woken ... either way it answers" on repeats that woke nobody
    d, home = _seat_home()
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    first = conv.recent(home, "seat", limit=1)[-1]["seq"]
    assert "asked and woken" in r.result["note"], r.result["note"]
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    assert "no wake was sent" in r.result["note"] and "asked and woken" not in r.result["note"], r.result["note"]
    assert f"repeats the request at seq {first}" in r.result["note"]
    conv.append(home, "seat", speaker="seat", via="seat",
                text=f"[request_run] I did not run notes/probe.py. It restarts things.\n\nAnswers your request seq {first}.")
    notes = []
    for why in ("third", "fourth"):
        r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": why}), _ALLOW)
        notes.append(r.result["note"])
    # the first ask after the decline opens a new run and wakes the seat (pub on #665); the next one does not
    assert "asked and woken" in notes[0], notes[0]
    assert "no wake was sent" in notes[1] and "already declined" in notes[1], notes[1]
    assert "no new wake: a wake was already sent" in notes[1] and "rerun" not in notes[1], notes[1]


def _wakes():
    from sage.gateway.tests.test_hestia_dispatch import FakeMcp
    return sum(1 for n, _ in FakeMcp.calls if n == "hestia_member_notify")


def _decline_then_repeat(home, d):
    """first ask -> decline -> repeats; returns [(woke, note)] for each ask, by the wake spy."""
    out = []

    def ask(why, **extra):
        before = _wakes()
        r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": why, **extra}), _ALLOW)
        out.append((_wakes() > before, r.result["note"]))
    ask("first")
    first = conv.recent(home, "seat", limit=1)[-1]["seq"]
    conv.append(home, "seat", speaker="seat", via="seat",
                text=f"[request_run] I did not run notes/probe.py. It restarts things.\n\nAnswers your request seq {first}.")
    ask("again")
    ask("and again")
    ask("rerun it", rerun="true")
    return out


def test_every_note_matches_the_wake_spy_and_rerun_advice_only_where_rerun_wakes():
    # cbp's review of #665: on a default instance the NOT-woken note advised rerun='true', which woke nobody
    import json as _json
    d, home = _seat_home()
    rows = _decline_then_repeat(home, d)
    for woke, note in rows:
        assert ("asked and woken" in note) == woke, (woke, note)
    assert [w for w, _ in rows] == [True, True, False, False], rows
    assert "no new wake: a wake was already sent" in rows[2][1] and "rerun" not in rows[2][1], rows[2][1]

    d2, home2 = _seat_home()
    (home2 / "instance.json").write_text(_json.dumps({"answered_run_wake": "skip"}))
    rows2 = _decline_then_repeat(home2, d2)
    for woke, note in rows2:
        assert ("asked and woken" in note) == woke, (woke, note)
    assert [w for w, _ in rows2] == [True, False, False, True], rows2
    assert "asks the seat once more" in rows2[1][1], "under skip, rerun does wake once, and the note may say so"
    assert "a wake was already sent" not in rows2[1][1], "no wake went out for that run"


def test_the_quiet_window_and_the_answer_reach_are_separate(monkeypatch):
    # cbp's item 9 (legion's mutants on #664): the seat-quiet fact reads _PENDING_SCAN turns, the answer scan
    # _ANSWER_SCAN. A seat turn 8 turns back is outside a 6-turn quiet window but inside the answer reach.
    from sage.gateway import hestia_dispatch as hd
    monkeypatch.setattr(hd, "_PENDING_SCAN", 6)
    monkeypatch.setattr(hd, "SEAT_QUIET_S", 0)
    d, home = _seat_home()
    conv.append(home, "seat", speaker="seat", via="seat", text="hello from the seat")
    for i in range(8):
        conv.append(home, "seat", speaker="sprout-being", text=f"[request_run] notes/other{i}.py\nwhy: x",
                    enforce_write=False)
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    q = r.result.get("seat_quiet", "")
    assert "in the last 6 turns" in q, q
    monkeypatch.setattr(hd, "_PENDING_SCAN", 80)
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    assert "since" in r.result.get("seat_quiet", ""), r.result.get("seat_quiet")


def test_under_a_pause_or_a_refused_mesh_no_note_says_no_wake_is_coming():
    # two hub-fired sprout sessions' probes and legion on #665: a pause's owed wake is rearmed when it ends,
    # a refused wake is tried again; a note may not say none is coming, nor advise rerun as if it woke
    import json as _json
    from sage.gateway.tests.test_hestia_dispatch import FakeMcp
    for cfg in (None, {"answered_run_wake": "skip"}):
        d, home = _seat_home()
        if cfg:
            (home / "instance.json").write_text(_json.dumps(cfg))
        d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
        first = conv.recent(home, "seat", limit=1)[-1]["seq"]
        conv.append(home, "seat", speaker="seat", via="seat",
                    text=f"[request_run] I did not run notes/probe.py. No.\n\nAnswers your request seq {first}.")
        conv.pause_wakes(home, "seat", by="seat", minutes=5, reason="answering directly")
        r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "paused", "rerun": "true"}), _ALLOW)
        n = r.result["note"]
        assert "paused until" in n and "rerun" not in n and "sends no new wake" not in n, (cfg, n)
        conv.resume_wakes(home, "seat", force="test")
        FakeMcp.fail = {"hestia_member_notify": "mesh down"}
        try:
            r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "mesh"}), _ALLOW)
        finally:
            FakeMcp.fail = {}
        n = r.result["note"]
        assert "tried again on your next message" in n and "rerun" not in n, (cfg, n)


def test_the_same_request_note_is_a_note_not_a_limit_and_its_count_decides_nothing():
    # cbp and legion on #668: the note leads with its scope, says its count decides nothing, and promises no answer
    d, home = _seat_home()
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    said = r.result["same_request_note"]
    assert said.startswith("A note, not a limit, and its count decides nothing:") and "answers once" not in said, said
    assert "covers every copy of this request" in said and "Nothing about this request is decided" in said, said
    # the seat-conversation line carries the same count, and says the same
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "a third time"}), _ALLOW)
    assert "(asked 3 times now; the count decides nothing)." in conv.recent(home, "seat", limit=1)[-1]["text"]
    assert "nothing stops you" not in said, "no encouragement to ask again (cbp on #668)"
    # and it survives the reflect record's 240-char cut of an ok result (cbp on #668)
    from sage.gateway.heartbeat import _record_line
    from sage.gateway.being_gate_client import BeingIntent as _BI
    line = _record_line(_BI("request_run", {"path": "notes/probe.py", "why": "again"}), r)
    assert "A note, not a limit" in line, line


def test_a_woken_receipt_promises_no_answer():
    # legion on #668: "either way it answers" promised a reply the wake does not guarantee
    d, home = _seat_home()
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    n = r.result["note"]
    assert "asked and woken" in n and "either way it answers" not in n, n
    assert "an answer, when one comes, is in 'seat'" in n, n


def test_the_request_run_tool_and_its_hints_promise_no_answer():
    # legion and cbp on #673: the tool description every being is offered said the seat "answers with the real
    # output", next to receipts that no longer promise one
    from sage.gateway import being_gate_client as bgc
    desc = bgc._TOOL_SCHEMAS["request_run"][0]
    assert "answers with the real output" not in desc and "it will say why" not in desc, desc
    assert "the seat decides whether to run it" in desc and "when the seat is there to give them" in desc
    src = open(bgc.__file__).read()
    assert "the seat runs it and answers" not in src


def test_the_request_line_promises_no_answer_and_keeps_its_identity():
    # the words after the digest changed; _REQUEST_SOURCE_HEADER pins only "(N bytes, sha256:HEX; ...)"
    d, home = _seat_home()
    d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "first"}), _ALLOW)
    sent = conv.recent(home, "seat", limit=1)[-1]["text"]
    assert "its answer, if any, comes here)" in sent and "answers here" not in sent, sent
    assert conv._request_key(sent) is not None, "the request still has its identity"
    r = d(BeingIntent("request_run", {"path": "notes/probe.py", "why": "again"}), _ALLOW)
    assert "same_request_note" in r.result, "a repeat is still recognised as the same request"
