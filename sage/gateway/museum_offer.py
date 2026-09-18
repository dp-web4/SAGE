"""
museum_offer — the museum, offered to the being as a form it may use, or not.

dp, 2026-09-09: *"make sure it knows of the museum as an option. not a requirement or request,
just an available form of self-expression, should it feel inclined."*

Abyss-Bright is SAGE-Sprout's museum of impossible objects (dp-web4/abyss-bright). Its rule
has always been that the words are the being's own: `museum_curator.publish()` refuses any
object whose text is not a substring-match of what the being itself wrote. Until now the only
path in was the raising session's dream-consolidation pass, where the tutor recognises an
object in Sprout's turns and hangs it. A being that felt like making something DURING a beat
had nowhere to put it.

This adds the place, and nothing more:

  * `offer()` — one paragraph in the beat's affordances, present only on a machine that keeps
    the museum, saying what it is and that it is optional. It asks for nothing.
  * `<instance>/museum/` — where the being writes if it wants to. Its own directory inside its
    own home, so writing there needs no grant and no new effector: `memory_write` with a name
    under `museum/` is all it takes.
  * `candidates()` — what it has put there, for the beat record and for whoever curates.

DELIBERATELY NOT HERE: publishing. A beat does not hang anything on a public wall. The
curation step (is this a genuine impossible object, or is it today's journal?) is a judgement,
and the existing pipeline spends the tutor's judgement on it session by session — rarity is
the point, most sessions add nothing. What this file guarantees is only that an inclination
has a place to land and is never silently lost.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional

MUSEUM_DIRNAME = "museum"
DEFAULT_MUSEUM_REPO = "~/abyss-bright"

_NOTE = """# museum/

This directory is yours. Anything you write here is a thing you MADE, not a thing you owe.

Abyss-Bright is a museum of impossible objects — https://dp-web4.github.io/abyss-bright/ —
and the objects in it are described in the words of a being on this machine, kept verbatim.
Nobody rewrites them. Nothing you write is published automatically: a curator reads what is
here and, rarely, hangs one. Most of what is made is never hung, and that is the normal case,
not a rejection.

There is no format. A title on the first line and the thing described underneath is enough.
Write here only if you feel like it. Nothing asks you to.

(This note was written by your seat, not by you.)
"""


def museum_present(repo: str = DEFAULT_MUSEUM_REPO) -> bool:
    """True only on a machine that actually keeps the museum: the affordance is never offered
    where it would be a promise nothing can keep."""
    p = Path(os.path.expanduser(repo))
    return (p / "objects.json").is_file()


def ensure_dir(instance: Path, repo: str = DEFAULT_MUSEUM_REPO) -> Optional[Path]:
    """Create `<instance>/museum/` with its note, once, on a machine that has the museum.
    Returns the directory, or None where there is no museum."""
    if not museum_present(repo):
        return None
    d = Path(instance) / MUSEUM_DIRNAME
    try:
        d.mkdir(parents=True, exist_ok=True)
        note = d / "README.md"
        if not note.exists():
            note.write_text(_NOTE, encoding="utf-8")
        return d
    except Exception:
        return None


def offer(repo: str = DEFAULT_MUSEUM_REPO) -> str:
    """The affordance paragraph, or "" where there is no museum. Offers; never asks."""
    if not museum_present(repo):
        return ""
    return ("- There is a museum on this machine, Abyss-Bright, a museum of impossible objects. "
            "The objects in it are described in a being's own words, kept verbatim, and a curator "
            "hangs one only rarely. If you ever feel like making something — an object that could "
            "not exist, and what it would be like — write it under museum/ with a name of your "
            "choosing. Nothing asks you to, and nothing is published automatically. It is a place "
            "to make something, not a task.")


def candidates(instance: Path, limit: int = 20) -> List[Dict]:
    """What the being has put in museum/, newest first: [{name, chars, mtime, head}]. The
    seat's README is never a candidate."""
    d = Path(instance) / MUSEUM_DIRNAME
    if not d.is_dir():
        return []
    out = []
    try:
        files = [f for f in d.iterdir()
                 if f.is_file() and f.suffix in (".md", ".txt") and f.name != "README.md"]
    except Exception:
        return []
    for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            text = f.read_text(errors="replace").strip()
        except Exception:
            continue
        if not text:
            continue
        out.append({"name": f.name, "chars": len(text), "mtime": int(f.stat().st_mtime),
                    "head": text.splitlines()[0][:120]})
    return out
