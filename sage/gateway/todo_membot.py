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
    if len(phrase) < MIN_PHRASE:
        return (phrase, [])
    closed = [items.pop(k)[0] for k in [k for k in items if phrase in k]]
    return (phrase, closed)


_SCOPE = re.compile(r"scope-[0-9a-f]{12}", re.I)
_DEVICE = re.compile(r"/dev/[A-Za-z]+\d*", re.I)


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
