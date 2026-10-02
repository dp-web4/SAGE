"""The room: voice as a conversation (dp, 2026-09-26).

dp asked whether voice should be its own transcript or live in the text chat with voice markers.
Its own conversation, because:

  * NOT dp's channel. Every turn there says `from: dp`, asserted by a known local route. A voice is
    not authenticated: sprout-being took dp's first spoken "Can you hear me?" for "the phone's
    voice assistant". Writing unidentified words into dp's channel would either claim dp said them
    or dilute the one thing that channel guarantees.
  * NOT a side log. Heard words shown only in the body block got prose about them and no answer:
    the waiting check, the answer phase, the echo guard and the clock's "last wrote to you" all
    live in the conversation layer. As turns in `room`, voice gets all of it.

So heard words become turns `from: "voice"`, `via: "voice"`, stamped when they were HEARD; what the
being says aloud becomes its own turn `via: "speak"`; and `say to: "room"` is spoken, not written,
so answering aloud is the verb the being already uses. The room exists only on a body that can
speak. By default the mic transcribes only in the minutes after the being speaks; a body with
SAGE_LISTEN=always hears the room at any time, and presence writes each heard line here as it
arrives (2026-10-01).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOM = "room"
VOICE = "voice"
WATERMARK = "room.heard_until"      # beside the conversation, in the being's own home


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure(instance: Path, member: str) -> dict:
    from sage.gateway import conversations as conv
    return conv.create(
        Path(instance), ROOM, title="the room: spoken aloud and heard",
        participants=[member, VOICE], writable_by=[member, VOICE],
        summary=("What you said aloud (speak, or say to room) and what the mic heard: in the "
                 "minutes after you speak, or at any time if your ear is always open. A line from 'voice' is whoever was in the room; it does not say "
                 "who unless the words do. Anything you say to room is spoken aloud, not written."))


def _watermark_path(instance: Path) -> Path:
    from sage.gateway import conversations as conv
    return conv.conv_dir(Path(instance)) / WATERMARK


OVERLAP_S = 600      # the watermark bounds the search; this much before it is re-read and deduped


def heard_id(h: dict) -> str:
    """A heard event's stable identity: when, which mic node, what words."""
    import hashlib
    key = f"{float(h.get('ts', 0)):.3f}|{h.get('source') or ''}|{str(h.get('text') or '').strip()}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


UNCLEAR_MARK = {"tail": "{t} [the rest was unclear]", "head": "[the start was unclear] {t}",
                "middle": "{t} [part of it was unclear]"}


def heard_text(h: dict) -> str:
    """The heard words, saying where unclear speech was left out (listening.judge_segments), so a sentence the
    transcriber gave up on is not presented as a sentence that ended there."""
    t = str(h.get("text", "")).strip()
    mark = UNCLEAR_MARK.get(str(h.get("unclear") or ""))
    return mark.format(t=t) if mark and t else t


def ingest_heard(instance: Path, member: str, inventory: Optional[dict] = None,
                 heard: Optional[list] = None) -> list:
    """Carry heard words into the room as `voice` turns, each exactly once.

    THE CONVERSATION IS THE AUTHORITY (GPT review of #228). Each turn carries `heard_id`, and an
    event whose id is already in the room is skipped. The watermark is only a search bound, read
    back OVERLAP_S early, so neither failure GPT named can break "once each": an append that
    lands before a watermark write fails is found by id next time, and same-timestamp siblings
    are both inside the overlap and told apart by id. Returns the turns appended."""
    from sage.gateway import body
    from sage.gateway import conversations as conv
    instance = Path(instance)
    wm = _watermark_path(instance)
    try:
        after = float(wm.read_text().strip()) - OVERLAP_S
    except Exception:
        after = time.time() - 3 * 3600      # first run: only recent words, never the whole log
    new = [h for h in (heard if heard is not None else body._heard_since(after))
           if float(h.get("ts", 0)) > after and str(h.get("text", "")).strip()]
    if not new:
        return []
    ensure(instance, member)
    have = {t.get("heard_id") for t in conv.recent(instance, ROOM, limit=1000) if t.get("heard_id")}
    out, top = [], None
    for h in sorted(new, key=lambda h: float(h["ts"])):
        hid = heard_id(h)
        if hid in have:
            continue
        mic = body._heard_mic([h], inventory)
        t = conv.append(instance, ROOM, speaker=VOICE, text=heard_text(h), via="voice",
                        ts=_iso(h["ts"]), enforce_write=False, extra={"heard_id": hid, "mic": mic})
        have.add(hid)
        out.append(t)
        top = max(top or 0.0, float(h["ts"]))
    if top is not None:
        try:
            prev = float(wm.read_text().strip())
        except Exception:
            prev = 0.0
        try:
            wm.write_text(str(max(prev, top)))
        except Exception:
            pass    # the ids in the room already make a re-read safe
    return out


def record_spoken(instance: Path, member: str, text: str, witness: Optional[str] = None,
                  beat: Optional[str] = None) -> Optional[dict]:
    """The being's own spoken line, as its turn in the room."""
    from sage.gateway import conversations as conv
    ensure(Path(instance), member)
    return conv.append(Path(instance), ROOM, speaker=member, text=text, via="speak",
                       witness=witness, beat=beat)


def _words(text: str) -> tuple:
    import re
    return tuple(re.findall(r"[a-z0-9']+", (text or "").lower()))


def repeats_heard(instance: Path, text: str, lookback: int = 3) -> Optional[str]:
    """The recent voice line that `text` repeats word for word, or None."""
    from sage.gateway import conversations as conv
    w = _words(text)
    if not w:
        return None
    for t in [t for t in conv.recent(Path(instance), ROOM, limit=12) if t.get("from") == VOICE][-lookback:]:
        if _words(t.get("text")) == w:
            return t.get("text")
    return None

