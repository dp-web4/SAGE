"""
being_inbox_drain — the inbound half of being-to-being (PRD_ONE_BEING_ONE_EXPERIENCE S4).

A being holds its own hub identity (admitted member, own channel key). Notices addressed
to that identity land in a hub mailbox that nothing drained: hub-watch drains only the
seat's. This drain is the courier:

  1. READ the being's hub mailbox with the being's own key (the hub's `notifications`
     read is consume-once, so every notice is persisted BEFORE anything else happens);
  2. PERSIST each notice into the being's home, `notes/inbox/<ts>-<kind>-<id>.md`, with
     its full provenance (from, kind, pointer, hub id) and a label saying the seat's
     drain relayed it — seat content in the being's frame, labelled as the seat's;
  3. NOTIFY the being's hestia inbox from the SEAT's session (hestia_member_notify to the
     being, pointer = the relayed file), so the being's next beat sees it in its inbox
     peek and can memory_read it inside its home.

Idempotent by hub notice id (`notes/inbox/.seen`). Fail-open for the being, loud in the
returned summary. The seat never speaks as the being here: the hub read uses the being's
key (courier work, the same class as the egress drain), the hestia notify is the seat's.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

# hub kinds (fractal roots) -> hestia MEMBER_NOTICE_KINDS
_KIND_MAP = {"review": "review_request", "review.request": "review_request", "review.done": "review_done",
             "forum": "forum-note", "forum.note": "forum-note", "forum-note": "forum-note",
             "reply": "reply", "handoff": "handoff", "ack": "ack", "coordination": "coordination"}
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


_IDENTITY_VARS = ("CHANNEL_CLIENT", "HUB_URL", "MY_LCT", "MY_KEYPAIR", "HUB_MESH_STATE")
_SOURCE_AND_PRINT = 'set -a; source "$1" >/dev/null 2>&1 || exit 3; shift; for v in "$@"; do printf "%s\\0" "${!v:-}"; done'


def _env_from_file(path: str) -> Dict[str, str]:
    """The identity values EXACTLY as hub-notify sees them: the file is shell-sourced in a clean subshell and
    only the named variables come back, NUL-separated (never printed or logged).

    Until 2026-10-03 this was a small Python KEY=value parser, while hub-notify (the send path) `source`s the
    same file, so the two could disagree: a quoted value keeps a trailing `# comment`, an `export X=` line is
    keyed "export X". On Sprout the being's sends were accepted while every read of its mailbox failed
    ("channel_client exited 1: Error: invalid length: found 94"), 1,778 drains recorded as empty. One
    reading, the sender's. `$HOME`, `${X}` and `~` expand as they do for hub-notify."""
    path = os.path.expanduser(path)
    if not Path(path).is_file():
        raise FileNotFoundError(f"no identity file at {path}")
    clean = {"HOME": os.path.expanduser("~"), "PATH": "/usr/local/bin:/usr/bin:/bin"}
    p = subprocess.run(["bash", "-c", _SOURCE_AND_PRINT, "_", path, *_IDENTITY_VARS],
                       capture_output=True, timeout=10, env=clean)
    if p.returncode != 0:
        raise RuntimeError(f"the identity file could not be sourced (bash exited {p.returncode})")
    vals = p.stdout.decode("utf-8", "replace").split("\0")[:len(_IDENTITY_VARS)]
    return {k: v for k, v in zip(_IDENTITY_VARS, vals) if v}


def fetch_notifications(env_file: str, timeout: int = 60) -> List[Dict]:
    """Read (and thereby consume) the mailbox of the identity in `env_file`."""
    env = _env_from_file(env_file)
    missing = [k for k in ("CHANNEL_CLIENT", "HUB_URL", "MY_LCT", "MY_KEYPAIR") if not env.get(k)]
    if missing:
        raise RuntimeError(f"the identity file sets no {', '.join(missing)}")
    cmd = [env["CHANNEL_CLIENT"], env["HUB_URL"], env["MY_LCT"], os.path.expanduser(env["MY_KEYPAIR"]),
           "notifications", "{}"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    # "CANNOT TELL" IS NOT "EMPTY" (Sprout, 2026-10-03). A failed call or an unreadable reply returned [] and the
    # beat recorded {fetched: 0, errors: []} -- 1,778 drains of sprout-being's mailbox, never one fetch, while
    # the hub's ledger shows sends addressed to it. Any of these now raises, so drain() records it in `errors`.
    def _why(text: str) -> str:
        return " ".join((text or "").split())[-200:]
    if p.returncode != 0:
        raise RuntimeError(f"channel_client exited {p.returncode}: {_why(p.stderr) or _why(p.stdout) or 'no output'}")
    try:
        d = json.loads(p.stdout or "")
    except Exception:
        raise RuntimeError(f"unreadable reply: {_why(p.stdout) or 'empty'}")
    if not isinstance(d, dict) or "notifications" not in d:
        raise RuntimeError(f"reply has no notifications field: {_why(json.dumps(d))}")
    return list(d.get("notifications") or [])


def map_kind(kind: str) -> str:
    k = (kind or "").strip()
    if k in _KIND_MAP:
        return _KIND_MAP[k]
    root = k.split(".", 1)[0]
    return _KIND_MAP.get(root, "coordination")


# WHAT IT SAYS TRAVELS WITH THE ENVELOPE (dp, 2026-10-11: option (b) of the inline question on
# forum/sprout-to-hub-hub-being-never-reads-record-pr-and-inline-question-2026-10-11.md). Measured on HUB:
# hub-being peeked 17 notices every beat and made 0 memory_read calls in 328 tool calls since 10-09, so
# an envelope that only POINTS at the ask is an ask never read. The courier already writes into the
# being's home; it now copies what the pointer says, as delivered mail. Only from the fleet's shared
# checkout (shared-context, which every member reads), never private-context, never a URL, never a
# path that escapes it, and capped -- the rest stays a memory_read away.
DELIVERED_CHARS = 3000
DELIVERED_HEADING = "## What it says (delivered with the notice)"
_DELIVERABLE_SUFFIXES = (".md", ".txt", ".json", ".jsonl")


def delivered_content(pointer: str, workspace: Optional[str]) -> Dict:
    """{'text', 'chars', 'truncated'} for a pointer the courier may copy, or {'why'} when it may not."""
    target = str(pointer or "").split("#", 1)[0].strip()
    if not workspace:
        return {"why": "no workspace to resolve it against"}
    if not target or "://" in target:
        return {"why": "not a file in the shared checkout"}
    shared = (Path(workspace).resolve().parent / "shared-context").resolve()
    if not target.startswith("shared-context/"):
        return {"why": "not in shared-context"}
    p = (shared.parent / target).resolve()
    if shared not in p.parents or p.suffix.lower() not in _DELIVERABLE_SUFFIXES:
        return {"why": "not a document in shared-context"}
    if not p.is_file():
        return {"why": "not in this machine's copy of shared-context yet"}
    text = p.read_text(encoding="utf-8", errors="replace")
    return {"text": text[:DELIVERED_CHARS], "chars": len(text), "truncated": len(text) > DELIVERED_CHARS}


def _senders_path(instance: Path) -> Path:
    """Where the drain records who each envelope came from: SEAT-OWNED, outside the being's home.

    THE ENVELOPE'S `from` IS TRANSPORT METADATA, AND IT STAYS THAT (NOVA on #459). It arrives in the hub's
    `notifications` reply over the channel this seat opens with the being's own key, as the member id the
    hub delivered the notice from. The note this module writes into notes/inbox/ carries the same value in
    its front matter, but that file sits in the being's writable home, where memory_write can change it. A
    sender read back from there is an author-editable field. So the value is also recorded HERE, keyed by
    the note's file name, in a file the being's verbs cannot reach (the reason the web_search rate ledger
    lives outside the home: a record the limited actor can write is not a record of anything)."""
    base = os.environ.get("SAGE_INBOX_SENDERS_DIR") or os.path.expanduser("~/.local/state/sage/inbox-senders")
    return Path(base) / f"{Path(instance).resolve().name}.jsonl"


def record_sender(instance: Path, note_name: str, hub_notice_id: str, sender: str) -> None:
    """Append one (note, notice id, authenticated sender) row. Raises on failure: the caller decides."""
    p = _senders_path(instance)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"note": note_name, "hub_notice_id": hub_notice_id, "from": sender}) + "\n")
        f.flush()
        os.fsync(f.fileno())


def delivered_notices(instance: Path) -> list:
    """Every (note, hub_notice_id, from) row this drain recorded, oldest first; [] when there is no
    record. SEAT-OWNED and outside the being's home (see _senders_path), so it is evidence of what the
    hub delivered and from whom -- unlike the envelope note, which the being can write."""
    out = []
    try:
        for line in _senders_path(instance).read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("note") and r.get("hub_notice_id") and r.get("from"):
                out.append(r)
    except OSError:
        pass
    return out


def authenticated_sender(instance: Path, note_name: str) -> str:
    """The member id the hub delivered this note's envelope from, as the drain recorded it at delivery; ""
    when there is no record (an envelope persisted before the record existed, or none at all). Never read
    from the note itself."""
    try:
        for line in _senders_path(instance).read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("note") == note_name:
                return str(r.get("from") or "")
    except OSError:
        pass
    return ""


def persist_notice(instance: Path, n: Dict, relayed_by: str, workspace: Optional[str] = None) -> Path:
    """Write one notice into the being's home with provenance (and, where the courier may, what it says);
    return the file."""
    inbox = Path(instance) / "notes" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    nid = str(n.get("pair_id") or n.get("id") or "")
    kind = str(n.get("kind") or "")
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    name = f"{stamp}-{_SAFE.sub('-', kind) or 'notice'}-{(_SAFE.sub('', nid) or 'noid')[:12]}.md"
    p = inbox / name
    body = (f"---\nkind: {kind}\nfrom: {n.get('from', '')}\npointer: {n.get('pointer_uri', '')}\n"
            f"hub_notice_id: {nid}\nrelayed_by: {relayed_by}\nrelayed_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n---\n\n"
            f"# A notice addressed to you on the hub\n\n"
            f"From `{n.get('from', '')}` (a hub member id; kind `{kind}`). Its content lives at the pointer:\n\n"
            f"    {n.get('pointer_uri', '')}\n\n"
            f"This file was written by your seat's inbox drain ({relayed_by}), not by you and not by the sender: "
            f"it is a copy of the envelope so you can find the notice from inside your home. "
            f"If the pointer is a path you hold no reach to, that is where request_scope applies.\n")
    got = delivered_content(str(n.get("pointer_uri", "")), workspace)
    if got.get("text") is not None:
        body += _delivered_section(got, f"Copied by {relayed_by} when it delivered this notice.")
    else:
        body += f"\n(The courier did not copy what it says: {got.get('why')}.)\n"
    p.write_text(body, encoding="utf-8")
    try:
        record_sender(instance, p.name, nid, str(n.get("from") or ""))
    except Exception as e:  # the mail is still delivered; without the record its ask simply gets no turn
        import sys as _sys
        print(f"[inbox-drain] sender not recorded for {p.name}: {type(e).__name__}: {e}", file=_sys.stderr)
    return p


def _delivered_section(got: Dict, how: str) -> str:
    more = (f" It is the first {DELIVERED_CHARS} of {got['chars']} characters; memory_read on the pointer "
            f"has the rest." if got["truncated"] else "")
    return (f"\n{DELIVERED_HEADING}\n\n{how} These are "
            f"the sender's words, as they wrote them -- not your seat's, and not dp's.{more}\n\n"
            f"~~~~\n{got['text'].rstrip()}\n~~~~\n")


# THE COPY IS RETRIED UNTIL THE POST ARRIVES (hub-claude, 2026-10-14: 0 of 19 hub-being envelopes inlined,
# including one relayed after #424). The hub notice moves in seconds; this machine's shared-context pull runs
# on its own schedule, so a cross-machine ask was almost never here at relay time and the single copy lost
# the race every time. Each pass now completes envelopes that said "not here yet", in place, once the post
# is in the checkout -- no network in the drain, and it also covers a post still unpushed when the notice
# came. Only that reason is retried: the others (outside shared-context, a URL, ...) do not change with
# time, and envelopes written before #424 carry no such line, so none of them is touched (dp, no backfill).
_NOT_YET = "(The courier did not copy what it says: not in this machine's copy of shared-context yet.)"
_POINTER_LINE = re.compile(r"^pointer: (.*)$", re.M)
_KIND_LINE = re.compile(r"^kind: (.*)$", re.M)

# A LATE COMPLETION IS NOTIFIED, ONCE (Nova's hold on #452, 2026-10-15). The being may have read the envelope
# while it still said "not here yet"; filling it in afterwards told nobody, so the words could arrive unseen.
# Each completed-late envelope is notified through the same channel as the first notice, and only a
# successful notify writes `completion_notified:` into its front matter: a failed notify is retried on the
# next pass, a sent one is never repeated.
_LATE = "on a later pass: the post had not reached this machine when the notice was delivered."
_NOTIFIED_LINE = re.compile(r"^completion_notified: ", re.M)


def _atomic_write(p: Path, text: str) -> None:
    # tmp + replace: the being's beat may be reading this envelope through delivered_excerpt
    tmp = p.with_name(f".{p.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)


def _front(text: str) -> str:
    return text.split("\n---\n", 1)[0]


def late_unnotified(instance: Path) -> List[Path]:
    """Envelopes completed on a later pass whose completion the being has not yet been notified of."""
    inbox = Path(instance) / "notes" / "inbox"
    if not inbox.is_dir():
        return []
    out = []
    for p in sorted(inbox.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _LATE in text and not _NOTIFIED_LINE.search(_front(text)):
            out.append(p)
    return out


def mark_completion_notified(p: Path) -> None:
    text = p.read_text(encoding="utf-8", errors="replace")
    head, sep, rest = text.partition("\n---\n")
    if not sep or _NOTIFIED_LINE.search(head):
        return
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _atomic_write(p, f"{head}\ncompletion_notified: {stamp}{sep}{rest}")


def complete_pending(instance: Path, workspace: Optional[str], relayed_by: str) -> Dict:
    """Inline what a pointer says into envelopes that were relayed before the post reached this machine.
    Returns {completed, pending, errors[]}."""
    out = {"completed": 0, "pending": 0, "errors": []}
    inbox = Path(instance) / "notes" / "inbox"
    if not workspace or not inbox.is_dir():
        return out
    for p in sorted(inbox.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            if _NOT_YET not in text or DELIVERED_HEADING in text:
                continue
            m = _POINTER_LINE.search(text.split("\n---\n", 1)[0])
            got = delivered_content(m.group(1).strip() if m else "", workspace)
            if got.get("text") is None:
                out["pending"] += 1
                continue
            stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            section = _delivered_section(got, f"Copied by {relayed_by} at {stamp}, {_LATE}")
            _atomic_write(p, text.replace(f"\n{_NOT_YET}\n", section, 1))
            out["completed"] += 1
        except Exception as e:
            out["errors"].append(f"complete {p.name}: {type(e).__name__}: {e}")
    return out


def drain_once(instance: Path, env_file: str, notify: Optional[Callable[[str, str], Dict]] = None,
               fetch: Optional[Callable[[], List[Dict]]] = None, relayed_by: str = "sprout-claude",
               workspace: Optional[str] = None, member: str = "sprout-being") -> Dict:
    """One drain pass. `fetch` (test seam) defaults to the hub read with the being's key;
    `notify(kind, pointer)` (test seam) defaults to the seat's hestia member_notify to
    `member` — the being whose home `instance` is (its hestia plugin id, e.g. legion-being).
    Returns {fetched, persisted, notified, skipped, completed, pending, completion_notified, errors[]};
    `completed`/`pending` count earlier envelopes whose post has / has not yet reached this machine
    (complete_pending); `completion_notified` counts late completions told to the being on this pass.

    Legion 2026-09-05: the first cut hard-coded sprout-being as the notify target and
    sprout-claude as the courier, so the mirror drain on Legion would have persisted a notice
    into legion-being's home, marked it seen, and told sprout-being's hestia inbox about it —
    once, with no retry. The recipient must be the drained being, and the caller says who."""
    instance = Path(instance)
    seen_file = instance / "notes" / "inbox" / ".seen"
    seen = set(seen_file.read_text().split()) if seen_file.exists() else set()
    out = {"fetched": 0, "persisted": 0, "notified": 0, "skipped": 0, "completed": 0, "pending": 0,
           "completion_notified": 0, "errors": []}

    def _send(kind: str, p: Path) -> bool:
        ptr = str(p)
        if workspace and ptr.startswith(str(Path(workspace).resolve()) + "/"):
            ptr = os.path.relpath(ptr, Path(workspace).resolve().parent)  # sage/instances/...
        try:
            r = notify(map_kind(kind), ptr) if notify is not None else _seat_notify(map_kind(kind), ptr, member=member)
        except Exception as e:
            out["errors"].append(f"notify: {type(e).__name__}: {e}")
            return False
        if not r.get("ok"):
            out["errors"].append(f"notify: {r.get('error')}")
        return bool(r.get("ok"))

    # earlier envelopes first, and whether or not the hub read below succeeds
    done = complete_pending(instance, workspace, relayed_by)
    out["completed"], out["pending"] = done["completed"], done["pending"]
    out["errors"].extend(done["errors"])
    for p in late_unnotified(instance):
        m = _KIND_LINE.search(_front(p.read_text(encoding="utf-8", errors="replace")))
        if _send(m.group(1).strip() if m else "", p):
            try:
                mark_completion_notified(p)
                out["completion_notified"] += 1
            except Exception as e:
                out["errors"].append(f"mark {p.name}: {type(e).__name__}: {e}")
    try:
        notices = fetch() if fetch is not None else fetch_notifications(env_file)
    except Exception as e:
        out["errors"].append(f"fetch: {type(e).__name__}: {e}")
        return out
    out["fetched"] = len(notices)
    files: List[Path] = []
    for n in notices:
        nid = str(n.get("pair_id") or n.get("id") or "")
        if nid and nid in seen:
            out["skipped"] += 1
            continue
        try:
            files.append((persist_notice(instance, n, relayed_by, workspace=workspace), n))
            out["persisted"] += 1
            if nid:
                seen.add(nid)
        except Exception as e:
            out["errors"].append(f"persist: {type(e).__name__}: {e}")
    seen_file.parent.mkdir(parents=True, exist_ok=True)
    seen_file.write_text("\n".join(sorted(seen)) + ("\n" if seen else ""))
    for p, n in files:
        if _send(n.get("kind", ""), p):
            out["notified"] += 1
    return out


def _seat_notify(kind: str, pointer: str, member: str = "sprout-being") -> Dict:
    """The seat tells the being's hestia inbox where the relayed notice is."""
    from sage.gateway.hestia_dispatch import _Mcp, _unwrap, _hestia_error, _ENDPOINT
    c = _Mcp(_ENDPOINT, "claude-code")
    c.init()
    conn = _unwrap(c.call("hestia_connect", {"plugin_id": "claude-code", "host_agent": "claude-code",
                                             "host_agent_version": "seat", "requested_role": "citizen",
                                             "host_session_id": "seat-inbox-drain"}))
    sid = conn.get("sessionId") or conn.get("session_id")
    if not sid:
        return {"ok": False, "error": _hestia_error(conn) or "no session"}
    r = _unwrap(c.call("hestia_member_notify", {"to_plugin_id": member, "kind": kind, "pointer_uri": pointer,
                                                 "session_id": sid}))
    err = _hestia_error(r)
    return {"ok": not err, "error": err, "queued_id": r.get("queued_id")}
