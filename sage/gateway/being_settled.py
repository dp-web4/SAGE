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
import math
import os
import re
import time
import unicodedata
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
    # NFKC folds compatibility forms, and these hyphens and dashes read as a space.
    # "context window", "context-window" and "context\u2011window" (a non-breaking hyphen) name the same question.
    # Normalizing them keeps repeated spellings on one settled entry.
    s = unicodedata.normalize("NFKC", (s or "")).lower()
    s = re.sub(r"[-\u2010-\u2015\u2212]", " ", s)
    s = re.sub(r"[`*_\"'?.!:;,]", "", s)
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


def _near(e: dict, near: Optional[Dict[str, List[str]]], show: int = 3) -> str:
    """The mark: the OLDEST other entry first, then the newest (cbp's review of #661: in sprout's shape the one
    true seat entry was the oldest of eleven, and newest-three hid it; later is not truer). `show` ids, then +N."""
    ids = (near or {}).get(e["id"])
    if not ids:
        return ""
    pick = ids[:1] + ids[1:][::-1][:max(show - 1, 0)] if show > 0 else []
    more = f"+{len(ids) - len(pick)}" if len(ids) > len(pick) else ""
    return f" ≈{','.join(pick)}{more}"


def _line(e: dict, cap: int = 0, near: Optional[Dict[str, List[str]]] = None) -> str:
    s = f"[{e['id']}{_near(e, near)}] {_flat(e['question'])} -> {_flat(e.get('answer', ''))}"
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
    near = _neighbours(entries)   # once, not per entry (pub's review of #661)
    return (f"What you have settled ({len(entries)}, newest first). To change one, settle the same "
            "question again (or its id with that question); to take one back, give its id and reopen='true'.\n"
            + "\n".join("- " + _line(e, near=near) for e in reversed(entries)))


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
        # the first token: an id copied from the block reads "[s3 ≈s1]" (cbp's review of #661)
        want = (a["id"].lower().lstrip("[").split() or [""])[0].rstrip("]")
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
    # A SETTLED ANSWER IS READ AS THE ANSWER TO ITS QUESTION, so a change by id restates that question. Measured on
    # cbp-being 2026-10-28..30: s10 kept "When should I escalate a scope request?" while its answer was replaced five
    # times by an id-only settle with conclusions about other things (a daemon status report, a unit-file fix, scope
    # expiry), one of them "consolidating with s10" after the full-list refusal told it to fold. Every beat then
    # showed that question with an answer to a different one: a settle that does not settle. The being never saw the
    # question it was answering; this makes it say it.
    if target is not None and a.get("answer") and not _truthy(a.get("reopen", "")):
        given = a.get("question", "")
        if not given:
            return False, (f"{target['id']} holds the question {target['question']!r}. To change its answer, "
                           f"settle id={target['id']} with that question and your new answer, so the answer stays "
                           "with the question it answers. If your answer answers a different question, settle it "
                           "as a new one: question and answer, without id. Nothing was changed.")
        if _norm(given) != _norm(target["question"]) and not _same_question(target, given):
            # THE ROUTE FOR A TRUE REWORDING, AND THE QUESTION WHOLE (cbp's replay on #661: about 18 of 26 new refusals
            # were true rewordings, and this refusal sent them round to the receipt that sent them here). A quote
            # cut short is not the question: copied, it can end mid-word and be refused too.
            return False, (f"{target['id']} holds the question {target['question']!r}; yours, "
                           f"{given[:160]!r}, reads as a different question. If it IS the same question, settle "
                           f"id={target['id']} with its question exactly as above. If not, settle yours as a new "
                           f"one (question and answer, without id), or reopen {target['id']} first if it no longer "
                           "holds. Nothing was changed.")
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
    close = _close_to(entries, question)
    if len(entries) >= MAX_ENTRIES:
        # sprout-being, 2026-10-30: four refusals here in its first hour at the cap, and no reopen or fold. Two of
        # the refused questions read close to one it held; the receipt named neither.
        # NO "FOLD IT INTO ONE YOU HAVE". That advice, without a close entry, is how cbp-being's questions came to
        # carry answers to other questions (s10, s20, s42: 10-28..30). A full list is made room in by reopening.
        oldest = ", ".join(f"{e['id']} ({e['question'][:60]!r}, {str(e.get('at', ''))[:10]})" for e in entries[:3])
        return False, (f"you have {len(entries)} settled entries, the most this list holds, so a new one was "
                       "not added. Nothing was changed. To make room, reopen one that no longer needs holding (its "
                       f"id and reopen='true'); the longest held are {oldest}. Do not put this answer under a "
                       "different question: every beat reads a settled answer as the answer to its question."
                       # "THE ANSWER THAT HOLDS", AS IN THE RECEIPT (legion on #661): followed literally at the cap,
                       # "your newest answer" replaced s30's true answer with the false one on the s100/s101 shape
                       + (f" This reads close to {close['id']} ({close['question']!r}), which says "
                          f"{_flat(close.get('answer', ''))[:200]!r} (settled {str(close.get('at', ''))[:10]}): if "
                          f"they are the same question, settle id={close['id']} with that question and the answer "
                          "that holds." if close else ""))
    entries = entries + [new]
    ok, msg = _commit(instance, entries, nxt + 1, {"op": "settle", "id": new["id"], "to": new, "why": why}, now,
                      f"settled {new['id']}: {question[:120]!r} -> {answer[:200]!r}. It is shown to you at the "
                      "start of every beat. To change it later, settle the same question again (with its id, if you like).")
    if ok and close:
        # WHAT THE EARLIER ONE SAYS, NOT ONLY ITS QUESTION. sprout-being 11-07: s101 was settled 2.5 h after s100,
        # on one subject, with the opposite answer; a receipt naming s100's question would not have shown that the
        # two answers disagree.
        near = _close_all(entries[:-1], question)
        said = "; ".join(f"{c['id']} (settled {str(c.get('at', ''))[:10]}) says {_flat(c.get('answer', ''))[:200]!r}"
                         for c in near)
        # "WITH THE ANSWER THAT HOLDS", NOT "YOUR NEWEST" (legion's review of #661): followed literally on the
        # s100/s101 shape, "settle id=s1 with your newest answer" replaced the true entry with the false one
        msg += (f" It reads close to {close['id']} ({close['question'][:120]!r}). Your earlier "
                f"answer{'s' if len(near) > 1 else ''}: {said}. If they are the same question, keep one: reopen "
                f"{new['id']}, then settle id={close['id']}, question {close['question']!r} word for word, with the "
                "answer that holds. If they differ, both stay, and each beat marks them with \u2248.")
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


def _stem(t: str) -> str:
    """A plain English ending off, so runs/run, service/services and process/processes meet (pub's review of
    #661: the first cut made services->servic and process->proces).

    NO UNDOUBLING: `running` stays `runn`, apart from `run`. Measured on sprout's settled log (a hub-fired
    sprout session, #661): joining them linked questions about whether a script had executed to questions about
    whether the seat was alive, 7 -> 19 such links, nothing gained on the live list. On this subject they are two questions (pub withdrew the suggestion)."""
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif len(t) > 4 and t.endswith("es") and t[:-2].endswith(("s", "x", "z", "ch", "sh")):
        t = t[:-2]
    elif len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        t = t[:-1]
    else:
        for suf in ("ing", "ed"):
            # a stem of 4+ letters: string and speed are words, not str+ing and spe+ed (pub on #661)
            if t.endswith(suf) and len(t) - len(suf) >= 4:
                t = t[:-len(suf)]
                break
    # then a final -e, on every path, so escalate/escalated/escalates and service/services all meet (a
    # hub-fired sprout session on #661: escalated -> escalat, escalate whole, counted as two words)
    return t[:-1] if len(t) > 4 and t.endswith("e") else t

def _subject_terms(text: str) -> Dict[str, str]:
    """{term: the word it came from}. A hyphenated name gives its parts, so 'gizmo-seat' meets 'gizmo seat',
    and a word loses a plain ending, so 'restarted' meets 'restart'.

    MEASURED ON SPROUT, 2026-11-09. It settled s100 (whether its seat was running; true answer) at 20:10Z on
    11-07, and s101 (the same question, its seat's name spelled with a hyphen; the opposite answer) at 22:46Z.
    relevance's terms scored that pair 0.0: the hyphenated name was one word, so the receipt for s101 named
    nothing, and both were shown as unrelated every
    beat after. Over the next two days it settled the seat dead or restartable in 5 more entries, worded 5 ways.
    With these terms, 9 of its 10 seat entries are linked at CLOSE_AT and nothing else is; across all 111
    questions in its settled log, at least 16 of 460 links join two subjects (a floor: the links between two
    seat-worded questions were not audited)."""
    from sage.gateway.home_recall import _terms
    out: Dict[str, str] = {}
    for t in _terms(_unnamed(text)):
        parts = [x for x in t.split("-") if x]
        for x in (parts if len(parts) > 1 else [t]):
            x = _stem(x.split("'")[0])
            if len(x) > 1 and x not in ("it", "its"):
                out.setdefault(x, t)
    return out


def _closeness(questions: List[str]):
    """score(query_terms, i): relevance's idf overlap over these questions, where the parts of one name count
    as one shared word (two parts of 'sprout-claude' are not two things in common). This is for NAMING only:
    whether a reworded question is the SAME question is _same_question's, on the predicate CLOSE_AT was set for."""
    groups = [_subject_terms(q) for q in questions]
    df: Dict[str, int] = {}
    for g in groups:
        for t in g:
            df[t] = df.get(t, 0) + 1
    n = len(groups)

    def idf(t: str) -> float:
        return math.log((n + 1) / (df[t] + 0.5)) if t in df else math.log(n + 1.5)

    def score(q: Dict[str, str], i: int) -> float:
        d = groups[i]
        shared = set(q) & set(d)
        # BOTH SIDES (cbp's review of #661): counted from the query only, "the parts of one name are one word"
        # held when the hyphenated question asked, not when the spaced one did, so marks went one way (s102
        # and s105 marked s101 on sprout's live list; s101 marked neither)
        words = min(len({q[t] for t in shared}), len({d[t] for t in shared})) if shared else 0
        if not shared or words < min(2, len(set(q.values())), len(set(d.values()))):
            return 0.0
        den = min(sum(idf(t) for t in q), sum(idf(t) for t in d)) or 1.0
        return sum(idf(t) for t in shared) / den

    return groups, score


def _close_all(entries: List[dict], question: str, limit: int = 3) -> List[dict]:
    """Existing entries whose question reads like this one, at or over CLOSE_AT, closest first (newer first on
    a tie). It names, never merges: whether two questions are one is the being's to say."""
    if not entries:
        return []
    try:
        _, score = _closeness([e["question"] for e in entries])
        q = _subject_terms(question)
        hits = [(score(q, i), i) for i in range(len(entries))]
    except Exception:
        return []
    hits = sorted((h for h in hits if h[0] >= CLOSE_AT), key=lambda h: (-h[0], -h[1]))
    return [entries[i] for _, i in hits[:limit]]


def _close_to(entries: List[dict], question: str) -> Optional[dict]:
    """The existing entry whose question reads most like this one, at or over CLOSE_AT; None otherwise."""
    hits = _close_all(entries, question, 1)
    return hits[0] if hits else None


#: What a question opens with, by kind: each wh-word its own, every yes/no auxiliary one kind.
_WH = ("how", "why", "when", "which", "what", "where", "who")
_YESNO = frozenset("is are was were does do did can could should would will has have may must".split())


def _asks(q: str) -> str:
    """The kind of question `q` opens with ('how', 'when', ... or 'yes/no'), or '' when it opens with neither."""
    w = (re.findall(r"[a-z]+", (q or "").lower()) or [""])[0]
    return w if w in _WH else "yes/no" if w in _YESNO else ""


def _same_question(target: dict, given: str) -> bool:
    """Whether `given` restates `target`'s question, so `id=` may put an answer under it. Two tests, both by
    the question's own words: the kind of question it opens with (how, when, which, yes/no ...) must not differ,
    and the new wording's terms must be among the old one's (a rewording may say less, not more).

    NOT THE NAMING SCORE, AND STRICTER THAN MAIN (reviews of #661 by cbp, legion and McNugget, and a hub-fired
    sprout session's table). A false admit takes the old answer out of the beat; a false refusal costs one
    retry, and the refusal says how. On main, against a "when should I escalate X?" entry, "when does an X
    expire?" was ADMITTED (only the plural was refused, for want of stemming), and no threshold on a one-entry
    corpus separates it from a true rewording (both 0.51). Over the
    506 ordered pairs of sprout's live list this admits 1 (s101's wording under s100, one name spelled two ways); main's
    predicate admitted 9. It still refuses some true rewordings (a terse "X escalation timing?", or a
    reworded question with one word of its own), which the being restates or settles anew.
    saying less cannot tell a dropped qualifier from a dropped filler word: "Is the seat running?" is admitted
    under "Is the seat running on legion?" (a hub-fired sprout session on #661), the price of letting the
    s100/s101 respelling through. Nor does it read negation ("Is the seat not running?" and "Is the seat running?"
    admit each other; cbp's replay found it differing in 1 real pair).

    A DIFFERENT NAME OR NUMBER MAKES TWO QUESTIONS (cbp's re-review): /dev/video1 under /dev/video0, k=1 under k=2
    (a real settle, cbp s319). Saying less stays allowed: "Does it exist?" under "Does /dev/video0 exist?"."""
    ka, kb = _asks(target["question"]), _asks(given)
    if ka and kb and ka != kb:
        return False   # how vs whether, when vs which: the question word is the question
    a, b = set(_subject_terms(target["question"])), set(_subject_terms(given))
    if not a or not b:
        return False
    # THE NEW WORDING MAY SAY LESS, NOT MORE. A question that brings a word of its own narrows or changes it
    # ("Is the seat running on legion?" under "Is the seat running?", "Did the build pass yesterday?" under
    # "Does the build pass?": pub's re-review of #661), and admitting it takes the old answer out of the beat.
    return b <= a and len(b) >= min(2, len(a)) and _named(given) <= _named(target["question"])


def _named(q: str) -> set:
    """The device nodes, scope ids, file names and numbers a question names, which its terms leave out or reduce."""
    from sage.gateway.relevance import _IDS
    return {m.group(0).lower() for m in _IDS.finditer(q or "")} | set(re.findall(r"\d+", q or ""))


def _neighbours(entries: List[dict]) -> Dict[str, List[str]]:
    """{id: ids of the other entries whose question reads close to its own}, for the beat's block."""
    if len(entries) < 2:
        return {}
    try:
        groups, score = _closeness([e["question"] for e in entries])
    except Exception:
        return {}
    out: Dict[str, List[str]] = {}
    for i, e in enumerate(entries):
        near = [entries[j]["id"] for j in range(len(entries)) if j != i and score(groups[i], j) >= CLOSE_AT]
        if near:
            out[e["id"]] = near
    return out


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


#: A short line keeps at least this much of its question; a mark that would take it below is left off the
#: line (the entry keeps its mark wherever it is shown whole, and in the listing).
SHORT_QUESTION_FLOOR = 24


def _short(e: dict, cap: int, near: Optional[Dict[str, List[str]]] = None) -> str:
    """An entry as its id, question and day only, the question cut to fit `cap`.

    ONE ID IN A SHORT LINE'S MARK, AND NEVER AT THE QUESTION'S EXPENSE (legion's review of #661): on legion-being's
    full list, three ids took the median short question from 49 chars to 28, and at every field cap with 3-digit
    ids the block passed RENDER_CHARS and showed 8 chars of a question. A mark asks the being to compare two
    entries; a question it cannot recognise defeats it."""
    tail = f" (settled {str(e.get('at', ''))[:10]})"
    pre = f"[{e['id']}{_near(e, near, 1)}] "
    if cap - len(pre) - len(tail) < SHORT_QUESTION_FLOOR:
        pre = f"[{e['id']}] "
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
    near = _neighbours(entries)
    head = ("## What you have settled (your own conclusions, newest first, each with the day you settled "
            "it. Settle a question again to change its answer; reopen one with its id and reopen='true')")
    if near:
        # THE BLOCK SHOWED TWO ANSWERS TO ONE SUBJECT AS UNRELATED (sprout-being, 11-07..09: 11 entries on
        # whether its seat was alive, 2 of them true). It says which read alike; which holds stays the being's.
        head += ("\n(\u2248 after an id names other entries whose question reads like this one's, the oldest "
                 "first: [s9 \u2248s4,s7] reads close to s4 and s7, and +N counts the rest. Their answers may "
                 "agree or not.)")
    foot = "- (entries shown without an answer: settle with no arguments shows them whole)"
    newest = list(reversed(entries))
    # room for the newest whole, then an equal share for each of the rest
    rest = RENDER_CHARS - len(head) - len(foot) - 2 - (len(_line(newest[0], RENDER_ENTRY_CHARS, near)) + 3)
    short_cap = rest // max(len(newest) - 1, 1) - 3
    shorts = ["- " + _short(e, min(short_cap, RENDER_ENTRY_CHARS), near) for e in newest]
    reserve = sum(len(x) + 1 for x in shorts)
    lines, used, cut = [], len(head), 0
    for e, short in zip(newest, shorts):
        reserve -= len(short) + 1
        full = "- " + _line(e, RENDER_ENTRY_CHARS, near)
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
