"""A seat's later word beside a settled entry (being_settled.seat_note). MEASURED ON SPROUT-BEING, 11-17..18: two
entries held a false world fact; its seat said so in conversation at least eight times in 21 h, each answer
scrolled away, and the entries, shown every beat, drove at least 15 more requests. The note puts the seat's turn
beside the entry; the entry stays the being's."""
import importlib.util
import json
import tempfile
from pathlib import Path

import pytest

from sage.gateway import being_settled as st
from sage.gateway import conversations as conv
from sage.gateway.tests.test_home_is_reachable import _being
from sage.gateway.tests.test_request_run_same_subject import _ask, _seat_home

SEAT = "test-seat"
FALSE_WORLD = {"question": "which account does the test service run under?", "answer": "the widget account, pid 41"}
SAYS = "There is no widget account on this machine; the test service runs as the operator."


def _conv(home):
    conv.create(home, SEAT, title=SEAT, participants=[SEAT, "test-being"], writable_by=[SEAT, "test-being"])


def _home(tmp_path, **entry):
    _conv(tmp_path)
    st.settle(tmp_path, dict(FALSE_WORLD, **entry), now=0)          # settled 1970-01-01
    conv.append(tmp_path, SEAT, speaker="test-being", text="please start it as the widget account")
    said = conv.append(tmp_path, SEAT, speaker=SEAT, text="I did not run it. " + SAYS)
    return said["seq"]


def test_the_seats_later_word_is_shown_beside_the_entry_and_the_entry_is_unchanged(tmp_path):
    seq = _home(tmp_path)
    before = (tmp_path / st.SETTLED_FILE).read_bytes()
    st.seat_note(tmp_path, "s1", SEAT, seq, SAYS)
    block = st.render(tmp_path)
    line = next(l for l in block.splitlines() if l.startswith("- [s1]"))
    assert "the widget account, pid 41" in line, "the being's answer is shown as it settled it"
    assert f"({SEAT} disagreed: seq {seq})" in line
    assert f"- on s1: {SEAT} at seq {seq} (" in block and SAYS in block, "the seat's words are in the beat"
    assert "Each entry is still yours: keep it, settle it again, or reopen it." in block
    assert (tmp_path / st.SETTLED_FILE).read_bytes() == before, "a note never changes the entry"
    listed = st.listing(tmp_path)
    assert f"({SEAT} disagreed at seq {seq}," in listed and SAYS in listed, "settle with no arguments shows it whole"


def test_settled_again_or_reopened_the_being_has_answered_and_the_note_goes(tmp_path):
    seq = _home(tmp_path)
    st.seat_note(tmp_path, "s1", SEAT, seq, SAYS)
    st.settle(tmp_path, {"id": "s1", "question": FALSE_WORLD["question"], "answer": "the operator's account"}, now=60)
    assert "disagreed" not in st.render(tmp_path), "a re-settled entry is a new conclusion; the note answered the old"
    st.settle(tmp_path, {"id": "s1", "reopen": "true"}, now=120)
    assert st.render(tmp_path) == "" and st.seat_notes(tmp_path, st.read(tmp_path)[0]) == {}
    st.settle(tmp_path, FALSE_WORLD, now=180)                         # the same question settled again as new
    assert "disagreed" not in st.render(tmp_path)


def test_the_act_that_drops_a_note_quotes_it_once(tmp_path):
    """sprout-being, 2026-11-22: an entry with a seat note was reopened with a reason the note contradicted, and the
    receipt said only "reopened". The note goes from the beat at that act, so its receipt quotes it, once."""
    seq = _home(tmp_path)
    st.seat_note(tmp_path, "s1", SEAT, seq, SAYS)
    ok, msg, _ = st.settle(tmp_path, {"id": "s1", "reopen": "true", "why": "the seat confirmed it"}, now=60)
    assert ok and msg.startswith("reopened s1") and f"{SEAT} at seq {seq}" in msg and SAYS in msg, msg
    assert "not shown from now on" in msg, msg
    st.settle(tmp_path, FALSE_WORLD, now=120)                         # s2, no note
    ok, msg, _ = st.settle(tmp_path, {"id": "s2", "reopen": "true"}, now=180)
    assert ok and SAYS not in msg and "seat's note" not in msg, "a note bound to the old s1 is not s2's"
    seq2 = _home(tmp_path / "b")
    st.seat_note(tmp_path / "b", "s1", SEAT, seq2, SAYS)
    ok, msg, _ = st.settle(tmp_path / "b", {"id": "s1", "question": FALSE_WORLD["question"],
                                            "answer": "the operator's account"}, now=60)
    assert ok and "now reads" in msg and SAYS in msg, "settled again, the note it answered is quoted too"


def test_without_a_note_nothing_is_added(tmp_path):
    _home(tmp_path)
    block = st.render(tmp_path)
    assert "disagreed" not in block and "still yours" not in block and "- on s1" not in block


@pytest.mark.parametrize("why, call", [
    ("no settled entry", lambda h, seq: st.seat_note(h, "s9", SEAT, seq, SAYS)),
    ("no turn seq", lambda h, seq: st.seat_note(h, "s1", SEAT, 999, SAYS)),
    ("not 'test-seat'", lambda h, seq: st.seat_note(h, "s1", SEAT, seq - 1, SAYS)),      # the being's own turn
    ("one sentence", lambda h, seq: st.seat_note(h, "s1", SEAT, seq, "x" * (st.SEAT_NOTE_MAX_CHARS + 1))),
    ("one sentence", lambda h, seq: st.seat_note(h, "s1", SEAT, seq, "  ")),
])
def test_a_note_points_only_at_the_seats_own_real_turn(tmp_path, why, call):
    seq = _home(tmp_path)
    with pytest.raises(ValueError) as e:
        call(tmp_path, seq)
    assert why in str(e.value)
    assert not (tmp_path / st.SEAT_NOTES).exists(), "refused: nothing written"


def test_a_turn_from_before_the_entry_is_not_a_later_word(tmp_path):
    _conv(tmp_path)
    conv.append(tmp_path, SEAT, speaker=SEAT, text=SAYS)
    st.settle(tmp_path, FALSE_WORLD, now=4_000_000_000)              # settled after the turn was sent
    with pytest.raises(ValueError) as e:
        st.seat_note(tmp_path, "s1", SEAT, 1, SAYS)
    assert "not later than s1" in str(e.value)


def test_the_being_cannot_write_or_erase_its_seats_notes():
    r, home = _being(Path(tempfile.mkdtemp()))
    (home / st.SEAT_NOTES).write_text("")
    for spelling in (st.SEAT_NOTES, str(home / st.SEAT_NOTES), f"/wherever/{st.SEAT_NOTES}"):
        with pytest.raises(ValueError) as e:
            r._safe_path(spelling, writing=True)
        assert "yours to read and not to edit" in str(e.value)
    assert r._safe_path(st.SEAT_NOTES, writing=False) == (home / st.SEAT_NOTES).resolve()


def test_a_short_line_names_the_note_and_the_full_block_stays_near_budget(tmp_path):
    seq = _home(tmp_path)
    st.seat_note(tmp_path, "s1", SEAT, seq, SAYS)
    for i in range(st.MAX_ENTRIES - 1):                               # s1 is now the oldest, shown short
        st.settle(tmp_path, {"question": f"test question {i} about the gadget number {i}", "answer": "x" * 400},
                  now=10 + i)
    block = st.render(tmp_path)
    line = next(l for l in block.splitlines() if l.startswith(("- [s1]", "- [s1 ")))
    assert f"({SEAT} disagreed: seq {seq})" in line and "settled 1970-01-01" in line
    assert SAYS in block, "shown short, its note's words are still in the beat"
    assert len(block) <= st.RENDER_CHARS, len(block)



@pytest.mark.parametrize("noted", [1, 4, 8, 10, 30])
def test_many_notes_keep_the_block_within_budget(tmp_path, noted):
    """legion's measurement on #783: 30 entries with 300-char answers and 190-char notes put the block at 4450
    chars with 8 notes and 9784 with 30. The newest SEAT_NOTES_SHOWN are whole; the rest are named."""
    _conv(tmp_path)
    for i in range(st.MAX_ENTRIES):
        st.settle(tmp_path, {"question": f"question {i} about gadget {i}", "answer": f"{i} " + "y" * 300}, now=i)
    for i in range(noted):
        said = conv.append(tmp_path, SEAT, speaker=SEAT, text=f"not so, entry {i + 1}")
        st.seat_note(tmp_path, f"s{i + 1}", SEAT, said["seq"], f"{i} " + "z" * 188, now=100 + i)
    block = st.render(tmp_path)
    assert len(block) <= st.RENDER_CHARS, len(block)
    whole = [l for l in block.splitlines() if l.startswith("- on s")]
    assert len(whole) == min(noted, st.SEAT_NOTES_SHOWN)
    assert whole[0].startswith(f"- on s{noted}:"), "the newest note is shown whole"
    if noted > st.SEAT_NOTES_SHOWN:
        also = next(l for l in block.splitlines() if l.startswith("- also on "))
        named = also[len("- also on "):also.index(" (")].split(", ")
        assert named == [f"s{i}" for i in range(noted - st.SEAT_NOTES_SHOWN, 0, -1)], also


def test_a_note_names_only_a_conversation_id(tmp_path):
    seq = _home(tmp_path)
    with pytest.raises(ValueError, match="not a conversation id"):
        st.seat_note(tmp_path, "s1", SEAT, seq, SAYS, conv_id="../../x")
    assert not (tmp_path / st.SEAT_NOTES).exists()

def test_the_request_run_receipt_shows_the_note_with_the_entry():
    d, home = _seat_home()
    st.settle(home, {"question": "can I reach /dev/gadget7 directly?", "answer": "only as the widget account"}, now=0)
    said = conv.append(home, "seat", speaker="seat", text="There is no widget account; nothing reaches it that way.")
    st.seat_note(home, "s1", "seat", said["seq"], "There is no widget account here.")
    r = _ask(d, home, "probe_a.py", "open /dev/gadget7 as the widget account")
    assert f"(seat disagreed at seq {said['seq']}," in r.result["you_settled"], r.result["you_settled"]


def test_the_seat_script_writes_and_refuses(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location(
        "settled_seat_note", Path(__file__).resolve().parents[2] / "scripts" / "settled_seat_note.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    seq = _home(tmp_path)
    base = ["--instance", str(tmp_path), "--entry", "s1", "--by", SEAT]
    assert cli.main(base + ["--seq", str(seq - 1), SAYS]) == 2
    assert "not written" in capsys.readouterr().err
    assert cli.main(base + ["--seq", str(seq), SAYS]) == 0
    note = json.loads(capsys.readouterr().out)
    assert note["seq"] == seq and note["entry_at"] == "1970-01-01T00:00:00Z" and note["by"] == SEAT
    said = conv.recent(tmp_path, SEAT, limit=1)[-1]
    assert note["said_at"] == said["ts"] and f"at seq {seq} ({said['ts'][:10]})" in st.render(tmp_path)
