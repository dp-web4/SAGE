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
nothing, so a being (or its seat) can check a word list before using it. A broad selection needs
a one-use, short-lived confirmation from a preview of the same words, reason and full source state.
It is process-local coordination evidence, not proof that a human reviewed the result or a grant of
authority. The existing gate remains necessary. A restart expires pending confirmations.
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
STOPWORDS = frozenset({"the", "and", "for"})
_PREVIEW_TTL = 300.0
_PREVIEW_CAP = 128
_preview_lock = threading.Lock()
_previews = {}  # one-use in-process confirmations; never authority or durable proof


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


def _write_atomic(p: Path, text: str | bytes) -> None:
    tmp = p.with_name(_tmp(p.name))
    stream = open(tmp, "wb") if isinstance(text, bytes) else open(tmp, "w", encoding="utf-8")
    with stream as f:
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


_TODO_UNREAD = object()


def _read_todo_bytes(instance: Path) -> Optional[bytes]:
    try:
        return (instance / TODO).read_bytes()
    except FileNotFoundError:
        return None


def plan(instance: Path, words: List[str], *, todo_snapshot=_TODO_UNREAD):
    """(todo_body, kept_items, moved_items, entries, nxt, moved_entries, error) -- reads only."""
    from sage.gateway import being_settled as st
    from sage.gateway.heartbeat import _todo_items
    instance = Path(instance)
    hit = matcher(words)
    try:
        raw = _read_todo_bytes(instance) if todo_snapshot is _TODO_UNREAD else todo_snapshot
        # The todo format is UTF-8 text. Replacement decoding could rewrite
        # unrelated damaged bytes on retirement; fail before changing records.
        body = raw.decode("utf-8") if raw is not None else ""
    except UnicodeDecodeError:
        return "", [], [], [], 0, [], "todo.md is not valid UTF-8; repair its encoding before retirement"
    except OSError as exc:
        return "", [], [], [], 0, [], f"cannot read todo.md ({type(exc).__name__})"
    # Match the universal-newline behavior of the former Path.read_text call.
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    items = list(_todo_items(body).values()) if body else []
    moved = [x for x in items if hit(x[0])]
    kept = [x for x in items if not hit(x[0])]
    entries, nxt, err = st.read(instance)
    # Evidence explains how a conclusion was supported; a shared citation or
    # tool name does not make every conclusion about that source's topic.
    gone = [e for e in entries if hit(f"{e.get('question', '')} {e.get('answer', '')}")]
    return body, kept, moved, entries, nxt, gone, err


def _broad(kept, moved, entries, gone):
    """Two or more matches and a strict majority of either affected collection."""
    return ((len(moved) >= 2 and len(moved) * 2 > len(moved) + len(kept)) or
            (len(gone) >= 2 and len(gone) * 2 > len(entries)))


def _preview_binding(instance, words, reason, todo_bytes, entries, nxt):
    # Bind complete semantic source state, not just counts or the first 20
    # items rendered. This digest is not an authentication or authority claim.
    raw = json.dumps({"instance": os.path.realpath(instance), "words": [w.lower() for w in words],
                      "reason": reason, "todo_bytes": (base64.b64encode(todo_bytes).decode("ascii")
                                                          if todo_bytes is not None else None),
                      "entries": entries, "next": nxt},
                     sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _issue_confirmation(binding):
    current = time.monotonic()
    with _preview_lock:
        for key, (_, expiry) in list(_previews.items()):
            if expiry <= current:
                del _previews[key]
        while len(_previews) >= _PREVIEW_CAP:
            del _previews[next(iter(_previews))]
        # 128 random bits in 22 URL-safe characters: shorter to transcribe,
        # while still unpredictable and never an authorization grant.
        token = secrets.token_urlsafe(16)
        _previews[token] = (binding, current + _PREVIEW_TTL)
    return token


def _consume_confirmation(token, binding):
    if token is None:
        return "missing"
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{22}", token):
        return "unknown"
    with _preview_lock:
        record = _previews.pop(token, None)
    if not record or record[1] <= time.monotonic():
        return "unknown"
    if not secrets.compare_digest(record[0], binding):
        return "changed"
    return "accepted"


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
        return False, "a common stopword is not a topic; choose more specific words. Nothing was changed.", False
    if not preview and not reason:
        return False, ("retire_thread needs a 'reason': why this line of work is finished. It is written "
                       "at the top of the retired file. (preview='true' shows what would move without one.)"), False
    instance = Path(instance)
    if preview:
        # A PREVIEW TAKES NO LOCK (NOVA on 577adb4b): _home_lock opens .home.lock in append mode, which
        # creates it on a fresh home, a write thread_paths does not declare for a preview. It only reads.
        return _preview(instance, words, reason)
    with st._home_lock(instance):
        try:
            todo_bytes = _read_todo_bytes(instance)
        except OSError as exc:
            return False, f"cannot read todo.md ({type(exc).__name__}); nothing was changed.", False
        body, kept, moved, entries, nxt, gone, err = plan(instance, words, todo_snapshot=todo_bytes)
        if err:
            return False, f"cannot prepare retirement: {err}. Nothing was changed.", False
        confirmation = a.get("confirmation")
        if _broad(kept, moved, entries, gone) or confirmation is not None:
            binding = _preview_binding(instance, words, reason, todo_bytes, entries, nxt)
            status = _consume_confirmation(confirmation, binding)
            if status != "accepted":
                explanation = {
                    "missing": "No confirmation was provided for this broad retirement.",
                    "unknown": "Confirmation is unknown, mistyped or expired; a later beat or restart may lose it.",
                    "changed": "The source, words or reason changed since preview; that confirmation is consumed.",
                }[status]
                return False, (f"{explanation} Make a fresh preview with the reason, then confirm in the same beat. "
                               "No todo or settled records were changed."), False
        topic = ", ".join(words)
        if not moved and not gone:
            return True, (f"Nothing names {topic}: no open todo item and no settled entry. Nothing was "
                          f"changed."), False
        stamp = _stamp(now)
        name = archive_name(a)
        if (instance / name).exists():
            return False, (f"a retire with these same words and reason already wrote {name}; nothing was "
                           f"changed. Give a different reason (say what is new) to retire again."), False
        settled_path = instance / st.SETTLED_FILE
        try:
            settled_before = settled_path.read_bytes() if settled_path.exists() else None
        except OSError as exc:
            return False, f"cannot snapshot the settled list ({type(exc).__name__}); nothing was retired.", False
        head = [f"> RETIRED {stamp:%Y-%m-%d %H:%M}Z with retire_thread"
                + (f" (by {by})" if by else "") + f". Topic words: {topic}.",
                f"> No longer current: {reason}", "",
                f"## Settled entries retired ({len(gone)})", ""]
        head += [f"- [{e['id']}] {st._flat(e['question'])} -> {st._flat(e.get('answer', ''))}"
                 + (f" (evidence: {st._flat(e['evidence'])})" if e.get("evidence") else "")
                 + f" (settled {str(e.get('at', ''))[:10]})" for e in gone]
        head += ["", f"## Open todo items retired ({len(moved)})", ""]
        head += [(f"- [ ] {t}" + (f" (since {s:%Y-%m-%d %H:%M} UTC)" if s else "")) for t, s in moved]
        head += ["", "## Original todo snapshot (base64; exact bytes)", "",
                 "absent" if todo_bytes is None else base64.b64encode(todo_bytes).decode("ascii")]
        head += ["", "## Original settled snapshot (base64; exact bytes)", "",
                 "absent" if settled_before is None else base64.b64encode(settled_before).decode("ascii")]
        head += ["", "> The todo.md this retire replaced, kept whole below, as it was written.", "", ""]
        arch = instance / name
        todo = instance / TODO
        try:
            _write_atomic(arch, "\n".join(head) + body)
            if moved:
                _write_atomic(todo, _fresh_todo(kept, stamp, name))
        except OSError as exc:
            return False, (f"retirement outcome may be partial ({type(exc).__name__}); preserve {name} "
                           "and any temporary files for recovery and ask your seat. Do not retry blindly."), True
        if gone:
            left = [e for e in entries if e not in gone]
            try:
                ok, msg = st._commit(instance, left, nxt,
                                     {"op": "retire_thread", "words": words, "ids": [e["id"] for e in gone],
                                      "from": gone, "to": name, "why": reason, **({"by": by} if by else {})},
                                     now, "ok")
            except OSError as exc:
                ok, msg = False, f"settled commit raised {type(exc).__name__}"
            if not ok:
                # _commit can return failure after its own rollback failed. Never
                # erase the pre-change evidence or infer a no-op from its result.
                todo_status = "todo was not changed"
                if moved:
                    try:
                        _write_atomic(todo, todo_bytes)
                        todo_status = "todo was restored"
                    except OSError:
                        todo_status = "todo restoration failed"
                return False, (f"{msg}. Retirement outcome may be partial; {todo_status}. "
                               f"Recovery evidence remains in {name}; ask your seat before retrying."), True
    said = (f"Retired the thread ({topic}): {len(moved)} open todo item(s) and {len(gone)} settled "
            f"entr{'y' if len(gone) == 1 else 'ies'} moved to {name}, where recall still finds them. "
            f"Still open: {len(kept)} todo item(s); still settled: {len(entries) - len(gone)}.")
    return True, said, True


def _preview(instance: Path, words: List[str], reason: str = "") -> Tuple[bool, str, bool]:
    from sage.gateway import being_settled as st
    try:
        todo_bytes = _read_todo_bytes(instance)
    except OSError as exc:
        return False, f"cannot read todo.md ({type(exc).__name__}); nothing was changed.", False
    body, kept, moved, entries, nxt, gone, err = plan(instance, words, todo_snapshot=todo_bytes)
    if err:
        return False, f"cannot prepare retirement: {err}. Nothing was changed.", False
    topic = ", ".join(words)
    lines =[f"PREVIEW, no files or records were changed. Words: {topic}. "
             f"{len(moved)} of {len(moved) + len(kept)} open todo item(s) and {len(gone)} of "
             f"{len(entries)} settled entr{'y' if len(entries) == 1 else 'ies'} would be retired."]
    lines += [f"- settled [{e['id']}] {st._flat(e['question'])[:140]}" for e in gone]
    lines += [f"- todo: {t[:140]}" for t, _ in moved[:20]]
    if len(moved) > 20:
        lines.append(f"- … and {len(moved) - 20} more todo item(s)")
    lines += [f"- STAYS: {t[:140]}" for t, _ in kept[:10]]
    if _broad(kept, moved, entries, gone):
        if reason:
            binding = _preview_binding(instance, words, reason, todo_bytes, entries, nxt)
            lines.append(f"Broad retirement: confirmation: {_issue_confirmation(binding)}")
            lines.append("Confirm once in the same beat, within 5 minutes, using the same words, reason and source state. "
                         "A later beat or restart may lose this confirmation.")
        else:
            lines.append("Broad retirement: preview again with a reason to obtain a confirmation.")
    return True, "\n".join(lines), False
