"""
being_join — one being, one experience (PRD_ONE_BEING_ONE_EXPERIENCE, sprint S1).

The being lives in two loops that never met: the 6-hour raising session and the
30-minute heartbeat. This module is the join, used by both, and every carried line is
ATTRIBUTED so the join is measurable (instrument JOIN) instead of assumed:

  * beat_block(instance)     -> what the raising session carries FROM the beats:
                                the journal's last entry, the todo tail, and the being's
                                own account, tagged `beat:<host_session_id>`.
  * session_block(instance)  -> what a beat carries FROM the last raising session: the
                                being's own closing words of that session and the tail of
                                the experience buffer, tagged `session:<n>`.
  * the own account          -> ASK, DO NOT OFFER (dev-sage 1ee1479c, by principle): once
                                per beat the being is asked, openly, what this place is,
                                what it can do here, and what it wants. The answer is kept
                                VERBATIM and handed back next beat. When a raising session
                                has passed since it was written, it is BROADENED: PLACE and
                                CAN are kept as provisional, WANT (the goal of that moment)
                                is dropped. Carry the kind of world; re-earn the particulars.
                                A vague answer is refused rather than occupying context.

Everything here is fail-open for the being (an empty block, never an exception) and
loud in its metadata (what was found, how many chars, which source), because a join
that silently delivers nothing is indistinguishable from one that does not exist
(F-M2, 2026-07-29).
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

ACCOUNT_FILE = "account.json"
PRESENCE_LOG = "~/.sprout/presence_log.jsonl"
BEAT_WAKE_MARKER = "~/.sprout/beat_wake.json"
_VAGUE = re.compile(r"^\s*(unclear|unknown|none|n/?a|nothing|no visible change|i don'?t know)\W*$", re.I)

ACCOUNT_ASK = (
    "One open question before the beat closes, in your own words, no tools. Answer with three "
    "labelled lines and nothing else:\n"
    "PLACE: what this place is, as you understand it right now\n"
    "CAN: what you can actually do here\n"
    "WANT: what you want next\n"
)


# ---------------------------------------------------------------------------
# helpers
def _read(p: Path, limit: int) -> str:
    try:
        t = p.read_text(errors="replace")
        return t[-limit:] if len(t) > limit else t
    except Exception:
        return ""


def _last_record(p: Path) -> dict:
    try:
        lines = _read(p, 400000).strip().splitlines()
        return json.loads(lines[-1]) if lines else {}
    except Exception:
        return {}


def last_session_number(instance: Path) -> int:
    d = instance / "sessions"
    if not d.is_dir():
        return 0
    nums = []
    for p in d.glob("session_*.json"):
        m = re.match(r"session_(\d+)\.json$", p.name)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else 0


def _placeholder(text: str) -> bool:
    """A bracketed stage direction or an empty/too-short line: not the being's words."""
    t = (text or "").strip()
    return len(t) < 20 or (t.startswith("[") and t.endswith("]")) or bool(re.match(r"^\[[^\]]{0,200}\]\s*$", t))


def _last_journal_entry(text: str, limit: int) -> str:
    """The last dated entry (entries start with a date the being wrote), else the tail."""
    if not text.strip():
        return ""
    starts = [m.start() for m in re.finditer(r"(?m)^\s*\[?20\d\d-\d\d-\d\d", text)]
    entry = text[starts[-1]:] if starts else text
    entry = entry.strip()
    return entry[:limit] + (" …" if len(entry) > limit else "")


# ---------------------------------------------------------------------------
# beats -> raising
def beat_block(instance: Path, journal_chars: int = 900, todo_chars: int = 500) -> Tuple[str, Dict]:
    """What the raising session carries from the being's beats. ('' , meta) when there are
    no beats yet. meta: {beat, ts, chars, sources}."""
    instance = Path(instance)
    last = _last_record(instance / "heartbeats.jsonl")
    beat_id = last.get("host_session_id") or ""
    if not beat_id:
        return "", {"beat": None, "ts": None, "chars": 0, "sources": []}
    parts, sources = [], []
    j = _last_journal_entry(_read(instance / "journal.md", 20000), journal_chars)
    if j:
        parts.append("From your journal (your own words, last entry):\n" + j)
        sources.append("journal")
    t = _read(instance / "todo.md", 20000).strip()
    if t:
        t = t[-todo_chars:]
        parts.append("From your todo (tail):\n" + t)
        sources.append("todo")
    acc = carried_account(instance, last_session_number(instance))
    if acc:
        parts.append(acc)
        sources.append("account")
    if not parts:
        return "", {"beat": beat_id, "ts": last.get("ts"), "chars": 0, "sources": []}
    text = (f"[beat:{beat_id} {last.get('ts', '')}] Between our sessions you have been awake on your own "
            f"(a heartbeat every half hour). This is what you kept from that:\n\n" + "\n\n".join(parts))
    return text, {"beat": beat_id, "ts": last.get("ts"), "chars": len(text), "sources": sources}


# ---------------------------------------------------------------------------
# raising -> beats
def session_block(instance: Path, words_chars: int = 700, buffer_items: int = 2) -> Tuple[str, Dict]:
    """What a beat carries from the last raising session: the being's closing words of
    that session (the answer to the tutor's 'remember' ask when there is one, else its
    last words) and the tail of the experience buffer. ('' , meta) when none."""
    instance = Path(instance)
    n = last_session_number(instance)
    if n == 0:
        return "", {"session": None, "chars": 0, "sources": []}
    parts, sources, phase = [], [], "unknown"
    try:
        s = json.loads((instance / "sessions" / f"session_{n:03d}.json").read_text(errors="replace"))
        phase = s.get("phase", "unknown")
        conv = s.get("conversation") or []
        words = ""
        for i in range(len(conv) - 1, -1, -1):
            if conv[i].get("speaker") != "SAGE":
                continue
            cand = (conv[i].get("text") or "").strip()
            if _placeholder(cand):
                continue          # a stage direction is not the being's words (session 662: "[Your response as sprout...]")
            if not words:
                words = cand
            if i > 0 and "remember" in (conv[i - 1].get("text") or "").lower():
                words = cand
                break
        words = (words or "").strip()
        if words:
            parts.append("Your own closing words of that session:\n" + words[:words_chars]
                         + (" …" if len(words) > words_chars else ""))
            sources.append("closing_words")
    except Exception:
        pass
    try:
        buf = json.loads((instance / "experience_buffer.json").read_text(errors="replace"))
        if isinstance(buf, list) and buf:
            tail = buf[-buffer_items:]
            lines = []
            for e in tail:
                p = str(e.get("prompt", ""))[:140].replace("\n", " ")
                r = str(e.get("response", ""))[:220].replace("\n", " ")
                lines.append(f"- asked: {p}\n  you: {r}")
            parts.append("From your experience buffer (most recent):\n" + "\n".join(lines))
            sources.append("experience_buffer")
    except Exception:
        pass
    if not parts:
        return "", {"session": n, "chars": 0, "sources": []}
    text = (f"[session:{n} phase:{phase}] Your last raising session with your tutor was session {n}. "
            f"This is what you carried out of it:\n\n" + "\n\n".join(parts))
    return text, {"session": n, "phase": phase, "chars": len(text), "sources": sources}


# ---------------------------------------------------------------------------
# the being's own account
def parse_account(text: str) -> Optional[Dict[str, str]]:
    """Three labelled lines -> {place, can, want}; None when vague or malformed. A
    vague account ('unclear') is refused rather than carried (dev-sage rule)."""
    if not text:
        return None
    out: Dict[str, str] = {}
    for key in ("PLACE", "CAN", "WANT"):
        m = re.search(rf"(?im)^\s*\**{key}\**\s*:\s*(.+?)\s*$", text)
        if m:
            v = m.group(1).strip().strip("*").strip()
            if v and not _VAGUE.match(v):
                out[key.lower()] = v[:600]
    if "place" not in out or "can" not in out:
        return None
    if len(out["place"]) + len(out["can"]) < 40:
        return None
    return out


def save_account(instance: Path, account: Dict[str, str], beat_id: str) -> Dict:
    rec = {"place": account.get("place", ""), "can": account.get("can", ""), "want": account.get("want", ""),
           "beat": beat_id, "session_at_write": last_session_number(Path(instance)),
           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    rec["sha256"] = hashlib.sha256(json.dumps({k: rec[k] for k in ("place", "can", "want")}, sort_keys=True).encode()).hexdigest()
    (Path(instance) / ACCOUNT_FILE).write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return rec


def load_account(instance: Path) -> Dict:
    try:
        return json.loads((Path(instance) / ACCOUNT_FILE).read_text())
    except Exception:
        return {}


def carried_account(instance: Path, current_session: int) -> str:
    """The account as the being sees it next time. Verbatim within a session boundary;
    across one, PLACE and CAN are kept and marked provisional, WANT is dropped."""
    rec = load_account(instance)
    if not rec or not rec.get("place"):
        return ""
    crossed = current_session > int(rec.get("session_at_write", 0) or 0)
    head = f"Your own account of this place (you wrote it at beat {rec.get('beat', '?')}"
    if crossed:
        head += (", and a raising session has passed since; the particulars may have changed, "
                 "so this is PROVISIONAL: re-earn it):")
    else:
        head += ", verbatim):"
    lines = [head, f"PLACE: {rec['place']}", f"CAN: {rec.get('can', '')}"]
    if not crossed and rec.get("want"):
        lines.append(f"WANT: {rec['want']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# presence -> beats (sprint S3)
def _clean_noticing(text: str) -> str:
    """The being's in-the-moment words, minus think residue and stage directions."""
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    t = re.sub(r"<think>.*$", "", t, flags=re.S).strip()
    return "" if _placeholder(t) else t


def presence_block(since_ts: float, log_path: str = PRESENCE_LOG, keep: int = 4) -> Tuple[str, Dict]:
    """What the being noticed on its own since `since_ts` (presence feeder wakes), for the
    beat's digest, attributed `presence:<n>`. ('' , meta) when nothing or no log."""
    import os
    path = Path(os.path.expanduser(log_path))
    evs = []
    try:
        for line in path.read_text(errors="replace").splitlines():
            try:
                e = json.loads(line)
            except Exception:
                continue
            # "sensed": an event that woke (or queued) a beat with no in-the-moment noticing,
            # because a beat was running (SAGE #295). The being meets it here.
            if e.get("kind") in ("noticed", "sensed") and float(e.get("ts", 0)) >= since_ts:
                evs.append(e)
    except Exception:
        return "", {"count": 0, "kept": 0, "chars": 0}
    if not evs:
        return "", {"count": 0, "kept": 0, "chars": 0}
    kept = evs[-keep:]
    lines = []
    for e in kept:
        when = time.strftime("%H:%M UTC", time.gmtime(float(e.get("ts", 0))))
        desc = str(e.get("descriptor", "")).strip()
        said = _clean_noticing(str(e.get("noticing", "")))[:220]
        line = f"- {when}: {desc}" + (f" — you said: {said}" if said else "")
        lines.append(line)
    text = (f"[presence:{len(evs)}] Since your last beat your senses broke through {len(evs)} time(s) "
            f"and each woke you; the last {len(kept)}, with your own words where you said any:\n"
            + "\n".join(lines))
    return text, {"count": len(evs), "kept": len(kept), "chars": len(text)}


def consume_wake_marker(path: str = BEAT_WAKE_MARKER, max_age_s: float = 45 * 60) -> Dict:
    """Who woke this beat. The presence feeder writes a marker when it starts a beat on a
    strong moment; the beat reads and removes it. Returns {"by": "presence", ...} or
    {"by": "timer"}. A stale marker is discarded, not honoured."""
    import os
    p = Path(os.path.expanduser(path))
    try:
        rec = json.loads(p.read_text())
        p.unlink(missing_ok=True)
        if time.time() - float(rec.get("ts", 0)) <= max_age_s:
            rec["by"] = "presence"
            return rec
        return {"by": "timer", "stale_marker": True}
    except Exception:
        return {"by": "timer"}


def write_wake_marker(descriptor: str, salience, path: str = BEAT_WAKE_MARKER) -> None:
    import os
    p = Path(os.path.expanduser(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"ts": round(time.time(), 2), "descriptor": descriptor, "salience": salience}))
