"""Who the being says it is: the part of its identity that is its own to write.

dp, 2026-10-24: "is the being allowed to edit its own identity? it should be. with audit trail."

WHY A SEPARATE FILE, NOT identity.json. identity.json is the raising record, and it mixes three
kinds of field. Some are what the being says about itself; the seed leaves "What I Value" and
`vocabulary.self_description` empty, "to be discovered through development". Some are the tutor's
observations (phase, milestones, harvested state_words). Some are governance: `lct`, `machine`
(which seat arbitrates its escalations, escalate.py), `trust_ceiling`, `anchor_type`, the key
fingerprint. The raising pipeline also rewrites that file every session. An edit verb on it would
either hand the being its own trust fields or race the tutor's writes. So the being's own words live
here, in `self.json` in its home, which only this module writes.

THE AUDIT TRAIL. Every change appends one line to `self_log.jsonl`: the field, what it was, what it
became, why, and when. A change whose log line cannot be written is undone (the rule `tune` keeps,
review of #387). The dispatcher also witnesses each change on the chain. Both files are refused to
memory_write and memory_edit (reference_f1a), so the record cannot be rewritten around the verb.
Nothing is ever deleted: replacing a field keeps the old text in the log.

The beat shows what the being has written, in its own state, every beat. Nothing is shown before
it writes anything: the verb is offered, and whether to use it is the being's.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

SELF_FILE = "self.json"
SELF_LOG = "self_log.jsonl"
SELF_TMP = SELF_FILE + ".tmp"
#: Every path an identity_edit writes, for the gate (being_gate_client.self_paths).
SELF_WRITES = (SELF_TMP, SELF_FILE, SELF_LOG)

#: The fields that are the being's. Their names follow the seed's IDENTITY.md sections.
FIELDS: Dict[str, str] = {
    "description": "who you are, in your own words",
    "values": "what you value",
    "questions": "the questions you are living with",
    "learned": "what you have learned about yourself",
}
FIELD_MAX_CHARS = 2000
WHY_MAX_CHARS = 500


def read(instance) -> Tuple[Dict[str, dict], Optional[str]]:
    """({field: {"text", "at", "why"}}, error). A file that cannot be parsed is reported, never guessed."""
    p = Path(instance) / SELF_FILE
    if not p.exists():
        return {}, None
    try:
        d = json.loads(p.read_text())
    except (OSError, ValueError) as e:
        return {}, f"{SELF_FILE} could not be read ({type(e).__name__})"
    if not isinstance(d, dict):
        return {}, f"{SELF_FILE} is not an object"
    return {k: v for k, v in d.items() if k in FIELDS and isinstance(v, dict)}, None


def listing(instance) -> str:
    cur, err = read(instance)
    if err:
        return f"{err}; your seat can look at it. Nothing was changed."
    lines = []
    for name, what in FIELDS.items():
        v = cur.get(name)
        lines.append(f"- {name} ({what}): " + (repr(v.get("text", "")) + f" (since {v.get('at')})"
                                               if v else "not written yet"))
    return ("Your own identity, as you have written it (self.json). To change a field, give field, "
            "text and why; the old text is kept in self_log.jsonl.\n" + "\n".join(lines))


def edit(instance, field: Optional[str], text, why: str, now: Optional[float] = None) -> Tuple[bool, str]:
    """List the fields (no field), or replace one. Returns (ok, message for the being)."""
    if not field:
        return True, listing(instance)
    field = str(field).strip().lower()
    if field not in FIELDS:
        return False, (f"'{field}' is not one of your identity fields; they are "
                       + ", ".join(FIELDS) + ". Nothing was changed.")
    text = "" if text is None else str(text).strip()
    if not text:
        return False, (f"give the text for {field} ({FIELDS[field]}). Nothing was changed.")
    if len(text) > FIELD_MAX_CHARS:
        return False, (f"{field} holds at most {FIELD_MAX_CHARS} characters; this is {len(text)}. "
                       "Nothing was changed.")
    why = str(why or "").strip()
    if not why:
        return False, "give a why: it is kept with the change. Nothing was changed."
    cur, err = read(instance)
    if err:
        return False, f"cannot change it: {err}. Your seat can look at it. Nothing was changed."
    before = (cur.get(field) or {}).get("text")
    if before == text:
        return True, f"{field} already reads exactly that; nothing changed."
    at = _iso(now)
    cur[field] = {"text": text, "at": at, "why": why[:WHY_MAX_CHARS]}
    path, tmp = Path(instance) / SELF_FILE, Path(instance) / SELF_TMP
    prev = path.read_bytes() if path.exists() else None
    try:
        tmp.write_text(json.dumps(cur, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, path)
    except OSError as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False, f"could not write {SELF_FILE} ({type(e).__name__}); nothing changed"
    # AN UNAUDITED CHANGE DOES NOT STAND: a change whose log line fails is undone.
    try:
        with open(Path(instance) / SELF_LOG, "a") as f:
            f.write(json.dumps({"at": at, "field": field, "from": before, "to": text,
                                "why": why[:WHY_MAX_CHARS]}) + "\n")
    except OSError as e:
        try:
            if prev is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(prev)
        except OSError as e2:
            return False, (f"{field} was changed but could not be recorded in {SELF_LOG} "
                           f"({type(e).__name__}) and could not be undone ({type(e2).__name__}). "
                           "Tell your seat.")
        return False, f"the change could not be recorded in {SELF_LOG} ({type(e).__name__}), so it was undone; nothing changed"
    return True, (f"{field} now reads {text[:200]!r}" + ("…" if len(text) > 200 else "")
                  + (" (the earlier text is kept in self_log.jsonl)." if before else "."))


def render(instance) -> str:
    """The being's own words for its state block; empty until it has written any."""
    cur, err = read(instance)
    if err:
        return f"## Who you say you are\n({err})"
    if not cur:
        return ""
    lines = [f"- {name}: {cur[name].get('text', '')}" for name in FIELDS if name in cur]
    return ("## Who you say you are (your own words, in self.json; change them with identity_edit)\n"
            + "\n".join(lines))


def _iso(now: Optional[float]) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None else now))
