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

Nothing in SAGE moves that checkout, so a reply pushed after the last time some session pulled sat
unseen (#792, cbp 2026-11-19: 13 commits behind, two replies to cbp-being missing). So each beat also
fetches (remote-tracking refs only, at most every few minutes) and reads the forum posts on
`origin/main` that the working tree does not have yet, straight from git. The working tree, index and
branch are never touched: siblings share that checkout and may have work in it.

Peer ASKS addressed to the being are not replies: they arrive through the hub inbox (being_inbox_drain)
with their words, so they are left to it. The being's own posts are not replies to it.
"""
from __future__ import annotations

import calendar
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

PER_BEAT = 3            # replies shown in full per beat; the rest wait, newest first
EXCERPT_CHARS = 700     # of a reply's body; the path has the rest (memory_read)
MAX_AGE_DAYS = 7        # by the post's own date: older replies are not offered at all
LEDGER = "notes/.forum_replies_shown"
UPSTREAM = "origin/main"  # where replies land; read from git, never merged into the shared tree
FETCH_EVERY_S = 300       # a beat fetches only when the last fetch (anyone's) is older than this
GIT_TIMEOUT_S = 20        # a hung fetch costs the beat this much at most, then the beat goes on

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


def _git(repo: Path, *args: str, timeout: float = GIT_TIMEOUT_S, data: Optional[bytes] = None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=10")
    return subprocess.run(["git", "-C", str(repo), *args], input=data, capture_output=True,
                          timeout=timeout, env=env)


def _fetch_due(repo: Path, now: float) -> bool:
    try:
        r = _git(repo, "rev-parse", "--git-path", "FETCH_HEAD")
        head = Path(r.stdout.decode().strip())
        if not head.is_absolute():
            head = Path(repo) / head
        return now - head.stat().st_mtime >= FETCH_EVERY_S
    except (OSError, subprocess.SubprocessError, ValueError):
        return True


def upstream_posts(repo: Path, fetch: bool = True, now: Optional[float] = None) -> Dict:
    """{posts: {name: text}, fetched, why}: forum posts on `UPSTREAM` that the working tree lacks.

    `git fetch` moves only remote-tracking refs; the posts are read with `cat-file`, so nothing in
    the checkout changes. Any failure (no remote, offline, a sibling holding the ref lock) is said in
    `why` and the beat goes on with what is on disk and whatever `UPSTREAM` already holds."""
    now = time.time() if now is None else now
    repo, out = Path(repo), {"posts": {}, "fetched": False, "why": ""}
    try:
        if fetch and _fetch_due(repo, now):
            r = _git(repo, "fetch", "-q", "origin")
            out["fetched"] = r.returncode == 0
            if r.returncode:
                out["why"] = "fetch failed: " + r.stderr.decode(errors="replace").strip()[:200]
        r = _git(repo, "ls-tree", "-z", "--name-only", UPSTREAM, "forum/")
        if r.returncode:
            out["why"] = (out["why"] + "; " if out["why"] else "") + f"no {UPSTREAM}"
            return out
        missing = [n for n in r.stdout.decode(errors="replace").split("\0")
                   if n.endswith(".md") and not (repo / n).exists()]
        if not missing:
            return out
        r = _git(repo, "cat-file", "--batch",
                 data="".join(f"{UPSTREAM}:{n}\n" for n in missing).encode())
        buf, i = r.stdout, 0
        for n in missing:
            nl = buf.index(b"\n", i)
            head = buf[i:nl].split()
            i = nl + 1
            if len(head) < 3 or head[1] != b"blob":
                continue
            size = int(head[2])
            out["posts"][n.split("/", 1)[1]] = buf[i:i + size].decode("utf-8", errors="replace")
            i += size + 1
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        out["why"] = (out["why"] + "; " if out["why"] else "") + f"{type(e).__name__}: {e}"[:200]
    return out


def pending(instance: Path, forum: Path, member: str, now: Optional[float] = None,
            upstream: Optional[Dict[str, str]] = None) -> List[Dict]:
    """Replies to `member` not yet acknowledged, newest first by authored time. `upstream` holds posts
    (name -> text) on `UPSTREAM` that the checkout lacks; a name on disk wins over its upstream copy."""
    now = time.time() if now is None else now
    shown, out = _shown(instance), []
    try:
        files = list(Path(forum).glob("*.md"))
    except OSError:
        return []
    found = []
    for p in files:
        if p.name in shown:
            continue
        try:
            found.append((p.name, p.read_text(encoding="utf-8", errors="replace"), p.stat().st_mtime, p, None))
        except OSError:
            continue
    on_disk = {p.name for p in files}
    for name, text in (upstream or {}).items():
        if name not in shown and name not in on_disk:
            # Not in this checkout yet: it "arrived" now, and the being reads it from the excerpt
            # (the whole post is at this git path until the checkout is pulled).
            found.append((name, text, now, None, f"{UPSTREAM}:forum/{name}"))
    for name, text, mtime, path, where in found:
        front = _front(text[:4000])
        if not is_reply_to(name, front, member):
            continue
        t, label = authored(front, name, mtime)
        if now - t > MAX_AGE_DAYS * 86400:
            continue
        out.append({"name": name, "path": path, "where": where, "text": text,
                    "from": _field(front, "from") or "someone",
                    "about": _field(front, "title") or _field(front, "re") or "",
                    "authored": t, "when": label, "arrived": mtime})
    # The post's own time decides the order and the age. Most posts carry a date without a time of day,
    # so a day's replies tie; arrival breaks only those ties (never across days, never the cutoff).
    return sorted(out, key=lambda r: (-r["authored"], -r["arrived"], r["name"]))


def _body(text: str) -> str:
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
        path = r.get("path")
        if path is None:
            shown_path = r["where"] + " — not in this checkout yet"
        else:
            shown_path = os.path.relpath(path, rel_root) if rel_root else str(path)
        body = _body(r["text"] if "text" in r else Path(path).read_text(encoding="utf-8", errors="replace"))
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
             now: Optional[float] = None, fetch: Optional[bool] = None) -> Dict:
    """{block, offered[], waiting, upstream}: the replies this beat offers. Marks nothing (see
    `acknowledge`). `fetch` defaults to on; SAGE_FORUM_FETCH=0 turns the fetch off (the posts
    `UPSTREAM` already holds are still read)."""
    if not workspace:
        return {"block": "", "offered": [], "waiting": 0, "why": "no workspace"}
    forum = Path(workspace).resolve().parent / "shared-context" / "forum"
    if not forum.is_dir():
        return {"block": "", "offered": [], "waiting": 0, "why": "no shared-context forum here"}
    if fetch is None:
        fetch = os.environ.get("SAGE_FORUM_FETCH", "1") != "0"
    up = upstream_posts(forum.parent, fetch=fetch, now=now) if (forum.parent / ".git").exists() \
        else {"posts": {}, "fetched": False, "why": "not a git checkout"}
    new = pending(instance, forum, member, now, upstream=up["posts"])
    take, waiting = new[:PER_BEAT], max(0, len(new) - PER_BEAT)
    return {"block": render(take, waiting, rel_root=forum.parent.parent),
            "offered": [r["name"] for r in take], "waiting": waiting,
            "upstream": {"fetched": up["fetched"], "unpulled": len(up["posts"]),
                         "offered": [r["name"] for r in take if r.get("path") is None],
                         **({"why": up["why"]} if up["why"] else {})}}
