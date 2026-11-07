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
    assert len(days) == len(set(days))                          # spread: at most one per day
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
    assert out["uptake"] == {"opened": ["conversations/dp.jsonl"], "recalled": 1, "cited_heuristic": 1}
    assert hb.recall_uptake({"source": "default"}, [None])["uptake"] == \
        {"opened": [], "recalled": 0, "cited_heuristic": 0}
