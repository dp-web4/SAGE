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
home root (todo.retired-<date>-thread.md). recall still searches that file (home_recall indexes
todo.retired-*), so nothing is lost and a deliberate search finds it; it just stops arriving uninvited.
Done items, other open items and other settled entries are untouched. The retired file keeps the old
todo.md whole below a header that lists exactly what was taken out, and settled_log.jsonl records each
entry removed, so the change is auditable and reversible by hand.

A word matches at the start of a word ("install" matches "installer", "scope" matches "scopes", "api"
does not match "rapid"), case-insensitively. `preview='true'` reports what would move and writes
nothing, so a being (or its seat) can check a word list before using it.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

TODO = "todo.md"
TODO_TMP = ".todo.md.tmp"
MIN_WORD = 3          # shorter words match too much to be a topic ("ap", "in")
MAX_WORDS = 100       # cbp-being's hestia thread (11-01) took 68 to cover without catching its own work
REASON_MAX = 600


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


def archive_name(instance: Path, now: Optional[float] = None) -> str:
    """The retired file this call writes: never one that already exists (a second retire the same day
    gets -2, -3, as retire_note's copies do)."""
    day = _stamp(now).strftime("%Y-%m-%d")
    name, n = f"todo.retired-{day}-thread.md", 2
    while (Path(instance) / name).exists():
        name, n = f"todo.retired-{day}-thread-{n}.md", n + 1
    return name


def writes(instance: Path, now: Optional[float] = None) -> Tuple[str, ...]:
    """Every file a (non-preview) retire_thread touches in the home, for the gate."""
    from sage.gateway.being_settled import SETTLED_WRITES
    return (TODO, TODO_TMP, archive_name(instance, now)) + tuple(SETTLED_WRITES)


def _write_atomic(p: Path, text: str) -> None:
    tmp = p.with_name(f".{p.name}.tmp")
    with open(tmp, "w") as f:
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
    p = instance / TODO
    body = p.read_text(errors="replace") if p.exists() else ""
    items = list(_todo_items(body).values()) if body else []
    moved = [x for x in items if hit(x[0])]
    kept = [x for x in items if not hit(x[0])]
    entries, nxt, err = st.read(instance)
    gone = [e for e in entries if hit(f"{e.get('question', '')} {e.get('answer', '')} {e.get('evidence', '')}")]
    return body, kept, moved, entries, nxt, gone, err


def retire_thread(instance, args: Dict, now: Optional[float] = None, by: str = "") -> Tuple[bool, str, bool]:
    """Returns (ok, message, changed)."""
    from sage.gateway import being_settled as st
    a = args or {}
    words = words_of(a.get("words"))
    reason = re.sub(r"\s+", " ", str(a.get("reason") or "")).strip()[:REASON_MAX]
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
    if not preview and not reason:
        return False, ("retire_thread needs a 'reason': why this line of work is finished. It is written "
                       "at the top of the retired file. (preview='true' shows what would move without one.)"), False
    instance = Path(instance)
    with st._home_lock(instance):
        body, kept, moved, entries, nxt, gone, err = plan(instance, words)
        if err:
            return False, f"cannot read your settled list: {err}. Nothing was changed.", False
        topic = ", ".join(words)
        if preview:
            lines = [f"PREVIEW, nothing was changed. Words: {topic}. "
                     f"{len(moved)} of {len(moved) + len(kept)} open todo item(s) and {len(gone)} of "
                     f"{len(entries)} settled entr{'y' if len(entries) == 1 else 'ies'} would be retired."]
            lines += [f"- settled [{e['id']}] {st._flat(e['question'])[:140]}" for e in gone]
            lines += [f"- todo: {t[:140]}" for t, _ in moved[:20]]
            if len(moved) > 20:
                lines.append(f"- … and {len(moved) - 20} more todo item(s)")
            lines += [f"- STAYS: {t[:140]}" for t, _ in kept[:10]]
            return True, "\n".join(lines), False
        if not moved and not gone:
            return True, (f"Nothing names {topic}: no open todo item and no settled entry. Nothing was "
                          f"changed."), False
        stamp = _stamp(now)
        name = archive_name(instance, now)
        head = [f"> RETIRED {stamp:%Y-%m-%d %H:%M}Z with retire_thread"
                + (f" (by {by})" if by else "") + f". Topic words: {topic}.",
                f"> No longer current: {reason}", "",
                f"## Settled entries retired ({len(gone)})", ""]
        head += [f"- [{e['id']}] {st._flat(e['question'])} -> {st._flat(e.get('answer', ''))}"
                 + (f" (evidence: {st._flat(e['evidence'])})" if e.get("evidence") else "")
                 + f" (settled {str(e.get('at', ''))[:10]})" for e in gone]
        head += ["", f"## Open todo items retired ({len(moved)})", ""]
        head += [(f"- [ ] {t}" + (f" (since {s:%Y-%m-%d %H:%M} UTC)" if s else "")) for t, s in moved]
        head += ["", "> The todo.md this retire replaced, kept whole below, as it was written.", "", ""]
        arch = instance / name
        _write_atomic(arch, "\n".join(head) + body)
        todo = instance / TODO
        if moved:
            _write_atomic(todo, _fresh_todo(kept, stamp, name))
        if gone:
            left = [e for e in entries if e not in gone]
            ok, msg = st._commit(instance, left, nxt,
                                 {"op": "retire_thread", "words": words, "ids": [e["id"] for e in gone],
                                  "from": gone, "to": name, "why": reason, **({"by": by} if by else {})},
                                 now, "ok")
            if not ok:   # undo: the todo back as it was, and no retired file claiming a retire
                if moved:
                    _write_atomic(todo, body)
                arch.unlink(missing_ok=True)
                return False, f"{msg}. The todo was put back as it was; nothing was retired.", False
    said = (f"Retired the thread ({topic}): {len(moved)} open todo item(s) and {len(gone)} settled "
            f"entr{'y' if len(gone) == 1 else 'ies'} moved to {name}, where recall still finds them. "
            f"Still open: {len(kept)} todo item(s); still settled: {len(entries) - len(gone)}.")
    return True, said, True
