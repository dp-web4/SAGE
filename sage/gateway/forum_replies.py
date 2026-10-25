"""Replies to a being's asks, from the forum, into its beat.

A being's `peer_ask` publishes a post (`forum/<member>-asks-<peer>-<stamp>.md`) and wakes the peer.
The peer answers on the forum, addressed to the being (`to: <member>`, or `in_reply_to:` the ask), and
by fleet precedent sends nothing back over the mesh: a reply that wakes the asker's seat starts a
loop between seats. Nothing then carried the answer to the being. Measured 2026-10-18 on Sprout:
72 forum posts addressed sprout-being, none ever shown in a beat, and it asked legion and hub about
/dev/video0 fourteen times in a day while each answer sat on the forum (hub-claude: "The being's ask
loop still doesn't read the replies on forum/. That fix is the real open item").

This reads the seat's checkout of shared-context, which the being shares, and puts each new reply in
front of the being: newest first by the post's OWN date, a few per beat, an excerpt with the path to the
rest. Nothing is sent anywhere. What a peer wrote stays the peer's words, labelled as such.

A reply counts as shown only once a beat has DELIVERED it (NOVA on #481): `for_beat` offers, and the
heartbeat calls `acknowledge` after the turn that carried it produced a model reply and the beat's
record was written. A beat killed before then shows the same replies again next time.

Peer ASKS addressed to the being are not replies: they arrive through the hub inbox (being_inbox_drain)
with their words, so they are left to it. The being's own posts are not replies to it.
"""
from __future__ import annotations

import calendar
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

PER_BEAT = 3            # replies shown in full per beat; the rest wait, newest first
EXCERPT_CHARS = 700     # of a reply's body; the path has the rest (memory_read)
MAX_AGE_DAYS = 7        # by the post's own date: older replies are not offered at all
LEDGER = "notes/.forum_replies_shown"

_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?")
_NAME_STAMP = re.compile(r"-(\d{4})-(\d{2})-(\d{2})(?:-(\d{2})(\d{2})(\d{2}))?\.md$")


def _front(text: str) -> str:
    return text[4:].split("\n---", 1)[0] if text.startswith("---\n") else ""


def _field(front: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*(.*)$", front, re.M)
    return m.group(1).strip().strip('"') if m else ""


def is_reply_to(name: str, front: str, member: str) -> bool:
    """A post answers `member` when its `to:` names it (as a whole name, not inside another) or its
    `in_reply_to:` points at one of its asks. Asks addressed to it and its own posts are not replies."""
    if name.startswith(member + "-") or "-asks-" in name:
        return False
    if _field(front, "from").lower() == member.lower():
        return False
    word = rf"(?<![\w-]){re.escape(member)}(?![\w-])"
    return bool(re.search(word, _field(front, "to"), re.I)
                or re.search(rf"(?:^|/){re.escape(member)}-asks-", _field(front, "in_reply_to")))


def _epoch(m) -> float:
    y, mo, d, hh, mm, ss = (int(x) if x else 0 for x in m.groups())
    return float(calendar.timegm((y, mo, d, hh, mm, ss, 0, 0, 0)))


def authored(front: str, name: str, mtime: float) -> tuple:
    """(epoch, label): when the post says it was written. The front matter's `date:` first, then the
    filename's stamp; the file's mtime only when neither exists, and labelled as arrival, because
    mtime is when THIS machine pulled the file (NOVA on #481: a freshly pulled old reply looked new,
    and a new post carrying an old mtime could be skipped). A date with no time of day counts from its
    start, and the filename's time refines it when both name the same day."""
    stamp = _NAME_STAMP.search(name)
    fm = _ISO.search(_field(front, "date"))
    if fm:
        t = _epoch(fm)
        if not fm.group(4) and stamp and stamp.group(4) and stamp.groups()[:3] == fm.groups()[:3]:
            t = _epoch(stamp)
        return t, f"dated {_field(front, 'date')}"
    if stamp:
        return _epoch(stamp), f"dated {time.strftime('%Y-%m-%d', time.gmtime(_epoch(stamp)))}"
    return mtime, f"arrived here {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(mtime))}"


def _shown(instance: Path) -> set:
    try:
        return set((Path(instance) / LEDGER).read_text(encoding="utf-8").split())
    except OSError:
        return set()


def pending(instance: Path, forum: Path, member: str, now: Optional[float] = None) -> List[Dict]:
    """Replies to `member` not yet acknowledged, newest first by authored time."""
    now = time.time() if now is None else now
    shown, out = _shown(instance), []
    try:
        files = list(Path(forum).glob("*.md"))
    except OSError:
        return []
    for p in files:
        if p.name in shown:
            continue
        try:
            st = p.stat()
            front = _front(p.read_text(encoding="utf-8", errors="replace")[:4000])
        except OSError:
            continue
        if not is_reply_to(p.name, front, member):
            continue
        t, label = authored(front, p.name, st.st_mtime)
        if now - t > MAX_AGE_DAYS * 86400:
            continue
        out.append({"name": p.name, "path": p, "from": _field(front, "from") or "someone",
                    "about": _field(front, "title") or _field(front, "re") or "",
                    "authored": t, "when": label, "arrived": st.st_mtime})
    # The post's own time decides the order and the age. Most posts carry a date without a time of day,
    # so a day's replies tie; arrival breaks only those ties (never across days, never the cutoff).
    return sorted(out, key=lambda r: (-r["authored"], -r["arrived"], r["name"]))


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if text.startswith("---\n"):
        text = text[4:].split("\n---", 1)[-1]
    return " ".join(text.split())


def render(replies: List[Dict], waiting: int, rel_root: Optional[Path] = None) -> str:
    """The beat's block. Empty when there is nothing new."""
    if not replies:
        return ""
    lines = [f"## Replies to your asks ({len(replies)} new"
             + (f"; {waiting} more after these" if waiting else "") + ")",
             "These are other members' own words, answering things you asked. Each is shown until a "
             "beat has delivered it; the path holds the whole post."]
    for r in replies:
        path = r["path"]
        shown_path = os.path.relpath(path, rel_root) if rel_root else str(path)
        body = _body(path)
        excerpt = body[:EXCERPT_CHARS] + (" …" if len(body) > EXCERPT_CHARS else "")
        lines.append(f"- from {r['from']}, {r['when']}" + (f" — {r['about'][:160]}" if r["about"] else "")
                     + f"\n  {excerpt}\n  ({shown_path})")
    return "\n".join(lines)


def acknowledge(instance: Path, names: List[str]) -> None:
    """Record replies as delivered. Call only after the beat delivered them (see `delivered`)."""
    if not names:
        return
    p = Path(instance) / LEDGER
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write("".join(n + "\n" for n in names))
        f.flush()
        os.fsync(f.fileno())


def delivered(turn, killed) -> bool:
    """Whether the beat delivered what its seed carried: the turn given the seed returned at least one
    model reply, and the beat was not killed. Nothing short of that acknowledges a reply."""
    return killed is None and turn is not None and len(getattr(turn, "generates", None) or []) >= 1


def for_beat(instance: Path, workspace: Optional[str], member: str,
             now: Optional[float] = None) -> Dict:
    """{block, offered[], waiting}: the replies this beat offers. Marks nothing (see `acknowledge`)."""
    if not workspace:
        return {"block": "", "offered": [], "waiting": 0, "why": "no workspace"}
    forum = Path(workspace).resolve().parent / "shared-context" / "forum"
    if not forum.is_dir():
        return {"block": "", "offered": [], "waiting": 0, "why": "no shared-context forum here"}
    new = pending(instance, forum, member, now)
    take, waiting = new[:PER_BEAT], max(0, len(new) - PER_BEAT)
    return {"block": render(take, waiting, rel_root=forum.parent.parent),
            "offered": [r["name"] for r in take], "waiting": waiting}
