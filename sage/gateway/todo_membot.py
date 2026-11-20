"""The todo membot: the being's own bookkeeping does what the being means. It has no judgment of its own.

dp, 2026-10-19: "we need a way for it to do that. should we have a mini-membot for the todo?"

MEASURED ON SPROUT, 2026-10-19. The being accepted that a goal was finished and tried to close it: "cross-check
camera grant off (scope-ef204d003703 expired undecided on Oct 17, closed without approval)". Nothing closed:
- memory_write appends, and the parser counts an item done only on [x], [done] or a `done:` section;
- a done line closed ONE matching item;
- 19 of the 79 open items it was shown every beat were differently worded copies of that one goal.

Within the hour the goal was back ("pending ~36 hours"), and the open copies grew from 17 to 19. The intent was
the being's; the mechanics failed it (dev research GOAL_ATTRACTORS.md).

What this does, and only this:
- **close by the being's act.** A done line whose text is `all: <words or id>` closes EVERY open item containing
  those words. The membot never closes anything by itself.
- **show the open list grouped.** Open items naming the same id (a scope request, a file, a device) are shown as
  one line with a count, so the being sees one goal once, not 19 times. The file is not changed.
- **say what it closed.** The view reports each recent `all:` closure and how many items it closed, so the
  being can check the effect of its act.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

ALL = re.compile(r"^(?:all|every)\s*:\s*(.+)$", re.I)
MIN_PHRASE = 4          # shorter phrases would close too much by accident ("ok", "dp")

# What makes two items "the same goal" for display: a scope request or a device they name. Script and file
# names are deliberately NOT ids here: they chain unrelated tasks together (measured on Sprout's 80 open items,
# file names merged 36 items, sandbox and shell-script tasks included, into one "camera" line).
_ID = re.compile(r"scope-[0-9a-f]{12}|/dev/[A-Za-z]+\d*", re.I)


def norm(s: str) -> str:
    s = re.sub(r"[`*_]", "", (s or "").lower())
    return re.sub(r"\s+", " ", s).strip(" .:;-")


def close_all(items: Dict[str, Tuple[str, object]], body: str) -> Optional[Tuple[str, List[str]]]:
    """If `body` is an `all: <phrase>` directive, delete every open item containing the phrase and return
    (phrase, [closed item texts]). Return None when it is not a directive (the caller then treats the line as an
    ordinary done item)."""
    m = ALL.match((body or "").strip())
    if not m:
        return None
    # A NOTE AFTER THE WORDS IS NOT PART OF THEM. The being's first use (Sprout 2026-10-19 08:51Z) was
    # `- [x] all: ef204d003703 (channel_egress not built; rate-governor calibration is design work, not a gate)`:
    # the id, then its reason in parentheses. Matched as one phrase it closed nothing, while 19 open items
    # contained the id. What it names is what comes before a bracketed or dashed note.
    phrase = norm(re.split(r"\s+[(\[]|\s+[—–]\s+|\s+-\s+", m.group(1), maxsplit=1)[0])
    # SEVERAL PHRASES, COMMA-SEPARATED. The first `all:` mcnugget-being wrote once it could see its list
    # (2026-11-08 21:58Z) was `all: camera advice, peer_ask`: two phrases. Read as one string it matched nothing.
    # Each part must stand on its own (MIN_PHRASE), so a short fragment cannot widen the close.
    parts = [p for p in (norm(x) for x in phrase.split(",")) if len(p) >= MIN_PHRASE]
    if not parts:
        return (phrase, [])
    closed = [items.pop(k)[0] for k in [k for k in items if any(p in k for p in parts)]]
    return (phrase, closed)


_SCOPE = re.compile(r"scope-[0-9a-f]{12}", re.I)
_DEVICE = re.compile(r"/dev/[A-Za-z]+\d*", re.I)


#: The response field a daemon would set to say `requests[]` is EVERY request it holds for the member,
#: unfiltered and untruncated. Only then may an id it lacks be called "not on record for you". No daemon
#: serves it as of hestia f0660a7 (2026-11-19): tool_scope_status returns the requests it holds in memory, but
#: whether that is all of them (pruning, restarts, an older daemon) is not a stated contract. Until one says
#: so, an absent id is reported as absent from this response, which is all that was observed.
SCOPE_COMPLETE_FIELD = "requests_complete"


class ScopeUnread(Exception):
    """A hestia_scope_status read that returned no usable request list (error envelope, wrong shape)."""


@dataclass(frozen=True)
class ScopeSnapshot:
    """One hestia_scope_status read, as observed at `observed_at`.

    Three states, never conflated (Nova on #730: a failed call must not become `{}`):
    - `error` set: the read failed. Nothing is known about any id; `rows` is None.
    - `error` None, `complete` False: these rows were in the response; an absent id is only absent from it.
    - `error` None, `complete` True: the daemon declared the list complete; an absent id is not on record."""
    rows: Optional[Dict[str, dict]]
    observed_at: datetime
    complete: bool = False
    error: Optional[str] = None


def scope_snapshot(st, observed_at: Optional[datetime] = None) -> ScopeSnapshot:
    """Wrap one hestia_scope_status response (or the exception its call raised) as a ScopeSnapshot."""
    at = observed_at or datetime.now(timezone.utc)
    if isinstance(st, BaseException):
        return ScopeSnapshot(None, at, error=type(st).__name__)
    if not isinstance(st, dict):
        return ScopeSnapshot(None, at, error="no response")
    err = st.get("_hestia_error")
    if err is not None:
        code = (err.get("code") or "hestia.error") if isinstance(err, dict) else str(err)
        return ScopeSnapshot(None, at, error=str(code))
    reqs = st.get("requests")
    if not isinstance(reqs, list):
        return ScopeSnapshot(None, at, error="no request list")
    rows = {str(r.get("request_id")).lower(): r for r in reqs if isinstance(r, dict) and r.get("request_id")}
    complete = st.get(SCOPE_COMPLETE_FIELD) is True and not st.get("truncated")
    return ScopeSnapshot(rows, at, complete=complete)


def _utc(x) -> str:
    """An epoch-seconds stamp from hestia as `YYYY-MM-DD HH:MM UTC`, or "" when it is not one."""
    try:
        return f"{datetime.fromtimestamp(float(x), timezone.utc):%Y-%m-%d %H:%M} UTC"
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def scope_status_note(text: str, snap: Optional[ScopeSnapshot]) -> str:
    """What one hestia_scope_status read held for each scope request an open item names, or "" when the item
    names none or the beat made no read (`snap` None).

    WHY (cbp-being, 2026-11-15; scope-8b0be4d34333 and scope-6ec4bf5583c4). Both asks were refused at 20:06 UTC.
    The being's todo kept several lines, copied from earlier beats' pending block, that called them pending with
    hours left. Over the next hour and a half it treated them as pending: it asked dp about them and searched
    its inbox for them, and its carried account still called them pending. The refusal was in the same beat's
    scope block, never next to the item that contradicted it. The item is the being's and stays verbatim; the
    measurement sits beside it (the same move as want_check). Nothing here closes, edits or rewrites an item.

    WORDING IS AN OBSERVATION AT A TIME, NOT A STANDING FACT (Nova on #730). The note names when the read was
    made, and a ruling's own time when hestia gives one, so a request read as pending that is ruled a minute
    later reads as "pending at that read", not as pending forever. It states status and ruler and nothing
    about what to do next: no advice, and nothing that says a refused or expired request can be renewed.

    AN ABSENT ID IS NOT CALLED "NOT ON RECORD" UNLESS THE LIST IS DECLARED COMPLETE (SCOPE_COMPLETE_FIELD).
    A failed read says it failed, and claims nothing about any id."""
    if snap is None:
        return ""
    ids = []
    for m in _SCOPE.finditer(text or ""):
        rid = m.group(0).lower()
        if rid not in ids:
            ids.append(rid)
    if not ids:
        return ""
    at = f"{snap.observed_at:%Y-%m-%d %H:%M} UTC"
    if snap.error is not None:
        return (f"hestia scope status could not be read at {at} ({snap.error}); "
                f"status of {', '.join(ids)} unknown")
    facts = []
    for rid in ids:
        row = (snap.rows or {}).get(rid)
        if not row:
            facts.append(f"{rid}: not on record for you" if snap.complete
                         else f"{rid}: not in this scope-status response")
            continue
        status = row.get("status") or row.get("decision")
        if not status:
            facts.append(f"{rid}: listed, with no status stated")
            continue
        fact = f"{rid}: {status}"
        if status != "pending":
            if row.get("decided_by"):
                fact += f" by {row['decided_by']}"
            when = _utc(row.get("decided_at"))
            if when:
                fact += f" at {when}"
        facts.append(fact)
    return f"hestia scope status as read at {at}: " + "; ".join(facts)


def group_key(text: str) -> Optional[str]:
    """The one id an item is grouped under, or None (shown alone).

    SCOPE IDENTITY IS DOMINANT (NOVA on #486). Two scope requests for the same device are different
    authorizations, and one may be open while the other was refused, so they must never fold together because the
    device matches. So:
    - an item naming exactly one scope request groups under that request, whatever devices it also names;
    - an item naming two or more scope requests stands alone (it must not bridge them);
    - only an item naming NO scope request groups by its device, and only with other such items."""
    scopes = {m.group(0).lower() for m in _SCOPE.finditer(text or "")}
    if len(scopes) == 1:
        return next(iter(scopes))
    if scopes:
        return None
    devices = {m.group(0).lower() for m in _DEVICE.finditer(text or "")}
    return f"device:{next(iter(devices))}" if len(devices) == 1 else None


def group(open_items: List[Tuple[str, object]]) -> List[Tuple[str, object, int, Optional[str]]]:
    """[(shown text, since, count, id)], in the given order (newest first). Items with the same group_key fold into
    the newest of them; nothing is joined transitively."""
    out: List[list] = []
    where: Dict[str, int] = {}
    for text, since in open_items:
        k = group_key(text)
        if k is not None and k in where:
            out[where[k]][2] += 1
            continue
        if k is not None:
            where[k] = len(out)
        out.append([text, since, 1, k.split(":", 1)[1] if k and k.startswith("device:") else k])
    return [tuple(x) for x in out]


def closures_line(closures: List[Tuple[str, int, object]], limit: int = 3) -> List[str]:
    """Lines reporting the being's recent `all:` closures, newest last: what it asked to close and how many
    items that closed. Zero is reported too: an `all:` that matched nothing is worth knowing."""
    out = []
    for phrase, n, when in closures[-limit:]:
        at = f" ({when:%Y-%m-%d %H:%M} UTC)" if hasattr(when, "strftime") else ""
        out.append(f"- your `all: {phrase}`{at} closed {n} open item(s)"
                   + ("" if n else "; nothing open contained those words"))
    return out
