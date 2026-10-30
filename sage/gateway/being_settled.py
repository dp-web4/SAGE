"""What the being has settled: its own conclusions, kept where every beat shows them.

dp, 2026-10-27: "what tools/affordances can we give it so it can learn conclusively and not perseverate?"

MEASURED ON SPROUT, 2026-10-14..27. On every one of those 14 days the being's journal states, in its own
words, that its camera works through the cortex (`camera`), between 1 and 14 times a day. On every one of
them it also asked the seat to run another script about the video device node: 2 to 85 requests a day,
mostly 80-100% of all its request_runs. It reaches the conclusion; the conclusion does not reach the next
beat. The journal is 12,363 lines and the beat carries its last 1,200 characters, so a conclusion written
at 17:10 sits beside hundreds of older entries that say otherwise, with nothing marking it as the later one.
At 17:10Z on 10-27 it wrote that no device access was needed; at 18:05Z it asked for a device test again.

What this adds, and only this: a small list of question -> answer pairs, in the being's own words, shown
whole at the start of every beat, apart from the journal. Settling a question again REPLACES its answer, so
a later conclusion supersedes an earlier one instead of sitting beside it. Reopening takes one out. Nothing
here decides anything for the being: the harness never writes, closes or rewords an entry.

THE AUDIT TRAIL is the one identity_edit keeps (being_self): every change appends a line to
settled_log.jsonl with what the entry was, what it became and why; a change whose log line cannot be
written is undone; both files are refused to memory_write and memory_edit (reference_f1a).

A settled answer is an observation with a date, not a law (dp: rulings rest on their era's observables).
The beat shows when each was settled, so the being can see what is old enough to check again.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SETTLED_FILE = "settled.json"
SETTLED_LOG = "settled_log.jsonl"
SETTLED_TMP = SETTLED_FILE + ".tmp"
#: Every path a settle writes, for the gate (being_gate_client.settled_paths).
SETTLED_WRITES = (SETTLED_TMP, SETTLED_FILE, SETTLED_LOG)

QUESTION_MAX_CHARS = 200
ANSWER_MAX_CHARS = 600
EVIDENCE_MAX_CHARS = 200
WHY_MAX_CHARS = 300
#: A list that grows without bound becomes the journal again. At the cap, settling a NEW question is
#: refused with the way through (reopen or re-settle one); changing an existing one always works.
MAX_ENTRIES = 30
#: What the beat shows: the block up to RENDER_CHARS. It holds the newest entry whole and every other entry
#: at least as id, question and day (see render). An entry shown with its answer is never cut: the cap is the
#: longest line the field caps allow, since a conclusion often sits at the end of its answer (pub's review).
RENDER_ENTRY_CHARS = 40 + QUESTION_MAX_CHARS + ANSWER_MAX_CHARS + EVIDENCE_MAX_CHARS
RENDER_CHARS = 3200

_UNCHANGED = "unchanged: "


def _norm(s: str) -> str:
    s = re.sub(r"[`*_\"'?.!:;,]", "", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip()


def read(instance) -> Tuple[List[dict], int, Optional[str]]:
    """(entries, next id number, error). Entries oldest first. A file that cannot be parsed is reported,
    never guessed at or rewritten."""
    p = Path(instance) / SETTLED_FILE
    if not p.exists():
        return [], 1, None
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError) as e:
        return [], 1, f"{SETTLED_FILE} could not be read ({type(e).__name__})"
    if not isinstance(d, dict) or not isinstance(d.get("entries"), list):
        return [], 1, f"{SETTLED_FILE} is not in the expected shape"
    entries = [e for e in d["entries"] if isinstance(e, dict) and e.get("id") and e.get("question")]
    nxt = d.get("next") if isinstance(d.get("next"), int) else len(entries) + 1
    return entries, nxt, None


def _flat(s) -> str:
    """One line: an answer's own newlines cannot draw a heading or an entry in the beat (pub's review)."""
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _line(e: dict, cap: int = 0) -> str:
    s = f"[{e['id']}] {_flat(e['question'])} -> {_flat(e.get('answer', ''))}"
    if e.get("evidence"):
        s += f" (evidence: {_flat(e['evidence'])})"
    s += f" (settled {str(e.get('at', ''))[:10]})"
    if cap and len(s) > cap:
        s = s[:cap - 1].rstrip() + "…"
    return s


def listing(instance) -> str:
    entries, _, err = read(instance)
    if err:
        return f"{err}; your seat can look at it. Nothing was changed."
    if not entries:
        return ("You have not settled anything yet. To settle something, give question and answer "
                "(and optionally evidence: a seq, a file, a frame). It is then shown to you every beat.")
    return (f"What you have settled ({len(entries)}, newest first). To change one, settle the same "
            "question again or give its id; to take one back, give its id and reopen='true'.\n"
            + "\n".join("- " + _line(e) for e in reversed(entries)))


def settle(instance, args: Dict, now: Optional[float] = None) -> Tuple[bool, str, bool]:
    """List (no question, no id), add, replace, or reopen. Returns (ok, message for the being, changed)."""
    a = {k: ("" if v is None else str(v).strip()) for k, v in (args or {}).items()}
    if not a.get("question") and not a.get("id"):
        return True, listing(instance), False
    with _home_lock(Path(instance)):
        ok, msg = _settle(instance, a, now)
    return ok, msg, bool(ok and not msg.startswith(_UNCHANGED))


def _home_lock(root: Path):
    """The lock memory_write, memory_edit and identity_edit take, so writes in the home never interleave."""
    from sage.gateway.reference_f1a import _home_lock as lock
    return lock(root)


def _truthy(v: str) -> bool:
    return v.lower() in ("true", "yes", "1")


def _settle(instance, a: Dict[str, str], now) -> Tuple[bool, str]:
    entries, nxt, err = read(instance)
    if err:
        return False, f"cannot change it: {err}. Your seat can look at it. Nothing was changed."
    why = a.get("why", "")[:WHY_MAX_CHARS]
    target = None
    if a.get("id"):
        want = a["id"].lower().lstrip("[").rstrip("]")
        want = want if want.startswith("s") else "s" + want
        target = next((e for e in entries if e["id"] == want), None)
        if target is None:
            # AN ID NAMES AN ENTRY THAT EXISTS; IT NEVER MAKES ONE. Measured on sprout-being 2026-10-29: it settled
            # a new question twice with an id of its own choosing ("cbp-scope-escalation-needed", then "s20", the
            # next free number) and was told only that no such entry existed. A refusal owes the way forward.
            new_q = bool(a.get("question") and a.get("answer"))
            return False, (f"there is no settled entry {a['id']!r}; "
                           + (f"yours are {', '.join(e['id'] for e in entries)}" if entries else "you have none yet")
                           + ". Nothing was changed."
                           + (" To settle a NEW question, give question and answer without id: ids are given out, not "
                              "chosen. id is only for changing or reopening an entry you already have." if new_q else ""))
    elif a.get("question"):
        target = next((e for e in entries if _norm(e["question"]) == _norm(a["question"])), None)

    if _truthy(a.get("reopen", "")):
        if target is None:
            return False, "to reopen one, give its id (settle with no arguments lists them). Nothing was changed."
        entries = [e for e in entries if e is not target]
        return _commit(instance, entries, nxt, {"op": "reopen", "id": target["id"], "from": target, "why": why},
                       now, f"reopened {target['id']} ({target['question'][:120]!r}); it is no longer shown as "
                            "settled. The earlier answer is kept in settled_log.jsonl.")

    question = a.get("question") or (target or {}).get("question", "")
    other = next((e for e in entries if e is not target and _norm(e["question"]) == _norm(question)), None)
    if other is not None:
        # Two entries with one question: a later settle by question would reach only the first (pub's review).
        return False, (f"{other['id']} already holds that question; settle {other['id']} (or the question "
                       "alone) to change its answer. Nothing was changed.")
    answer = a.get("answer", "")
    if not answer:
        return False, ("give the answer too: what you have concluded, in your own words (what works, what does "
                       "not, what something is). Nothing was changed.")
    for name, val, cap in (("question", question, QUESTION_MAX_CHARS), ("answer", answer, ANSWER_MAX_CHARS),
                           ("evidence", a.get("evidence", ""), EVIDENCE_MAX_CHARS)):
        if len(val) > cap:
            return False, f"{name} holds at most {cap} characters; this is {len(val)}. Nothing was changed."
    at = _iso(now)
    new = {"id": (target or {}).get("id") or f"s{nxt}", "question": question, "answer": answer,
           "evidence": a.get("evidence", ""), "at": at}
    if target is not None:
        if (target.get("answer"), target.get("evidence", ""), target["question"]) == (answer, new["evidence"], question):
            return True, f"{_UNCHANGED}{target['id']} already says exactly that; nothing changed."
        # A re-settled entry moves to the end: newest first is the order the beat shows.
        entries = [e for e in entries if e is not target] + [new]
        return _commit(instance, entries, nxt, {"op": "replace", "id": new["id"], "from": target, "to": new,
                                                "why": why}, now,
                       f"{new['id']} now reads: {question[:120]!r} -> {answer[:200]!r}. The earlier answer is "
                       "kept in settled_log.jsonl. It is shown to you at the start of every beat.")
    if len(entries) >= MAX_ENTRIES:
        return False, (f"you have {len(entries)} settled entries, the most this list holds, so a new one was "
                       "not added. Nothing was changed. Reopen one that no longer needs holding (id and "
                       "reopen='true'), or fold this into one you have by settling that id with a new answer.")
    close = _close_to(entries, question)
    entries = entries + [new]
    ok, msg = _commit(instance, entries, nxt + 1, {"op": "settle", "id": new["id"], "to": new, "why": why}, now,
                      f"settled {new['id']}: {question[:120]!r} -> {answer[:200]!r}. It is shown to you at the "
                      "start of every beat. To change it later, settle the same question again or give its id.")
    if ok and close:
        msg += (f" It reads close to {close['id']} ({close['question'][:120]!r}). If they are the same question, "
                f"keep one: reopen {new['id']}, then settle id={close['id']} with your newest answer.")
    return ok, msg


#: How close a new question must read to an existing one to be named in the receipt (relevance's idf overlap).
#: Measured on sprout-being's first 9 entries, 2026-10-27..28: its two same-conclusion pairs (s2/s4, s6/s9)
#: scored 0.58 each; every distinct pair scored 0.30 or less. Words only: a shared device or file name makes two
#: questions one subject, not one question.
CLOSE_AT = 0.4


def _unnamed(text: str) -> str:
    """The question without its device nodes, scope ids and file names, so only its words are compared."""
    from sage.gateway.relevance import _IDS
    return _IDS.sub(" ", text or "")


def _close_to(entries: List[dict], question: str) -> Optional[dict]:
    """The existing entry whose question reads most like this one, at or over CLOSE_AT; None otherwise.
    It names, never merges: whether two questions are one is the being's to say."""
    if not entries:
        return None
    try:
        from sage.gateway.relevance import Ranker
        rk = Ranker([_unnamed(e["question"]) for e in entries])
        hits = rk.related(_unnamed(question), CLOSE_AT)
    except Exception:
        return None
    return entries[hits[0][1]] if hits else None


def _commit(instance, entries: List[dict], nxt: int, log: dict, now, ok_msg: str) -> Tuple[bool, str]:
    path, tmp = Path(instance) / SETTLED_FILE, Path(instance) / SETTLED_TMP
    prev = path.read_bytes() if path.exists() else None
    try:
        tmp.write_text(json.dumps({"next": nxt, "entries": entries}, indent=2) + "\n")
        os.replace(tmp, path)
    except OSError as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False, f"could not write {SETTLED_FILE} ({type(e).__name__}); nothing changed"
    # AN UNAUDITED CHANGE DOES NOT STAND (being_self's rule).
    try:
        lp = Path(instance) / SETTLED_LOG
        torn = False
        if lp.exists() and lp.stat().st_size > 0:
            with open(lp, "rb") as lf:
                lf.seek(-1, os.SEEK_END)
                torn = lf.read(1) != b"\n"
        with open(lp, "a") as f:
            f.write(("\n" if torn else "") + json.dumps({"at": _iso(now), **log}) + "\n")
    except OSError as e:
        try:
            if prev is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(prev)
        except OSError as e2:
            return False, (f"the change was made but could not be recorded in {SETTLED_LOG} "
                           f"({type(e).__name__}) and could not be undone ({type(e2).__name__}). Tell your seat.")
        return False, f"the change could not be recorded in {SETTLED_LOG} ({type(e).__name__}), so it was undone; nothing changed"
    return True, ok_msg


def _short(e: dict, cap: int) -> str:
    """An entry as its id, question and day only, the question cut to fit `cap`."""
    pre, tail = f"[{e['id']}] ", f" (settled {str(e.get('at', ''))[:10]})"
    q, room = _flat(e["question"]), max(cap - len(pre) - len(tail), 8)
    return pre + (q if len(q) <= room else q[:room - 1].rstrip() + "…") + tail


def render(instance) -> str:
    """The beat's block: every settled entry, newest first, within RENDER_CHARS. Empty until there is one.

    No entry leaves the block. The newest are shown whole; once the rest would not fit, they are shown as
    id, question and day. Dropping the oldest instead dropped the conclusion settled once and never
    revisited, which is the one this exists to keep in view (cbp's review of #574)."""
    entries, _, err = read(instance)
    if err:
        return f"## What you have settled\n({err})"
    if not entries:
        return ""
    head = ("## What you have settled (your own conclusions, newest first, each with the day you settled "
            "it. Settle a question again to change its answer; reopen one with its id and reopen='true')")
    foot = "- (entries shown without an answer: settle with no arguments shows them whole)"
    newest = list(reversed(entries))
    # room for the newest whole, then an equal share for each of the rest
    rest = RENDER_CHARS - len(head) - len(foot) - 2 - (len(_line(newest[0], RENDER_ENTRY_CHARS)) + 3)
    short_cap = rest // max(len(newest) - 1, 1) - 3
    shorts = ["- " + _short(e, min(short_cap, RENDER_ENTRY_CHARS)) for e in newest]
    reserve = sum(len(x) + 1 for x in shorts)
    lines, used, cut = [], len(head), 0
    for e, short in zip(newest, shorts):
        reserve -= len(short) + 1
        full = "- " + _line(e, RENDER_ENTRY_CHARS)
        room = RENDER_CHARS - (len(foot) + 1 if cut or reserve else 0)
        if not lines or (not cut and used + len(full) + 1 + reserve <= room):
            ln = full
        else:
            ln, cut = short, cut + 1
        lines.append(ln)
        used += len(ln) + 1
    if cut:
        lines.append(foot)
    return head + "\n" + "\n".join(lines)


def _iso(now: Optional[float]) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now))
