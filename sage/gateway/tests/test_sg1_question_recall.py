"""SG1 (paged-context PRD §9a): the question is the page fault.

Hermetic FIRE on the case that motivated it. nomad-being, 2026-11-07: dp asked for "details on
textstats project"; beat-start recall searched a fixed phrase, conversations were not in the
index, and the being said it had no details while its journal and its own 10-31 diagnosis
held them. No model, no membot, temp dirs only."""
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv  # noqa: E402
from sage.gateway import heartbeat as hb  # noqa: E402
from sage.gateway import home_recall as hr  # noqa: E402

BEING = "nomad-being"
DIAGNOSIS = ("I have read the content of `textstats/core.py`. The functions are: `_tokens`, "
             "`word_count`, `average_word_length`, and `longest_word`. The reported bug is with "
             "`word_count('hello  world')` returning 3 instead of 2.")
QUESTION = "give me details on textstats project"


def _home() -> Path:
    d = Path(tempfile.mkdtemp(prefix="sg1-"))
    (d / "journal.md").write_text(
        "2026-09-27 03:31 UTC: Read textstats/core.py in my worktree.\n\n"
        "2026-10-29 15:42 UTC: The core task is the reported bug in the textstats project: fix the "
        "word_count logic to handle multiple spaces.\n\n"
        # the same day's restatements, which hold no details
        "2026-11-07 19:08 UTC: Context flow lesson. Asked for details on the textstats project.\n\n"
        "2026-11-07 19:41 UTC: Context flow lesson again. Asked for details on the textstats project.\n\n"
        "2026-11-07 20:14 UTC: Context flow lesson once more. Asked for details on the textstats project.\n")
    conv.create(d, "dp", title="dp", participants=["dp", BEING], writable_by=["dp", BEING])
    conv.append(d, "dp", speaker="dp", text="what do you want to explore?", ts="2026-10-31T19:59:44Z",
                enforce_write=False)
    conv.append(d, "dp", speaker=BEING, text=DIAGNOSIS, ts="2026-10-31T23:56:06Z", enforce_write=False)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conv.append(d, "dp", speaker="dp", text=QUESTION, ts=now, enforce_write=False)
    return d


def _pending(d: Path) -> list:
    return [dict(t, cid=cid) for cid, t in hb.pending_turns(d, BEING)[1] if t.get("from") != BEING]


def test_conversation_turns_are_in_the_home_index_with_speaker_and_seq():
    d = _home()
    units = [u for u in hr.index_home(d) if u["source"] == "conversations/dp.jsonl"]
    assert [u["seq"] for u in units] == [1, 2, 3]
    assert units[1]["text"].startswith(f"{BEING}: ") and units[1]["date"] == "2026-10-31 23:56"
    # the being's own recall verb reaches its diagnosis now
    hits = hr.search_home(d, "textstats word_count", top_k=3)
    assert any(h["source"] == "conversations/dp.jsonl" and h.get("seq") == 2 for h in hits)
    assert "conversations/dp.jsonl seq 2 @ 2026-10-31 23:56" in hr.render(hits)


def test_fire_recall_is_keyed_on_the_pending_turn_and_reaches_the_older_work():
    d = _home()
    turns = _pending(d)
    assert [t["seq"] for t in turns] == [3] and turns[0]["text"] == QUESTION
    qr = hr.question_recall(d, turns)
    rec, text = qr["record"], qr["text"]
    assert rec["source"] == "pending" and rec["turns"] == [["dp", 3]]
    listed = [(s, q) for s, q, _ in rec["listed"]]
    assert ("conversations/dp.jsonl", 3) not in listed          # never answered with itself
    days = [dt[:10] for _, _, dt in rec["listed"] if dt]
    slots = [(hr._kind(s), dt[:10]) for s, _, dt in rec["listed"] if dt]
    assert len(slots) == len(set(slots))                        # spread: one per kind per day first
    assert "2026-10-29" in days                                 # the older entry with the detail
    assert sum(1 for dt in days if dt == "2026-11-07") <= 1     # the echoes do not crowd it out
    # the word directory names where the topic lives and where it first appears
    row = [r for r in rec["directory"] if r[0] == "textstats"]
    assert row and row[0][1] >= 5
    assert '"textstats":' in text and "first at journal.md @ 2026-09-27 03:31" in text
    # coverage is stated, including conversations (P6)
    assert rec["coverage"]["conversations"] == 3 and rec["coverage"]["journal"] == 5
    assert text.rstrip().endswith(".") and "Searched 8 entries" in text
    assert "word overlap with what dp said" in text


def test_the_block_offers_material_and_tells_the_being_nothing_to_do():
    text = hr.question_recall(_home(), _pending(_home()))["text"].lower()
    for phrase in ("you should", "first,", "you must", "remember to", "answer with", "call say"):
        assert phrase not in text, phrase


def test_no_match_and_failure_read_differently():
    d = Path(tempfile.mkdtemp(prefix="sg1-empty-"))
    (d / "journal.md").write_text("2026-11-01 10:00 UTC: something unrelated entirely.\n")
    turn = {"cid": "dp", "seq": 1, "from": "dp", "ts": "2026-11-07T20:24:19Z", "text": "textstats"}
    none = hr.question_recall(d, [turn])
    assert none["text"].startswith("No entry in your home shares a word") and "Searched 1 entries" in none["text"]
    orig = hr.index_home
    try:
        hr.index_home = lambda *a, **k: (_ for _ in ()).throw(OSError("disk"))
        bad = hr.question_recall(d, [turn])
    finally:
        hr.index_home = orig
    assert "failed: OSError" in bad["text"] and bad["record"]["error"].startswith("OSError")


def test_nothing_pending_leaves_the_default_query_alone():
    d = _home()
    conv.append(d, "dp", speaker=BEING, text="Here is what I found about textstats.",
                enforce_write=False)
    assert _pending(d) == []


def test_uptake_rungs_read_opened_recalled_and_cited():
    rec = {"source": "pending", "listed": [["journal.md", None, "2026-10-29 15:42"],
                                           ["conversations/dp.jsonl", 2, "2026-10-31 23:56"]],
           "directory": [["textstats", 7]]}
    it = lambda eff, **a: (SimpleNamespace(effector=eff, args=a), SimpleNamespace(ok=True))
    explore = SimpleNamespace(trace=[it("memory_read", path="conversations/dp.jsonl"),
                                     it("memory_read", path="todo.md"), it("recall", query="x")])
    answer = SimpleNamespace(trace=[it("say", to="dp", text="The textstats bug is word_count.")])
    out = hb.recall_uptake(rec, [explore, None, None, answer])
    assert out["uptake"] == {"opened": ["conversations/dp.jsonl"], "recalled": 1, "lexical_reuse": 1}
    assert hb.recall_uptake({"source": "default"}, [None])["uptake"] == \
        {"opened": [], "recalled": 0, "lexical_reuse": 0}


# ---- review controls (nova on SAGE#650)

def _long_home(n: int, fact_at: int) -> Path:
    """A conversation of n turns whose only mention of the fact is turn `fact_at`."""
    d = Path(tempfile.mkdtemp(prefix="sg1-long-"))
    conv.create(d, "dp", title="dp", participants=["dp", BEING], writable_by=["dp", BEING])
    for i in range(1, n + 1):
        text = DIAGNOSIS if i == fact_at else f"routine turn {i} about the weather"
        conv.append(d, "dp", speaker=BEING if i % 2 else "dp", text=text,
                    ts=f"2026-10-{1 + i // 40:02d}T{i % 24:02d}:00:00Z", enforce_write=False)
    conv.append(d, "dp", speaker="dp", text="what was the textstats word_count bug?",
                ts="2026-11-07T20:00:00Z", enforce_write=False)
    return d


def test_history_beyond_the_window_is_disclosed_not_denied():
    """Negative control, >400 turns: the fact sits before the indexed tail. The block must not
    say the home holds nothing; it says what was not searched, and the record carries it."""
    d = _long_home(450, fact_at=10)
    units = hr.conversation_units(d)
    assert len(units) == hr.CONVERSATION_TURNS
    assert units[0]["omitted_before"] and units[0]["seq"] == 452 - hr.CONVERSATION_TURNS
    qr = hr.question_recall(d, _pending(d))
    assert all(q != 10 for _, q, _ in qr["record"]["listed"])        # not reachable, and not claimed
    assert qr["record"]["omitted"] == [["conversations/dp.jsonl", units[0]["seq"], units[0]["date"]]]
    assert "No entry in your home" not in qr["text"]
    assert f"Not searched: conversations/dp.jsonl before seq {units[0]['seq']}" in qr["text"]
    # inside the window the same fact is found, and the older history is still disclosed
    d2 = _long_home(450, fact_at=300)
    qr2 = hr.question_recall(d2, _pending(d2))
    assert any(q == 300 for _, q, _ in qr2["record"]["listed"]) and qr2["record"]["omitted"]
    assert "Not searched" in qr2["text"]
    # a conversation inside the cap reports nothing omitted
    d3 = _long_home(30, fact_at=10)
    qr3 = hr.question_recall(d3, _pending(d3))
    assert qr3["record"]["omitted"] == [] and "Not searched" not in qr3["text"]


def test_tail_read_is_bounded_and_exact():
    d = Path(tempfile.mkdtemp(prefix="sg1-tail-"))
    f = d / "c.jsonl"
    f.write_text("".join(f'{{"seq": {i}}}\n' for i in range(1, 5001)))
    lines, whole = hr._tail_lines(f, 400, block=1024)
    assert len(lines) == 400 and lines[0] == '{"seq": 4601}' and not whole
    lines, whole = hr._tail_lines(f, 6000)
    assert len(lines) == 5000 and whole


def test_same_day_diagnosis_survives_an_echo():
    """Competing facts on one day. A conversation turn holding the diagnosis on the echo's day
    is listed, and a same-day journal diagnosis is offered when slots remain, rather than
    discarded by a one-per-day rule."""
    d = Path(tempfile.mkdtemp(prefix="sg1-day-"))
    (d / "journal.md").write_text(
        "2026-11-07 19:08 UTC: Asked for details on the textstats project, details textstats project.\n\n"
        "2026-11-07 19:30 UTC: Found the textstats project bug: word_count splits on one space, "
        "so 'hello  world' counts 3.\n")
    conv.create(d, "dp", title="dp", participants=["dp", BEING], writable_by=["dp", BEING])
    conv.append(d, "dp", speaker=BEING, text="The textstats project bug is in word_count: "
                "it splits on a single space.", ts="2026-11-07T19:35:00Z", enforce_write=False)
    conv.append(d, "dp", speaker="dp", text=QUESTION, ts="2026-11-07T20:00:00Z", enforce_write=False)
    rec = hr.question_recall(d, _pending(d))["record"]
    listed = [(s, q, dt) for s, q, dt in rec["listed"]]
    assert ("conversations/dp.jsonl", 1, "2026-11-07 19:35") in listed
    assert ("journal.md", None, "2026-11-07 19:30") in listed
    assert ("conversations/dp.jsonl", 2) not in [(s, q) for s, q, _ in listed]   # exclusion control


def test_the_question_is_excluded_and_its_echoes_listed_once():
    """Exclusion control: the pending turn never answers itself, and near-copies of the
    question elsewhere in the home are listed once, not once per day."""
    d = Path(tempfile.mkdtemp(prefix="sg1-excl-"))
    (d / "journal.md").write_text("".join(
        f"2026-11-0{i} 10:00 UTC: dp said give me details on textstats project.\n\n" for i in range(1, 6)))
    conv.create(d, "dp", title="dp", participants=["dp", BEING], writable_by=["dp", BEING])
    conv.append(d, "dp", speaker="dp", text=QUESTION, ts="2026-11-07T20:00:00Z", enforce_write=False)
    rec = hr.question_recall(d, _pending(d))["record"]
    assert ("conversations/dp.jsonl", 1) not in [(s, q) for s, q, _ in rec["listed"]]
    assert len(rec["listed"]) == 1


class _Sel:
    def __init__(self, cid, seq):
        self.cid, self.seq = cid, seq


def test_a_turn_racing_the_beat_is_witnessed():
    """Recall keys on the turns pending at beat start; a turn arriving before the selection is
    selected instead, and the record says the answer target was not what recall searched."""
    d = _home()
    rec = hr.question_recall(d, _pending(d))["record"]
    conv.append(d, "dp", speaker="dp", text="actually, what time is it?", enforce_write=False)
    sel = hb.pending_selection(d, BEING)[4]
    assert (sel.cid, sel.seq) == ("dp", 4)
    out = hb.reconcile_recall(rec, hb.LAST_PENDING_SCAN, sel)["reconcile"]
    assert out == {"selected": ["dp", 4], "selected_keyed": False, "added": [["dp", 4]], "removed": []}
    # an answered turn leaves the scan: removed
    gone = hb.reconcile_recall(rec, [], None)["reconcile"]
    assert gone["removed"] == [["dp", 3]] and gone["selected"] is None
    # no race: the selected turn is the keyed one
    d2 = _home()
    rec2 = hr.question_recall(d2, _pending(d2))["record"]
    sel2 = hb.pending_selection(d2, BEING)[4]
    assert hb.reconcile_recall(rec2, hb.LAST_PENDING_SCAN, sel2)["reconcile"] == \
        {"selected": ["dp", 3], "selected_keyed": True, "added": [], "removed": []}
    # the selection could not scan: unknown, not "nothing changed"
    assert hb.reconcile_recall(rec2, None, _Sel("dp", 3))["reconcile"]["added"] is None


# ---- read failures are not absence (nova's second pass on SAGE#650)

def _two_conversations() -> Path:
    """dp's conversation holds only the question; the diagnosis lives in nomad-claude's."""
    d = Path(tempfile.mkdtemp(prefix="sg1-unread-"))
    conv.create(d, "dp", title="dp", participants=["dp", BEING], writable_by=["dp", BEING])
    conv.create(d, "nomad-claude", title="nc", participants=["nomad-claude", BEING],
                writable_by=["nomad-claude", BEING])
    conv.append(d, "nomad-claude", speaker=BEING, text=DIAGNOSIS, ts="2026-10-31T23:56:06Z",
                enforce_write=False)
    conv.append(d, "dp", speaker="dp", text=QUESTION, ts="2026-11-07T20:24:19Z", enforce_write=False)
    return d


def test_an_unreadable_conversation_cannot_masquerade_as_empty():
    d = _two_conversations()
    assert any(q == 1 for s, q, _ in hr.question_recall(d, _pending(d))["record"]["listed"]
               if s == "conversations/nomad-claude.jsonl")       # readable: found
    orig = hr._tail_lines

    def failing(path, n, block=65536):
        if path.name == "nomad-claude.jsonl":
            raise PermissionError(13, "Permission denied")
        return orig(path, n, block)
    try:
        hr._tail_lines = failing
        qr = hr.question_recall(d, _pending(d))
    finally:
        hr._tail_lines = orig
    rec, text = qr["record"], qr["text"]
    assert rec["listed"] == []
    assert rec["unread"] and rec["unread"][0][0] == "conversations/nomad-claude.jsonl"
    assert rec["unread"][0][1].startswith("PermissionError")
    assert "No entry in your home" not in text
    assert text.startswith("No match in the entries searched") and "Part of your home was not searched" in text
    assert "Could not read: conversations/nomad-claude.jsonl (PermissionError" in text


def test_malformed_turns_are_reported_not_dropped():
    d = _two_conversations()
    pending = _pending(d)
    # written after the pending scan: a non-object line also breaks conversations.listing and
    # awaiting, which is outside this recall path
    f = d / "conversations" / "nomad-claude.jsonl"
    f.write_text("{not json\n[1, 2]\n" + f.read_text())
    problems = []
    units = hr.conversation_units(d, problems=problems)
    assert any(u["source"] == "conversations/nomad-claude.jsonl" for u in units)   # the good turn stays
    assert problems == [{"source": "conversations/nomad-claude.jsonl",
                         "reason": "2 malformed lines not searched"}]
    rec = hr.question_recall(d, pending)["record"]
    assert rec["unread"] == [["conversations/nomad-claude.jsonl", "2 malformed lines not searched"]]


def test_complete_coverage_reports_nothing_unread():
    d = _two_conversations()
    rec = hr.question_recall(d, _pending(d))["record"]
    assert rec["unread"] == [] and rec["omitted"] == []
