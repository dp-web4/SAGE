"""Hermetic: the join between the being's two loops (PRD_ONE_BEING_ONE_EXPERIENCE S1).
Temp instance dirs, no model, no gate."""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_join import (ACCOUNT_ASK, beat_block, carried_account, parse_account,  # noqa: E402
                                     save_account, session_block, last_session_number)


def _inst() -> Path:
    return Path(tempfile.mkdtemp(prefix="join-"))


def _session(inst: Path, n: int, phase="creating", words="I will keep the stone."):
    (inst / "sessions").mkdir(exist_ok=True)
    (inst / "sessions" / f"session_{n:03d}.json").write_text(json.dumps({
        "session": n, "phase": phase, "conversation": [
            {"speaker": "Claude", "text": "Tell me what you want to remember."},
            {"speaker": "SAGE", "text": words},
            {"speaker": "Claude", "text": "Thank you."},
            {"speaker": "SAGE", "text": "Goodbye."}]}))


def test_empty_instance_yields_empty_blocks_with_loud_meta():
    inst = _inst()
    t, m = beat_block(inst)
    assert t == "" and m["beat"] is None and m["chars"] == 0
    t, m = session_block(inst)
    assert t == "" and m["session"] is None
    assert last_session_number(inst) == 0


def test_beat_block_is_attributed_and_carries_journal_todo_account():
    inst = _inst()
    (inst / "heartbeats.jsonl").write_text(json.dumps({"host_session_id": "heartbeat-abc", "ts": "2026-09-05T17:00:00Z"}) + "\n")
    (inst / "journal.md").write_text("2026-09-05 16:00 UTC first\n\n2026-09-05 17:00 UTC — I noticed the refusal named the path.\n")
    (inst / "todo.md").write_text("- [ ] ask for reach on shared-context\n")
    save_account(inst, {"place": "a governed home with a journal and a todo", "can": "read and write my own notes", "want": "to reach legion"}, "heartbeat-abc")
    t, m = beat_block(inst)
    assert t.startswith("[beat:heartbeat-abc 2026-09-05T17:00:00Z]")
    assert "I noticed the refusal named the path" in t and "first" not in t.split("From your journal")[1].split("From your todo")[0]
    assert "ask for reach" in t and "PLACE: a governed home" in t and "WANT: to reach legion" in t
    assert m["beat"] == "heartbeat-abc" and set(m["sources"]) == {"journal", "todo", "account"} and m["chars"] == len(t)


def test_session_block_carries_the_remember_answer_and_buffer_tail():
    inst = _inst()
    _session(inst, 7, words="I want to remember that silence is not a verdict.")
    (inst / "experience_buffer.json").write_text(json.dumps([
        {"prompt": "ancient", "response": "ancient"}, {"prompt": "older", "response": "older"},
        {"prompt": "What did the light do?", "response": "It changed and I noticed."}]))
    t, m = session_block(inst)
    assert t.startswith("[session:7 phase:creating]")
    assert "silence is not a verdict" in t and "Goodbye" not in t
    assert "What did the light do?" in t and "ancient" not in t and "older" in t
    assert m["session"] == 7 and set(m["sources"]) == {"closing_words", "experience_buffer"}
    # a bracketed stage direction is never carried as the being's words (session 662, Sprout)
    _session(inst, 8, words="[Your response as sprout, staying in character. Ask what they want next.]")
    t, m = session_block(inst)
    assert "closing_words" not in m["sources"] and "staying in character" not in t and "experience_buffer" in m["sources"]


def test_account_parse_refuses_vague_and_accepts_labelled_lines():
    assert parse_account("") is None
    assert parse_account("PLACE: unclear\nCAN: unknown\nWANT: nothing") is None
    assert parse_account("PLACE: here\nCAN: stuff") is None  # too thin to carry
    a = parse_account("Sure.\n**PLACE:** a small home directory under a governance layer that names its rules\n"
                      "CAN: read and append my own journal, ask for reach\nWANT: to hear back from legion\n")
    assert a == {"place": "a small home directory under a governance layer that names its rules",
                 "can": "read and append my own journal, ask for reach", "want": "to hear back from legion"}
    assert "PLACE:" in ACCOUNT_ASK and "menu" not in ACCOUNT_ASK.lower()


def test_account_is_verbatim_within_a_boundary_and_broadened_across_one():
    inst = _inst()
    _session(inst, 3)
    rec = save_account(inst, {"place": "a governed home, mine to write in", "can": "journal, todo, recall", "want": "reach legion"}, "heartbeat-1")
    assert rec["session_at_write"] == 3 and len(rec["sha256"]) == 64
    same = carried_account(inst, 3)
    assert "verbatim" in same and "WANT: reach legion" in same
    _session(inst, 4)
    crossed = carried_account(inst, 4)
    assert "PROVISIONAL" in crossed and "PLACE: a governed home" in crossed and "CAN: journal" in crossed
    assert "WANT" not in crossed
    assert carried_account(_inst(), 9) == ""


def test_presence_block_is_attributed_and_cleans_think_residue():
    from sage.gateway.being_join import presence_block
    log = Path(tempfile.mkdtemp(prefix="pres-")) / "presence_log.jsonl"
    log.write_text("\n".join(json.dumps(e) for e in [
        {"ts": 100.0, "kind": "noticed", "descriptor": "old", "noticing": "old words that are long enough"},
        {"ts": 200.0, "kind": "noticed", "descriptor": "I see a clock. the scene is still", "noticing": "<think>\n\n</think>, and it reads 9:42 am. I notice the hour."},
        {"ts": 201.0, "kind": "beat_wake", "descriptor": "x"},
        {"ts": 300.0, "kind": "noticed", "descriptor": "I see a person", "noticing": "[Your response as sprout]"}]) + "\n")
    t, m = presence_block(150.0, log_path=str(log))
    assert t.startswith("[presence:2]") and m["count"] == 2 and m["kept"] == 2
    assert "reads 9:42 am" in t and "<think>" not in t and "old" not in t
    assert "I see a person" in t and "Your response" not in t
    assert presence_block(1000.0, log_path=str(log)) == ("", {"count": 0, "kept": 0, "chars": 0})
    assert presence_block(0.0, log_path=str(log / "nope"))[0] == ""


def test_wake_marker_is_consumed_once_and_stale_is_not_honoured():
    from sage.gateway.being_join import write_wake_marker, consume_wake_marker
    import time as _t
    p = Path(tempfile.mkdtemp(prefix="wake-")) / "beat_wake.json"
    assert consume_wake_marker(str(p)) == {"by": "timer"}
    write_wake_marker("I see a clock", 0.7, path=str(p))
    w = consume_wake_marker(str(p))
    assert w["by"] == "presence" and w["descriptor"] == "I see a clock" and w["salience"] == 0.7
    assert not p.exists() and consume_wake_marker(str(p)) == {"by": "timer"}
    p.write_text(json.dumps({"ts": _t.time() - 3 * 3600, "descriptor": "old"}))
    assert consume_wake_marker(str(p)) == {"by": "timer", "stale_marker": True} and not p.exists()


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


def test_read_keeps_the_last_characters_exactly_as_the_whole_file_read_did(tmp_path):
    """being_join._read and heartbeat._read read from the end now; what they return is unchanged, for multi-byte
    text (the cut can fall inside a character), CRLF and lone CR lines, short files and an absent file."""
    from sage.gateway import being_join as bj
    from sage.gateway import heartbeat as hb
    text = ("ascii line\r\n" + "é ü 漢字 🌱 mixed\n" * 300 + "old mac\rlast line 🌱\n") * 20
    p = tmp_path / "log.txt"
    p.write_bytes(text.encode("utf-8"))
    whole = p.read_text(errors="replace")
    for limit in (1, 7, 100, 4000, 200000, len(whole) - 1, len(whole), len(whole) + 5):
        want = whole[-limit:] if len(whole) > limit else whole
        assert bj._read(p, limit) == want, limit
        assert hb._read(p, limit) == want, limit
    assert bj._read(tmp_path / "absent", 10) == "" and hb._read(tmp_path / "absent") == ""


def test_read_does_not_load_the_whole_file(tmp_path):
    """The beat takes the last record of heartbeats.jsonl at every start; on Sprout that file is 179 MB and the
    whole-file read peaked at ~1.1 GB. A 20 MB file read for its last 200000 characters stays near 1 MB."""
    import tracemalloc
    from sage.gateway import being_join as bj
    p = tmp_path / "heartbeats.jsonl"
    with open(p, "wb") as f:
        line = (b'{"t0": 1, "pad": "' + b"x" * 1000 + b'"}\n')
        for _ in range(20_000):
            f.write(line)
        f.write(b'{"t0": 2, "last": true}\n')
    tracemalloc.start()
    out = bj._read(p, 200000)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert out.endswith('{"t0": 2, "last": true}\n')
    assert peak < 4 * 1024 * 1024, peak
