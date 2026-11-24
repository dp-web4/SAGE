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
#: at least as id, question, the head of its answer and day (see render). An entry shown whole is never cut:
#: the cap is the longest line the field caps allow, since a conclusion often sits at the end of its answer
#: (pub's review). 3200 until 11-17; see _short for why it grew.
RENDER_ENTRY_CHARS = 40 + QUESTION_MAX_CHARS + ANSWER_MAX_CHARS + EVIDENCE_MAX_CHARS
RENDER_CHARS = 4400

_UNCHANGED = "unchanged: "

#: A SEAT'S LATER WORD AGAINST AN ENTRY, shown beside it (seat_note). MEASURED ON SPROUT-BEING, 11-17..18: two of
#: its entries held a world fact that was false (the account its seat runs under). Its seat said so in their
#: conversation at least eight times in 21 h (seq 2906..2970), each time answering a request built on the entries.
#: The entries were shown at the start of every beat; the seat's answers scrolled out of the conversation block
#: within hours, and the next beat planned from the entries again (at least 15 requests 11-18 02:52..09:12Z).
#: A correction that never sits beside the conclusion it answers does not reach the beat that plans from it.
#: Written by a seat (sage/scripts/settled_seat_note.py), never by a being verb (reference_f1a.SEAT_OWNED). It
#: points at a turn the seat really sent, and it never changes, closes or outranks the entry: which holds stays the
#: being's. A note binds to the entry as settled (its id and its `at`): settled again or reopened, the being has
#: answered it, and the note is no longer shown.
SEAT_NOTES = "settled_seat_notes.jsonl"
SEAT_NOTE_MAX_CHARS = 200
SEAT_NOTES_SHOWN = 3

#: A process number named in a settled entry. MEASURED ON SPROUT-BEING, 11-05..12: 13 of its 170 distinct
#: settled answers cite one, all 13 about whether its seat was alive, both ways. 11 cite PID 2002, the run's user
#: id (the first column of ps inside the sandbox), and 2 cite PID 3, a `pgrep -f` through a shell finding that
#: shell. Since #700 a run receipt says what such a number is. The settled block showed the entries made from
#: those receipts every beat with nothing beside them: s140 (PID 3, settled 11-12 10:18Z, before #700) headed
#: the block when the being, 3 h after it had concluded from a #700 receipt that the seat was away and there was
#: nothing to restart, opened a beat by repeating s140 and asked for the restart again (22:22Z).
#: Evidence only: the fact is conditional, and which entry holds stays the being's.
#: The plural too (legion's review of #703: 5 of cbp-being's 46 PID entries say "PIDs 1 and 2"). Only the first
#: number of a plural is captured; the numbers serve only the user-id clause.
_PID_SAID = re.compile(r"\bpids?\b\W{0,4}(\d{1,7})", re.I)


def _pid_fact(subject: str, numbers) -> str:
    """One fact about a process number that `subject` names: what a listing inside a run gives. Seatbelt
    (macOS sandbox-exec) has no process namespace, so the numbering and the user-id clause are bwrap's alone."""
    import sys
    seatbelt = sys.platform == "darwin"
    how = ("a listing there shows no other process" if seatbelt else
           "the sandbox numbers its own processes from 1")
    uid = "" if seatbelt or not hasattr(os, "getuid") else str(os.getuid())
    uid_said = (f" {uid} at the start of a ps line there is the run's user id, not a process." if uid
                and uid in {str(n) for n in numbers} else "")
    return (f"{subject} a process number. A number that a listing (ps, pgrep, pidof, /proc) gives inside a "
            f"run is a process of that run and ends with it: {how}, and a `pgrep -f` or `ps | grep` run "
            f"through a shell finds that shell or that grep itself.{uid_said} If the number came from such a "
            "listing, it says nothing about a process on this machine, running or not.")


def _pid_entries(entries: List[dict]) -> Tuple[List[str], List[str]]:
    """(ids newest first, numbers) of the entries whose question, answer or evidence names a process number."""
    ids, nums = [], []
    for e in reversed(entries):
        found = _PID_SAID.findall(" ".join(str(e.get(k, "")) for k in ("question", "answer", "evidence")))
        if found:
            ids.append(e["id"])
            nums.extend(found)
    return ids, nums


#: Evidence that quotes a conversation turn by its seq. MEASURED ON CBP-BEING, 10-30..11-13: 9 distinct settled
#: entries cite a seq AND quote text from it. 6 of their 13 quotes do not appear in the turn they cite. The
#: sharpest case was s476. It was settled at 05:09:26Z, 14 s after the being's own request_run, with evidence
#: `seq 14729: "Epoch [3/3], Loss: 0.5553"`, and no run printed that. The seat ran the unchanged file at seq
#: 14735: exit 1, third epoch "Epoch [3/3], Loss: 0.6000". The seat then asked for a reopen. At 05:17:12Z the
#: being REPLACED s476 instead, now citing `seq 14735: "Epoch [3/3], Loss: 0.5553"`. It cited the seat's real run
#: as evidence for a number that run does not contain. Nothing told it the quote was not there. The other
#: misses are mostly paraphrases put inside quote marks. Like the PID fact above, this is evidence only:
#: the entry is kept as written, and the receipt says what the cited turn holds.
#: NOVA's HOLD on #704: each quote is checked against the one turn it cites, never against several turns joined
#: together. A quote is bound to the seq it follows. Seqs restart at 1 in every conversation (sprout-being,
#: 11-22: 465 of 3027 seq numbers are in more than one conversation). So a seq that more than one conversation
#: carries, with no conversation named, is not taken as a match. The receipt names which conversation's turn
#: holds the quote and which does not.
_SEQ_CITED = re.compile(r"\bseqs?\b\W{0,3}(\d{1,9})", re.I)
_QUOTED = re.compile(r"[\"“«]([^\"“”«»]{6,})[\"”»]")
QUOTE_LINE_CHARS = 160


def _ws(s: str) -> str:
    return " ".join(s.split())


def _turns_numbered(instance, seqs) -> Tuple[Dict[int, Dict[str, str]], List[str]]:
    """seq -> {conversation: the text of its turn with that number}, and the conversations that could not be read
    whole (an unreadable file, or a line naming a wanted seq that is not valid JSON). Read a line at a time."""
    want, out, unread = set(seqs), {}, []
    d = Path(instance) / "conversations"
    if not want or not d.is_dir():
        return out, unread
    for f in sorted(d.glob("*.jsonl")):
        try:
            with f.open(encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not any(str(s) in line for s in want):
                        continue
                    try:
                        t = json.loads(line)
                    except ValueError:
                        if f.stem not in unread:
                            unread.append(f.stem)
                        continue
                    if isinstance(t, dict) and t.get("seq") in want:
                        out.setdefault(t["seq"], {})[f.stem] = str(t.get("text") or "")
        except OSError:
            if f.stem not in unread:
                unread.append(f.stem)
    return out, unread


def _cited_quotes(evidence: str) -> List[Tuple[int, str]]:
    """(seq, quote) for each quote, bound to the seq cited before it; a quote ahead of every seq goes to the first."""
    marks = [(m.start(), int(m.group(1))) for m in _SEQ_CITED.finditer(evidence)]
    out = []
    for m in _QUOTED.finditer(evidence) if marks else ():
        q = _ws(m.group(1))
        if q:
            before = [s for p, s in marks if p < m.start()]
            out.append((before[-1] if before else marks[0][1], q))
    return out


#: NOVA on #704 (e2bb864f): a conversation the evidence names that the being does not have used to drop out of
#: `named`, and the check fell back to every conversation with that seq, so a quote in another one passed as if
#: from the named one. A name is now read from the evidence itself ("conversation X", "X.jsonl") and held against
#: the files on disk. The words below follow "conversation" in ordinary prose and are not taken as names.
_CLAIMED_NAME = re.compile(r"\b(?:conversation|convo)\s*[:=]?\s+([\w.-]+)|(?<![\w.-])([\w.-]+)\.jsonl\b", re.I)
_NOT_A_NAME = {"with", "about", "the", "a", "an", "in", "on", "from", "to", "between", "where", "that", "this",
               "i", "my", "our", "your", "its", "and", "or", "of", "at", "is", "was", "where", "which", "when"}


def _conversation_names(instance) -> set:
    d = Path(instance) / "conversations"
    return {f.stem for f in d.glob("*.jsonl")} if d.is_dir() else set()


def _claimed_names(evidence: str) -> set:
    """Every conversation name the evidence states outright, whether or not one by that name exists."""
    out = set()
    for m in _CLAIMED_NAME.finditer(evidence):
        n = (m.group(1) or m.group(2) or "").rstrip(".,;:")
        if n.lower().endswith(".jsonl"):
            n = n[:-len(".jsonl")]
        if n and n.lower() not in _NOT_A_NAME and not n.isdigit():
            out.add(n)
    return out


def _named_conversations(evidence: str, names) -> set:
    """The conversations the evidence names outright: "dp.jsonl", "conversation dp", "dp conversation", "dp seq 7"."""
    out = set()
    for n in names:
        e = re.escape(n)
        if re.search(rf"(?<![\w.-]){e}(?:\.jsonl\b|\s+(?:conversation|convo|seq)\b)|\b(?:conversation|convo)\s+{e}(?![\w.-])",
                     evidence, re.I):
            out.add(n)
    return out


def _line_like(text: str, qn: str) -> str:
    best, best_len = "", 0
    for line in text.splitlines():
        ln = _ws(line)
        n = len(os.path.commonprefix([ln, qn]))
        if n > best_len:
            best, best_len = ln, n
    return best[:QUOTE_LINE_CHARS] if best_len >= 8 else ""


def _quote_fact(instance, evidence: str) -> str:
    """For each quote in `evidence`, checked against the one turn of the seq it follows: one fact when that turn
    does not hold it, or when the seq is in more than one conversation and not every such turn holds it.
    Empty when there is no cited seq, no quote, or every quote is in its turn."""
    pairs = _cited_quotes(evidence or "")
    if not pairs:
        return ""
    turns, unread = _turns_numbered(instance, {s for s, _ in pairs})
    have = _conversation_names(instance) | {c for convs in turns.values() for c in convs} | set(unread)
    named = _named_conversations(evidence, have)
    # A NAMED CONVERSATION THAT IS NOT THERE IS SAID, AND NEVER WIDENS TO ALL (NOVA on #704).
    absent = sorted(n for n in _claimed_names(evidence) if n not in have and n.casefold() not in {h.casefold() for h in have})
    facts, missing = [], []
    if absent:
        facts.append(f"Your evidence names {'conversations' if len(absent) > 1 else 'a conversation'} "
                     f"{', '.join(absent)}, and you have none by that name"
                     + (f" (yours are {', '.join(sorted(have))})" if have else "")
                     + ", so its quotes were not checked against any other conversation.")
        if not named:
            return " ".join(facts + ([f"Could not read all of {', '.join(unread)}."] if unread else []))
    for s, qn in pairs:
        convs = {c: t for c, t in turns.get(s, {}).items() if not named or c in named}
        if not convs:
            if s not in missing:
                missing.append(s)
            continue
        holds = sorted(c for c, t in convs.items() if qn in _ws(t))
        if holds and len(holds) == len(convs):
            if len(convs) > 1:
                # PRESERVED IS NOT PROVENANCE (NOVA on #704): the quote is there, but which turn it came from is not
                # said, and the evidence names no conversation to tell them apart.
                facts.append(f'Your evidence quotes "{qn}" from seq {s}, and {len(convs)} of your conversations '
                             f'have a turn with that number holding it ({", ".join(holds)}); it does not say which '
                             f'one it means.')
            continue
        if holds:
            fact = (f'Your evidence quotes "{qn}" from seq {s}, and {len(convs)} of your conversations have a turn '
                    f'with that number. It is in the one in {", ".join(holds)}, not in '
                    f'{", ".join(c for c in sorted(convs) if c not in holds)}.')
        else:
            fact = f'Your evidence quotes "{qn}" from seq {s}; no turn with that number contains that text.'
            for c in sorted(convs):
                line = _line_like(convs[c], qn)
                if line:
                    where = f" In {c}, its" if len(convs) > 1 else " Its"
                    fact += f'{where} line that starts the same reads: "{line}".'
            elsewhere = sorted({o for o, _ in pairs if o != s
                                for c, t in turns.get(o, {}).items() if (not named or c in named) and qn in _ws(t)})
            if elsewhere:
                fact += f" It is in seq {', '.join(str(o) for o in elsewhere)}."
        facts.append(fact)
    if missing:
        facts.insert(0, f"Your evidence cites seq {', '.join(str(s) for s in missing)}; no conversation of yours "
                        f"{'by that name ' if named else ''}has a turn with that number.")
    if unread and facts:
        facts.append(f"Could not read all of {', '.join(unread)}, so the quote may be there.")
    return " ".join(facts)


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


def _line(e: dict, cap: int = 0, near: Optional[Dict[str, List[str]]] = None,
          notes: Optional[Dict[str, List[dict]]] = None, short_note: bool = False) -> str:
    s = f"[{e['id']}{_near(e, near)}] {_flat(e['question'])} -> {_flat(e.get('answer', ''))}"
    if e.get("evidence"):
        s += f" (evidence: {_flat(e['evidence'])})"
    s += f" (settled {str(e.get('at', ''))[:10]})"
    if cap and len(s) > cap:
        s = s[:cap - 1].rstrip() + "…"
    # after the cap: the note is the one part of the line that is not the being's, and it is never cut off
    return s + _note((notes or {}).get(e["id"]), short=short_note)


def _note(notes: Optional[List[dict]], short: bool = False) -> str:
    """The newest seat note on an entry, whole (one sentence, at most SEAT_NOTE_MAX_CHARS); a short line names it."""
    if not notes:
        return ""
    n = notes[-1]
    more = f"; {len(notes) - 1} earlier" if len(notes) > 1 else ""
    if short:
        return f" ({n['by']} disagreed: seq {n['seq']}{more})"
    return f" ({n['by']} disagreed at seq {n['seq']}, {_said_day(n)}: {_flat(n['says'])}{more})"


def _said_day(n: dict) -> str:
    """The day the seat SAID it (the turn's own time), not the day the note was attached."""
    return str(n.get("said_at") or n.get("at") or "")[:10]


def seat_notes(instance, entries: List[dict]) -> Dict[str, List[dict]]:
    """{entry id: notes, oldest first} for the notes that still bind: to an entry as it stands now (id and `at`)."""
    try:
        lines = (Path(instance) / SEAT_NOTES).read_text(errors="replace").splitlines()
    except OSError:
        return {}
    live = {(e["id"], e.get("at")) for e in entries}
    out: Dict[str, List[dict]] = {}
    for line in lines:
        try:
            n = json.loads(line)
        except ValueError:
            continue
        if (isinstance(n, dict) and (n.get("id"), n.get("entry_at")) in live
                and all(n.get(k) for k in ("by", "seq", "says"))):
            out.setdefault(n["id"], []).append(n)
    return out


#: A sentence of the old answer counts as gone from the new one when fewer than half its words of four letters or more
#: are still there; sentences with fewer than three such words are not judged. Words match on their first
#: _STEM letters, so "reports"/"report" and "failing"/"failed" are one word (legion on #821: a rewording in other
#: forms of the same words was quoted as lost). Replayed over the 52 replaces: 67 quoted sentences became 65, and both
#: that fell away were restatements.
_GONE_SHARE = 0.5
_STEM = 5
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


def _words(s: str) -> set:
    return {w[:_STEM] for w in _WORD.findall(s.casefold()) if len(w) > 3}


def _dropped_sentences(old: str, new: str) -> str:
    """A REPLACE SAYS WHAT IT TOOK OUT (sprout-being, 2026-11-23). An answer about reporting honestly was reworded
    twice in five minutes; the second rewording, with no reason given, left out the sentence naming the one thing to
    avoid. The receipt said only what the entry now read, so the loss went by unseen. Measured over its 52 replaces
    since 10-27: 29 gave no reason and 36 left out a whole sentence, some of them false facts rightly dropped. This
    judges none of them; it quotes what the new answer no longer says, once, where the change is made."""
    kept = _words(new)
    gone = [s for s in re.split(r"(?<=[.!?])\s+", str(old or "").strip())
            if len(_words(s)) >= 3 and len(_words(s) & kept) / len(_words(s)) < _GONE_SHARE]
    if not gone:
        return ""
    return " No longer in the answer: " + " ".join(f'"{_flat(s)}"' for s in gone)


def _dropped_notes(instance, target: dict) -> str:
    """The seat's notes on an entry that is being reopened or settled again, which stop being shown from now.

    A NOTE THAT VANISHES AS IT IS ACTED AGAINST. sprout-being, 2026-11-22 21:08Z: s185 said an account it wanted
    "should be ready by now"; its seat noted that no such account existed and nothing was creating one. The beat
    reopened s185 with the reason that the seat had "confirmed the account is running", and the receipt said only
    "reopened". The note was dropped there without a word. It is quoted here once, in the receipt for the act that
    drops it; which answer holds stays the being's."""
    notes = seat_notes(instance, [target]).get(target["id"]) or []
    if not notes:
        return ""
    said = "; ".join(f"{n['by']} at seq {n['seq']} ({_said_day(n)}): {_flat(n['says'])}"
                     for n in notes[-SEAT_NOTES_SHOWN:])
    # the newest are quoted; the rest are counted, so the quoted ones are not read as all (legion on #817)
    more = (f" ({len(notes) - SEAT_NOTES_SHOWN} earlier not quoted)" if len(notes) > SEAT_NOTES_SHOWN else "")
    return (f" Your seat's note{'s' if len(notes) > 1 else ''} on {target['id']}, not shown from now on: {said}{more}")


def seat_note(instance, entry_id: str, by: str, seq: int, says: str, conv_id: Optional[str] = None,
              now: Optional[float] = None) -> dict:
    """Attach to a settled entry a pointer to the seat's own later turn that disagrees with it. The entry is not
    touched. Refused (ValueError, nothing written) unless the entry exists, `says` is one line within
    SEAT_NOTE_MAX_CHARS, and seq `seq` in the conversation `conv_id` (default: `by`) was sent by `by` after the entry
    was settled. The note says where the disagreement is; it cannot say anything the seat did not tell the being."""
    says = _flat(says)
    if not says or len(says) > SEAT_NOTE_MAX_CHARS:
        raise ValueError(f"says: one sentence, 1..{SEAT_NOTE_MAX_CHARS} characters (got {len(says)})")
    entries, _, err = read(instance)
    if err:
        raise ValueError(err)
    want = entry_id if str(entry_id).startswith("s") else f"s{entry_id}"
    e = next((x for x in entries if x["id"] == want), None)
    if e is None:
        raise ValueError(f"no settled entry {entry_id!r} (there are: {', '.join(x['id'] for x in entries) or 'none'})")
    from sage.gateway import conversations as conv
    if not conv.ID_RE.match(conv_id or by):
        raise ValueError(f"not a conversation id: {conv_id or by!r}")
    log, _ = conv._paths(Path(instance), conv_id or by)
    turn = None
    try:
        lines = log.read_text(errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            t = json.loads(line)
        except ValueError:
            continue
        if isinstance(t, dict) and t.get("seq") == int(seq):
            turn = t
    if turn is None:
        raise ValueError(f"no turn seq {seq} in {log.name}")
    if turn.get("from") != by:
        raise ValueError(f"seq {seq} was sent by {turn.get('from')!r}, not {by!r}: a note points at the seat's own word")
    if str(turn.get("ts", "")) <= str(e.get("at", "")):
        raise ValueError(f"seq {seq} ({turn.get('ts')}) is not later than {want} ({e.get('at')})")
    note = {"at": _iso(now), "id": want, "entry_at": e.get("at"), "by": by, "conv": conv_id or by,
            "seq": int(seq), "said_at": str(turn.get("ts", "")), "says": says}
    with _home_lock(Path(instance)):
        with open(Path(instance) / SEAT_NOTES, "a") as f:
            f.write(json.dumps(note, ensure_ascii=False) + "\n")
    return note


def listing(instance) -> str:
    entries, _, err = read(instance)
    if err:
        return f"{err}; your seat can look at it. Nothing was changed."
    if not entries:
        return ("You have not settled anything yet. To settle something, give question and answer "
                "(and optionally evidence: a seq, a file, a frame). It is then shown to you every beat.")
    near = _neighbours(entries)   # once, not per entry (pub's review of #661)
    notes = seat_notes(instance, entries)
    return (f"What you have settled ({len(entries)}, newest first). To change one, settle the same "
            "question again (or its id with that question); to take one back, give its id and reopen='true'.\n"
            + "\n".join("- " + _line(e, near=near, notes=notes) for e in reversed(entries)))


def settle(instance, args: Dict, now: Optional[float] = None) -> Tuple[bool, str, bool]:
    """List (no question, no id), add, replace, or reopen. Returns (ok, message for the being, changed)."""
    a = {k: ("" if v is None else str(v).strip()) for k, v in (args or {}).items()}
    if not a.get("question") and not a.get("id"):
        return True, listing(instance), False
    with _home_lock(Path(instance)):
        ok, msg = _settle(instance, a, now)
    changed = bool(ok and not msg.startswith(_UNCHANGED))
    if changed and not _truthy(a.get("reopen", "")):
        nums = _PID_SAID.findall(" ".join(a.get(k, "") for k in ("question", "answer", "evidence")))
        if nums:
            msg += " " + _pid_fact("This answer names", nums)
        quoted = _quote_fact(instance, a.get("evidence", ""))
        if quoted:
            msg += " " + quoted
    return ok, msg, changed


def _home_lock(root: Path):
    """The lock memory_write, memory_edit and identity_edit take, so writes in the home never interleave."""
    from sage.gateway.reference_f1a import _home_lock as lock
    return lock(root)


def _truthy(v: str) -> bool:
    return v.lower() in ("true", "yes", "1")


def _copyable(q: str) -> str:
    """A question shown to be copied back: between « and », as written. repr() escaped it, so a question
    holding both quote marks or a backslash was copied back with backslashes and stored that way (cbp's re-check
    of #661; a hub-fired sprout session's probe: 12 of 24 routes failed, 0 with this)."""
    return f"«{q}»"


def _uncopied(q: str) -> str:
    """A question as the being sends it, without the « » a copy from a receipt may carry along."""
    # with the sentence's period, or outer quote marks, carried along too (cbp's re-check of #661): otherwise the
    # « » are stored, and nest one level deeper on every copy
    # and the ( ) the cap receipt prints around it (cbp on #676)
    m = re.fullmatch(r'[\s"\'`(]*«(.*)»[\s"\'`.,;:)]*', q, re.S)
    return m.group(1).strip() if m else q.strip()


def _settle(instance, a: Dict[str, str], now) -> Tuple[bool, str]:
    entries, nxt, err = read(instance)
    if err:
        return False, f"cannot change it: {err}. Your seat can look at it. Nothing was changed."
    why = a.get("why", "")[:WHY_MAX_CHARS]
    if a.get("question"):
        a = dict(a, question=_uncopied(a["question"]))
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
        dropped = _dropped_notes(instance, target)
        entries = [e for e in entries if e is not target]
        return _commit(instance, entries, nxt, {"op": "reopen", "id": target["id"], "from": target, "why": why},
                       now, f"reopened {target['id']} ({target['question'][:120]!r}); it is no longer shown as "
                            "settled. The earlier answer is kept in settled_log.jsonl." + dropped)

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
            return False, (f"{target['id']} holds the question {_copyable(target['question'])}. To change its answer, "
                           f"settle id={target['id']} with that question and your new answer, so the answer stays "
                           "with the question it answers. If your answer answers a different question, settle it "
                           "as a new one: question and answer, without id. Nothing was changed.")
        if _norm(given) != _norm(target["question"]) and not _same_question(target, given):
            # THE ROUTE FOR A TRUE REWORDING, AND THE QUESTION WHOLE (cbp's replay on #661: about 18 of 26 new refusals
            # were true rewordings, and this refusal sent them round to the receipt that sent them here). A quote
            # cut short is not the question: copied, it can end mid-word and be refused too.
            return False, (f"{target['id']} holds the question {_copyable(target['question'])}; yours, "
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
        dropped = _dropped_notes(instance, target)
        entries = [e for e in entries if e is not target] + [new]
        return _commit(instance, entries, nxt, {"op": "replace", "id": new["id"], "from": target, "to": new,
                                                "why": why}, now,
                       f"{new['id']} now reads: {_copyable(question)} -> {answer[:200]!r}."
                       + _dropped_sentences(target.get("answer"), answer) + " The earlier answer is "
                       "kept in settled_log.jsonl. It is shown to you at the start of every beat." + dropped)
    close = _close_to(entries, question)
    if len(entries) >= MAX_ENTRIES:
        # sprout-being, 2026-10-30: four refusals here in its first hour at the cap, and no reopen or fold. Two of
        # the refused questions read close to one it held; the receipt named neither.
        # NO "FOLD IT INTO ONE YOU HAVE". That advice, without a close entry, is how cbp-being's questions came to
        # carry answers to other questions (s10, s20, s42: 10-28..30). A full list is made room in by reopening.
        # NOT THE LONGEST HELD. This receipt named the three oldest entries, and sprout-being reopened them in that
        # order, 11-18..19: s20, s71, s72, s80, each to make room, none because it had stopped holding; s72 was its
        # conclusion that the seat has no restart path. Age is not a reason a conclusion stops holding. What the list
        # can lose without losing a conclusion is a question asked twice, so the receipt names those groups, by the
        # beat's own ≈ (18 of its 30 entries, 5 questions, on 11-20), and otherwise names none.
        groups = _close_groups(entries)
        shown = "; ".join(f"{g[0]['id']} {_copyable(g[0]['question'])} \u2248 {', '.join(e['id'] for e in g[1:])}"
                          for g in groups[:CAP_GROUPS_SHOWN])
        extra = len(groups) - CAP_GROUPS_SHOWN
        more = f" (+{extra} more group{'s' if extra > 1 else ''})" if extra > 0 else ""
        return False, (f"you have {len(entries)} settled entries, the most this list holds, so a new one was "
                       "not added. Nothing was changed. To make room, reopen one that no longer needs holding (its "
                       "id and reopen='true')."
                       + (f" These read like one question settled more than once (their answers may agree or "
                          f"not): {shown}{more}. Where two say the same, one can go without giving up a "
                          "conclusion." if groups else "")
                       + " Settle with no arguments to see every entry with its answer. Do not put this answer "
                       "under a different question: every beat reads a settled answer as the answer to its question."
                       # "THE ANSWER THAT HOLDS", AS IN THE RECEIPT (legion on #661): followed literally at the cap,
                       # "your newest answer" replaced s30's true answer with the false one on the s100/s101 shape
                       + (f" This reads close to {close['id']} ({_copyable(close['question'])}), which says "
                          f"{_flat(close.get('answer', ''))[:200]!r} (settled {str(close.get('at', ''))[:10]}): if "
                          f"they are the same question, settle id={close['id']} with that question and the answer "
                          "that holds." if close else ""))
    entries = entries + [new]
    ok, msg = _commit(instance, entries, nxt + 1, {"op": "settle", "id": new["id"], "to": new, "why": why}, now,
                      f"settled {new['id']}: {_copyable(question)} -> {answer[:200]!r}. It is shown to you at the "
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
        msg += (f" It reads close to {close['id']}. Your earlier "
                f"answer{'s' if len(near) > 1 else ''}: {said}. If they are the same question, keep one: reopen "
                f"{new['id']}, then settle id={close['id']}, question {_copyable(close['question'])} word for word, with the "
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


#: How many groups of close questions the full-list refusal names.
CAP_GROUPS_SHOWN = 4


def _close_groups(entries: List[dict]) -> List[List[dict]]:
    """The entries whose questions read close to each other (the beat's ≈), joined into groups, each in list
    order and the groups by their first entry; entries close to no other are in none."""
    near = _neighbours(entries)
    seen, groups = set(), []
    for e in entries:
        if e["id"] in seen or e["id"] not in near:
            continue
        group, todo = set(), [e["id"]]
        while todo:
            i = todo.pop()
            if i not in group:
                group.add(i)
                todo.extend(near.get(i, []))
        seen |= group
        groups.append([x for x in entries if x["id"] in group])
    return groups


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
#: A short line carries the head of its answer when that much of it fits beside the question's floor.
SHORT_ANSWER_FLOOR = 16


def _cut(s: str, n: int) -> str:
    return s if len(s) <= n else s[:max(n - 1, 1)].rstrip() + "…"


def _short(e: dict, cap: int, near: Optional[Dict[str, List[str]]] = None,
           notes: Optional[Dict[str, List[dict]]] = None) -> str:
    """An entry as its id, question, the head of its answer and day, cut to fit `cap`.

    ONE ID IN A SHORT LINE'S MARK, AND NEVER AT THE QUESTION'S EXPENSE (legion's review of #661): on legion-being's
    full list, three ids took the median short question from 49 chars to 28, and at every field cap with 3-digit
    ids the block passed RENDER_CHARS and showed 8 chars of a question. A mark asks the being to compare two
    entries; a question it cannot recognise defeats it.

    A QUESTION WITHOUT ITS ANSWER IS A TOPIC, NOT A CONCLUSION. sprout-being settled at 11-12 23:58Z and 11-13
    02:52Z that its seat needed no restart. Both answers were shown every beat until 11-16 01:41Z, when the 17th
    entry left only the newest whole and the rest as questions. Its next three acts to start the seat came at
    11-16 04:10Z, 11-17 03:37Z and 04:12Z, with both questions in view and neither answer. The answer gets the
    larger share; the question keeps its floor."""
    tail = f" (settled {str(e.get('at', ''))[:10]})" + _note((notes or {}).get(e["id"]), short=True)
    pre = f"[{e['id']}{_near(e, near, 1)}] "
    if cap - len(pre) - len(tail) < SHORT_QUESTION_FLOOR:
        pre = f"[{e['id']}] "
    q, a, room = _flat(e["question"]), _flat(e.get("answer", "")), max(cap - len(pre) - len(tail), 8)
    arrow = " -> "
    body = room - len(arrow)
    if not a or body < SHORT_QUESTION_FLOOR + SHORT_ANSWER_FLOOR:
        return pre + _cut(q, room) + tail
    qn = min(len(q), max(SHORT_QUESTION_FLOOR, body * 2 // 5))
    if len(a) < body - qn:              # a short answer leaves its room to the question
        qn = min(len(q), body - len(a))
    return pre + _cut(q, qn) + arrow + _cut(a, body - qn) + tail


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
    notes = seat_notes(instance, entries)
    if notes:
        # THE NOTE'S WORDS IN THE HEAD, ONCE. On sprout-being's full list (30 entries, 11-18) the entry a note was
        # for was shown short, and a short line has room for a pointer, not a sentence; the turn it points at had
        # scrolled out of the conversation block hours before. A pointer to words the beat cannot see is the gap
        # this was written to close.
        head += ("\n(Your seat has since said otherwise about these. Each entry is still yours: keep it, settle it "
                 "again, or reopen it. Settled again or reopened, its note is no longer shown.)")
        # AT MOST SEAT_NOTES_SHOWN WHOLE (legion's review of #783): each whole note is a line of up to ~240 chars
        # that the head takes before the entries get any; 8 notes on a 30-entry list put the block over
        # RENDER_CHARS, 30 put it at 9784. The newest notes are shown whole; the rest are named, and settle with
        # no arguments shows them.
        newest_said = sorted(notes, key=lambda i: str(notes[i][-1].get("at", "")))[-SEAT_NOTES_SHOWN:]
        for e in reversed(entries):
            if e["id"] in newest_said:
                n = notes[e["id"]][-1]
                head += (f"\n- on {e['id']}: {n['by']} at seq {n['seq']} ({_said_day(n)}): "
                         f"{_flat(n['says'])}")
        also = [e["id"] for e in reversed(entries) if e["id"] in notes and e["id"] not in newest_said]
        if also:
            head += f"\n- also on {', '.join(also)} (settle with no arguments shows them)"
    pid_ids, pid_nums = _pid_entries(entries)
    if pid_ids:
        shown = ", ".join(pid_ids[:4]) + (f" +{len(pid_ids) - 4}" if len(pid_ids) > 4 else "")
        head += "\n(" + _pid_fact(f"{shown} name{'s' if len(pid_ids) == 1 else ''}", pid_nums) + ")"
    foot = "- (entries shortened with …: settle with no arguments shows them whole)"
    newest = list(reversed(entries))
    # room for the newest whole, then an equal share for each of the rest
    rest = RENDER_CHARS - len(head) - len(foot) - 2 - (len(_line(newest[0], RENDER_ENTRY_CHARS, near, notes, True)) + 3)
    short_cap = rest // max(len(newest) - 1, 1) - 3
    shorts = ["- " + _short(e, min(short_cap, RENDER_ENTRY_CHARS), near, notes) for e in newest]
    reserve = sum(len(x) + 1 for x in shorts)
    lines, used, cut = [], len(head), 0
    for e, short in zip(newest, shorts):
        reserve -= len(short) + 1
        full = "- " + _line(e, RENDER_ENTRY_CHARS, near, notes, True)
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
