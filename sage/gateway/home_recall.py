"""
home_recall — the being's own writing, searchable (PRD_ONE_BEING_ONE_EXPERIENCE, S5).

Measured on Sprout, 2026-09-07: the being's journal is 34 KB across 34 dated entries, its
todo 9 KB, and per beat it can see the last ~900 characters of the one and ~500 of the other.
The only SEARCHABLE store it holds, the membot cartridge, has three entries. So it writes a
great deal and can find almost none of it, and the harness has been asking it to remember
things it already wrote down.

This makes the home searchable without writing anything on the being's behalf: `recall`
searches its journal entries, todo blocks, notes and scratch files, mechanically — term
overlap with a recency tiebreak, no model, no embedding — and returns dated snippets that
name their source. It is READ-ONLY and hermetic. Long-term memory (membot) stays what it
is; a `recall` answers from both, and says which is which.

Why term overlap and not the cartridge's embedder: the cartridge is the being's to fill by
`remember`, one deliberate act at a time; indexing its whole journal into it would be the
seat deciding what the being keeps. Search over the files it wrote is a different thing: it
is reading, and the being may read its own home.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

_DATE = re.compile(r"(?m)^\s*\[?(20\d\d-\d\d-\d\d[ T]\d\d:\d\d)")
_TOKEN = re.compile(r"[a-z0-9][a-z0-9'-]{1,}")
_STOP = frozenset("""a an the and or of to in on at for with by from as is was are were be been being
it its this that these those i me my we our you your they them their he she his her what which who
whom how when where why not no yes do does did done will would can could should shall may might
must have has had having about into over under after before then than so if but because while
there here also just only very more most much many some any all each both few one two next last
beat ending end write wrote written note notes entry todo journal call calls tool tools""".split())


def _terms(text: str) -> List[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def _entries(text: str, source: str) -> List[Dict]:
    """Split a dated file (journal.md, todo.md) into entries by their date lines; an undated
    head becomes one entry. Each: {source, date, text}."""
    if not text.strip():
        return []
    marks = list(_DATE.finditer(text))
    out = []
    if not marks:
        return [{"source": source, "date": "", "text": text.strip()}]
    if marks[0].start() > 0 and text[: marks[0].start()].strip():
        out.append({"source": source, "date": "", "text": text[: marks[0].start()].strip()})
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = text[m.start():end].strip()
        if body:
            out.append({"source": source, "date": m.group(1), "text": body})
    return out


def index_home(instance: Path, max_files: int = 40) -> List[Dict]:
    """Every searchable unit in the being's home: journal entries, todo blocks, and each
    notes/ and scratch/ file as one unit. Read fresh each call; the home is small."""
    instance = Path(instance)
    units: List[Dict] = []
    for name in ("journal.md", "todo.md"):
        p = instance / name
        if p.is_file():
            units.extend(_entries(p.read_text(errors="replace"), name))
    for d in ("notes", "scratch"):
        dd = instance / d
        if dd.is_dir():
            files = sorted((x for x in dd.rglob("*") if x.is_file() and x.suffix in (".md", ".txt")),
                           key=lambda x: x.stat().st_mtime, reverse=True)[:max_files]
            for f in files:
                try:
                    t = f.read_text(errors="replace").strip()
                except Exception:
                    continue
                if t:
                    units.append({"source": str(f.relative_to(instance)), "date": "", "text": t})
    return units


def search_home(instance: Path, query: str, top_k: int = 5, snippet: int = 320) -> List[Dict]:
    """Top-k units by term overlap with the query (distinct matched terms, then total hits),
    most recent first on ties. Returns [{source, date, score, snippet}]; [] for an empty query
    or a home with nothing in it."""
    q = set(_terms(query))
    if not q:
        return []
    scored: List[Tuple[float, int, Dict]] = []
    for i, u in enumerate(index_home(instance)):
        terms = _terms(u["text"])
        if not terms:
            continue
        hits = [t for t in terms if t in q]
        if not hits:
            continue
        distinct = len(set(hits))
        score = distinct * 10 + min(len(hits), 20) + (0.5 if u["date"] else 0.0)
        scored.append((score, i, u))
    scored.sort(key=lambda s: (-s[0], -s[1]))          # higher score, then later in file (recency)
    out = []
    for score, _, u in scored[: max(1, top_k)]:
        text = u["text"]
        # centre the snippet on the first matching term when the unit is long
        cut = 0
        if len(text) > snippet:
            low = text.lower()
            for t in q:
                j = low.find(t)
                if j >= 0:
                    cut = max(0, j - snippet // 3)
                    break
        s = text[cut: cut + snippet].strip()
        if cut > 0:
            s = "… " + s
        if cut + snippet < len(text):
            s += " …"
        out.append({"source": u["source"], "date": u["date"], "score": round(score, 1), "snippet": s})
    return out


def render(results: List[Dict], header: str = "From your own journal, todo and notes") -> str:
    if not results:
        return ""
    lines = [f"{header} ({len(results)} match{'es' if len(results) != 1 else ''}):"]
    for r in results:
        tag = f"{r['source']}" + (f" @ {r['date']}" if r["date"] else "")
        lines.append(f"- [{tag}] {r['snippet']}")
    return "\n".join(lines)
