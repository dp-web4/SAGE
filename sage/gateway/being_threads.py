"""retire_thread: close a whole line of work at once -- its open todo items and its settled entries.

WHY THIS EXISTS. dp, 2026-11-01, to cbp-being: "retire the whole hestia thread and work on something
different." The being could not have done it with what it had. On that day 550 of its 584 open todo
items and 29 of its 30 settled entries were on that one thread, and every one of them reached every
beat. `retire_note todo.md` starts a fresh todo but carries forward EVERY open item (it never drops
one, by design), and `settle` replaces or reopens one entry per act. So a single person's turn saying
"stop" sat against hundreds of lines saying "the daemon is down, fix it", and the next beat's own
account still read "WANT: to understand why the Hestia daemon is not running". Nothing it could do
said "this whole line is finished".

WHAT IT DOES. Given topic words (comma separated) and a reason, every OPEN todo item and every settled
entry that names one of the words is moved out of what the beat shows, into one retired file at the
home root (todo.retired-thread-<hash>.md, named by the words and reason). recall still searches that file (home_recall indexes
todo.retired-*), so nothing is lost and a deliberate search finds it; it just stops arriving uninvited.
Done items, other open items and other settled entries are untouched. The retired file keeps the old
todo.md whole below a header that lists exactly what was taken out, and settled_log.jsonl records each
entry removed, so the change is auditable and reversible by hand.

A word matches at the start of a word ("install" matches "installer", "scope" matches "scopes", "api"
does not match "rapid"), case-insensitively. `preview='true'` reports what would move and writes
nothing, so a being (or its seat) can check a word list before using it.

A BROAD RETIRE IS CONFIRMED FROM ITS OWN PREVIEW (NOVA on #619, after Codex's candidate d217a7a8). A
selection that takes a strict majority of the open todo or of the settled list (and at least two) needs
`confirmation`: a one-use value a preview WITH THE SAME WORDS AND REASON returned, bound to the exact
todo bytes and settled entries it previewed, valid for five minutes in this process. A changed source
consumes it. It is coordination evidence that the selection was looked at, not a grant: the gate still
decides the act.

ONLY QUESTION AND ANSWER SELECT A SETTLED ENTRY. Evidence explains how a conclusion was supported; a
shared citation or tool name does not make every conclusion about that topic (NOVA, item 1).

A FAILURE AFTER THE FIRST WRITE IS REPORTED AS POSSIBLY PARTIAL, never as "nothing was retired": the
archive (which carries the exact prior todo and settled bytes, base64) is kept as recovery evidence,
the todo is restored from its exact bytes, and the result says what is known (NOVA, item 3).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

TODO = "todo.md"
MIN_WORD = 3          # shorter words match too much to be a topic ("ap", "in")
MAX_WORDS = 100       # cbp-being's hestia thread (11-01) took 68 to cover without catching its own work
REASON_MAX = 600
STOPWORDS = frozenset({"the", "and", "for", "with", "this", "that", "from"})
_PREVIEW_TTL = 300.0
_PREVIEW_CAP = 128
_preview_lock = threading.Lock()
_previews: Dict[str, Tuple[str, float]] = {}   # one-use, in-process; never authority or durable proof


def _stamp(now: Optional[float]) -> datetime:
    return datetime.fromtimestamp(now, timezone.utc) if now is not None else datetime.now(timezone.utc)


def words_of(raw) -> List[str]:
    if isinstance(raw, (list, tuple)):
        parts = [str(x) for x in raw]
    else:
        parts = str(raw or "").split(",")
    out = []
    for p in parts:
        w = re.sub(r"\s+", " ", p).strip()
        if w and w.lower() not in (x.lower() for x in out):
            out.append(w)
    return out


def matcher(words: List[str]) -> Callable[[str], bool]:
    pats = [re.compile((r"\b" if re.match(r"\w", w) else "") + re.escape(w), re.I) for w in words]
    return lambda text: any(p.search(text or "") for p in pats)


def _reason_of(args: Dict) -> str:
    return re.sub(r"\s+", " ", str((args or {}).get("reason") or "")).strip()[:REASON_MAX]


def archive_name(args: Dict) -> str:
    """The retired file this call writes, from the call's OWN arguments and nothing else.

    NOVA's hold on #619 (1bd4fd69): the first cut picked the name from the home's listing, once when the
    gate was told the write set and again after the lock was taken, so a retire landing in between moved
    this one to "-2", a path the gate never saw. A name that is a function of (words, reason) is the same
    at both points. If that file already exists (the same words and reason were used before), the retire
    is REFUSED rather than renamed: no path outside the declared set is ever written."""
    key = json.dumps([[w.lower() for w in words_of(args.get("words"))], _reason_of(args)])
    return f"todo.retired-thread-{hashlib.sha256(key.encode()).hexdigest()[:12]}.md"


def _tmp(name: str) -> str:
    return f".{name}.tmp"           # _write_atomic's temp file for `name`


def writes(args: Dict) -> Tuple[str, ...]:
    """Every file a (non-preview) retire_thread opens for writing in the home, for the gate: todo.md and
    its temp, the archive and its temp (NOVA, 1bd4fd69: the temp was undeclared), and settled's own."""
    from sage.gateway.being_settled import SETTLED_WRITES
    arch = archive_name(args)
    return (TODO, _tmp(TODO), arch, _tmp(arch)) + tuple(SETTLED_WRITES)


def _write_atomic(p: Path, text) -> None:
    tmp = p.with_name(_tmp(p.name))
    with open(tmp, "wb" if isinstance(text, bytes) else "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def _fresh_todo(items: List[Tuple[str, Optional[datetime]]], stamp: datetime, retired_as: str) -> str:
    """A todo.md holding exactly `items`, each under the date it was opened (as retire_note's fresh
    todo does, so todo_open reads the same ages: Nova's review of 0557d9bcf)."""
    if not items:
        return f"{stamp:%Y-%m-%d %H:%M} UTC\nstill open: none\n"
    out = [f"Carried forward from {retired_as} on {stamp:%Y-%m-%d %H:%M} UTC: every item still open "
           f"that is not on the retired thread, each under the date it was opened.\n"]
    last = None
    for t, since in sorted(items, key=lambda x: (x[1] is not None, x[1] or stamp)):
        if since is not None and since != last:
            out.append(f"{since:%Y-%m-%d %H:%M} UTC\n")
            last = since
        out.append(f"- [ ] {t}\n")
    return "".join(out)


def plan(instance: Path, words: List[str]):
    """(todo_body, kept_items, moved_items, entries, nxt, moved_entries, error) -- reads only."""
    from sage.gateway import being_settled as st
    from sage.gateway.heartbeat import _todo_items
    instance = Path(instance)
    hit = matcher(words)
    raw = _todo_bytes(instance)
    try:
        body = raw.decode("utf-8") if raw is not None else ""
    except UnicodeDecodeError:   # a replacement decode would rewrite unrelated bytes on retire
        return "", [], [], [], 0, [], "todo.md is not valid UTF-8; repair its encoding before retiring"
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    items = list(_todo_items(body).values()) if body else []
    moved = [x for x in items if hit(x[0])]
    kept = [x for x in items if not hit(x[0])]
    entries, nxt, err = st.read(instance)
    gone = [e for e in entries if hit(f"{e.get('question', '')} {e.get('answer', '')}")]
    return body, kept, moved, entries, nxt, gone, err


def _todo_bytes(instance: Path) -> Optional[bytes]:
    p = Path(instance) / TODO
    return p.read_bytes() if p.exists() else None


def _broad(kept, moved, entries, gone) -> bool:
    """At least two, and a strict majority of either collection."""
    return ((len(moved) >= 2 and len(moved) * 2 > len(moved) + len(kept))
            or (len(gone) >= 2 and len(gone) * 2 > len(entries)))


def _binding(instance: Path, words: List[str], reason: str, entries, nxt) -> str:
    """The full source state a confirmation is bound to: exact todo bytes and every settled entry."""
    raw = _todo_bytes(instance)
    return hashlib.sha256(json.dumps(
        {"home": os.path.realpath(instance), "words": [w.lower() for w in words], "reason": reason,
         "todo": base64.b64encode(raw).decode("ascii") if raw is not None else None,
         "entries": entries, "next": nxt}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _issue(binding: str) -> str:
    now = time.monotonic()
    with _preview_lock:
        for k, (_, exp) in list(_previews.items()):
            if exp <= now:
                del _previews[k]
        while len(_previews) >= _PREVIEW_CAP:
            del _previews[next(iter(_previews))]
        token = secrets.token_urlsafe(16)       # 22 characters, 128 random bits
        _previews[token] = (binding, now + _PREVIEW_TTL)
    return token


def _consume(token, binding: str) -> str:
    if token is None:
        return "missing"
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{22}", token.strip()):
        return "unknown"
    with _preview_lock:
        rec = _previews.pop(token.strip(), None)
    if not rec or rec[1] <= time.monotonic():
        return "unknown"
    return "accepted" if secrets.compare_digest(rec[0], binding) else "changed"


def retire_thread(instance, args: Dict, now: Optional[float] = None, by: str = "") -> Tuple[bool, str, bool]:
    """Returns (ok, message, changed)."""
    from sage.gateway import being_settled as st
    a = args or {}
    words = words_of(a.get("words"))
    reason = _reason_of(a)
    preview = str(a.get("preview") or "").strip().lower() in ("true", "yes", "1")
    if not words:
        return False, ("retire_thread needs 'words': the topic, as words separated by commas, e.g. "
                       "words='hestia, daemon, port 7711'. Every open todo item and settled entry naming "
                       "one of them is retired."), False
    short = [w for w in words if len(w) < MIN_WORD]
    if short:
        return False, (f"each word needs at least {MIN_WORD} characters, so it names a topic rather than "
                       f"matching everything: {', '.join(repr(w) for w in short)}. Nothing was changed."), False
    if len(words) > MAX_WORDS:
        return False, f"at most {MAX_WORDS} words in one retire; nothing was changed.", False
    if any(w.casefold() in STOPWORDS for w in words):
        return False, "a common word is not a topic; choose more specific words. Nothing was changed.", False
    if not preview and not reason:
        return False, ("retire_thread needs a 'reason': why this line of work is finished. It is written "
                       "at the top of the retired file. (preview='true' shows what would move without one.)"), False
    instance = Path(instance)
    if preview:
        # A PREVIEW TAKES NO LOCK (NOVA on 577adb4b): _home_lock opens .home.lock in append mode, which
        # creates it on a fresh home, a write thread_paths does not declare for a preview. It only reads.
        return _preview(instance, words, reason)
    with st._home_lock(instance):
        body, kept, moved, entries, nxt, gone, err = plan(instance, words)
        if err:
            return False, f"cannot prepare the retire: {err}. Nothing was changed.", False
        confirmation = a.get("confirmation")
        if _broad(kept, moved, entries, gone) or confirmation is not None:
            status = _consume(confirmation, _binding(instance, words, reason, entries, nxt))
            if status != "accepted":
                why = {"missing": f"This retire takes most of a list ({len(moved)} of {len(moved) + len(kept)} "
                                  f"open items, {len(gone)} of {len(entries)} settled), so it needs the "
                                  f"confirmation a preview with the same words and reason returns.",
                       "unknown": "That confirmation is unknown, mistyped or expired (five minutes, this beat).",
                       "changed": "Your todo, settled list, words or reason changed since that preview; the "
                                  "confirmation is used up."}[status]
                return False, (f"{why} Preview again with preview='true' and the same reason, then retire with "
                               f"the confirmation it gives. Nothing was changed."), False
        topic = ", ".join(words)
        if not moved and not gone:
            return True, (f"Nothing names {topic}: no open todo item and no settled entry. Nothing was "
                          f"changed."), False
        stamp = _stamp(now)
        name = archive_name(a)
        if (instance / name).exists():
            return False, (f"a retire with these same words and reason already wrote {name}; nothing was "
                           f"changed. Give a different reason (say what is new) to retire again."), False
        head = [f"> RETIRED {stamp:%Y-%m-%d %H:%M}Z with retire_thread"
                + (f" (by {by})" if by else "") + f". Topic words: {topic}.",
                f"> No longer current: {reason}", "",
                f"## Settled entries retired ({len(gone)})", ""]
        head += [f"- [{e['id']}] {st._flat(e['question'])} -> {st._flat(e.get('answer', ''))}"
                 + (f" (evidence: {st._flat(e['evidence'])})" if e.get("evidence") else "")
                 + f" (settled {str(e.get('at', ''))[:10]})" for e in gone]
        head += ["", f"## Open todo items retired ({len(moved)})", ""]
        head += [(f"- [ ] {t}" + (f" (since {s:%Y-%m-%d %H:%M} UTC)" if s else "")) for t, s in moved]
        todo_raw = _todo_bytes(instance)
        settled_p = instance / st.SETTLED_FILE
        settled_raw = settled_p.read_bytes() if settled_p.exists() else None
        b64 = lambda b: "absent" if b is None else base64.b64encode(b).decode("ascii")  # noqa: E731
        head += ["", "## Exact prior todo.md (base64, for recovery)", "", b64(todo_raw),
                 "", "## Exact prior settled.json (base64, for recovery)", "", b64(settled_raw)]
        head += ["", "> The todo.md this retire replaced, kept whole below, as it was written.", "", ""]
        arch = instance / name
        _write_atomic(arch, "\n".join(head) + body)    # before this, nothing has changed
        todo = instance / TODO
        try:
            if moved:
                _write_atomic(todo, _fresh_todo(kept, stamp, name))
        except OSError as e:
            return False, (f"the retire may be partial ({type(e).__name__} writing todo.md). {name} holds "
                           f"the exact prior todo and settled list; ask your seat before retrying."), True
        if gone:
            left = [e for e in entries if e not in gone]
            try:
                ok, msg = st._commit(instance, left, nxt,
                                     {"op": "retire_thread", "words": words, "ids": [e["id"] for e in gone],
                                      "from": gone, "to": name, "why": reason, **({"by": by} if by else {})},
                                     now, "ok")
            except OSError as e:
                ok, msg = False, f"the settled commit raised {type(e).__name__}"
            if not ok:
                # _commit can fail AFTER its own rollback failed, so a failure is never read as a no-op:
                # the todo is restored from its exact bytes and the archive stays as recovery evidence.
                state = "todo.md was not changed"
                if moved:
                    try:
                        _write_atomic(todo, todo_raw if todo_raw is not None else b"")
                        state = "todo.md was restored"
                    except OSError:
                        state = "todo.md could NOT be restored"
                return False, (f"{msg}. The retire may be partial; {state}. {name} holds the exact prior "
                               f"todo and settled list; ask your seat before retrying."), True
    said = (f"Retired the thread ({topic}): {len(moved)} open todo item(s) and {len(gone)} settled "
            f"entr{'y' if len(gone) == 1 else 'ies'} moved to {name}, where recall still finds them. "
            f"Still open: {len(kept)} todo item(s); still settled: {len(entries) - len(gone)}. Your reason is "
            f"shown in every beat among the lines of work you closed, until {CLOSED_SHOWN} newer closings "
            f"replace it.")
    return True, said, True


#: The beat's block of closed lines: the newest few, each reason cut to fit.
CLOSED_SHOWN = 4
CLOSED_REASON_CHARS = 240
CLOSED_WORDS_CHARS = 80   # topic words can be a whole todo sentence (598 chars on cbp; legion on #662)
# the optional " (by <who>)" may hold dots (a dotted member id, "v0.3 seat"): McNugget on #662
_HEAD = re.compile(r"^> RETIRED (\d{4}-\d{2}-\d{2} \d{2}:\d{2})Z with retire_thread(?: \(by [^)]*\))?\. "
                   r"Topic words: (.*)\.\s*$")
_WHY = re.compile(r"^> No longer current: (.*)$")


def closed(instance) -> List[Dict[str, str]]:
    """Every line of work this home closed with retire_thread, newest first: {at, words, reason, file}, read from
    the first two lines of each retired file (the header retire_thread writes). Unreadable files are skipped."""
    out = []
    for f in Path(instance).glob("todo.retired-thread-*.md"):
        try:
            with open(f, errors="replace") as fh:
                h, w = fh.readline().rstrip("\n"), fh.readline().rstrip("\n")
        except OSError:
            continue
        mh, mw = _HEAD.match(h), _WHY.match(w)
        if mh and mw:
            out.append({"at": mh.group(1), "words": mh.group(2), "reason": mw.group(1).strip(), "file": f.name})
    # (at, file): `at` has minute resolution and two closes can share a minute (legion on #662)
    return sorted(out, key=lambda c: (c["at"], c["file"]), reverse=True)


def render_closed(instance) -> str:
    """The beat's block: the lines of work it closed most recently, with its own reason for each. Empty until
    one is closed.

    A CLOSED LINE OF WORK LEFT NO TRACE IN THE BEAT, SO ITS CONCLUSION LEFT WITH IT. Measured on sprout-being,
    11-03..09: 11 retires. At 08:11Z on 11-07 it retired its seat thread with a reason stating that the seat was
    answering and nothing needed restarting, which took 15 settled entries out of view, two of them true. The
    reason was written only into the retired file. By 22:46Z it had settled the opposite, and it asked the seat
    to restart itself 20 times the next day. Retiring is meant to stop a finished line arriving uninvited, and it did, but
    the beat then held nothing that said the line was finished, or why. This shows the why (the being's own
    reason, the day, the topic words); the items stay retired. (Docstrings here describe the being's records;
    they do not quote them: being records are private.)"""
    try:
        cs = closed(instance)
    except Exception:
        return ""
    if not cs:
        return ""
    head = ("## Lines of work you closed (newest first, with your own reason when you closed each; the items "
            "you retired stay in the retired files, where recall finds them)")
    lines = []
    for c in cs[:CLOSED_SHOWN]:
        why = c["reason"]
        if len(why) > CLOSED_REASON_CHARS:
            why = why[:CLOSED_REASON_CHARS - 1].rstrip() + "…"
        words = c["words"]
        if len(words) > CLOSED_WORDS_CHARS:
            words = words[:CLOSED_WORDS_CHARS - 1].rstrip() + "…"
        lines.append(f"- {c['at']}Z, {words}: {why}")
    if len(cs) > CLOSED_SHOWN:
        lines.append(f"- … {len(cs) - CLOSED_SHOWN} earlier (todo.retired-thread-*.md)")
    return head + "\n" + "\n".join(lines)


def _preview(instance: Path, words: List[str], reason: str = "") -> Tuple[bool, str, bool]:
    from sage.gateway import being_settled as st
    body, kept, moved, entries, nxt, gone, err = plan(instance, words)
    if err:
        return False, f"cannot read your settled list: {err}. Nothing was changed.", False
    topic = ", ".join(words)
    lines =[f"PREVIEW, nothing was changed. Words: {topic}. "
             f"{len(moved)} of {len(moved) + len(kept)} open todo item(s) and {len(gone)} of "
             f"{len(entries)} settled entr{'y' if len(entries) == 1 else 'ies'} would be retired."]
    lines += [f"- settled [{e['id']}] {st._flat(e['question'])[:140]}" for e in gone]
    lines += [f"- todo: {t[:140]}" for t, _ in moved[:20]]
    if len(moved) > 20:
        lines.append(f"- … and {len(moved) - 20} more todo item(s)")
    lines += [f"- STAYS: {t[:140]}" for t, _ in kept[:10]]
    if _broad(kept, moved, entries, gone):
        if reason:
            lines.append(f"This takes most of a list, so it needs this confirmation: "
                         f"{_issue(_binding(instance, words, reason, entries, nxt))} -- retire with the same "
                         f"words and reason and confirmation='<it>' in this beat, within five minutes. It is "
                         f"used once, and any change to your todo or settled list before then voids it.")
        else:
            lines.append("This takes most of a list: preview again WITH the reason to get a confirmation.")
    return True, "\n".join(lines), False
