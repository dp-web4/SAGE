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
CONVERSATION_TURNS = 400       # per conversation; the view is bounded, the file never is


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


def index_home(instance: Path, max_files: int = 40, conversations: bool = True) -> List[Dict]:
    """Every searchable unit in the being's home: journal entries, todo blocks, each notes/
    and scratch/ file as one unit, and each conversation turn (SG1). Read fresh each call;
    the home is small."""
    instance = Path(instance)
    units: List[Dict] = []
    # A retired journal or todo (retire_note, journal.retired-<date>.md) stays searchable: retiring
    # starts the file fresh, it does not take the being's history out of its own recall.
    names = ["journal.md", "todo.md"]
    if instance.is_dir():
        names += sorted(x.name for x in instance.iterdir()
                        if x.is_file() and x.name.startswith(("journal.retired-", "todo.retired-")))
    for name in names:
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
    if conversations:
        units.extend(conversation_units(instance))
    return units


def conversation_units(instance: Path, per_conversation: int = CONVERSATION_TURNS) -> List[Dict]:
    """Each turn of each conversation in the home, as one unit naming its speaker and seq.

    SG1 (paged-context PRD §9a), measured 2026-11-07 on nomad-being: dp asked for "details on
    textstats project" and the being said it had none. Its own diagnosis of the bug was seq 55
    of that same conversation (2026-10-31), and the index this module built did not include
    conversations at all, so neither `recall` nor beat-start recall could reach it. Reading
    its own conversations is reading its own home: nothing here is written or chosen for it."""
    import json
    out: List[Dict] = []
    d = Path(instance) / "conversations"
    if not d.is_dir():
        return out
    for f in sorted(x for x in d.iterdir() if x.is_file() and x.suffix == ".jsonl"):
        try:
            lines = [l for l in f.read_text(errors="replace").splitlines() if l.strip()]
        except Exception:
            continue
        for line in lines[-max(1, per_conversation):]:
            try:
                turn = json.loads(line)
            except Exception:
                continue
            text = " ".join(str(turn.get("text") or "").split())
            if not text:
                continue
            ts = str(turn.get("ts") or "")
            out.append({"source": f"conversations/{f.name}", "date": ts[:16].replace("T", " "),
                        "seq": turn.get("seq"), "from": turn.get("from"),
                        "text": f"{turn.get('from')}: {text}"})
    return out


def search_home(instance: Path, query: str, top_k: int = 5, snippet: int = 320,
                exclude=None) -> List[Dict]:
    """Top-k units by term overlap with the query (distinct matched terms, then total hits),
    most recent first on ties. Returns [{source, date, score, snippet}]; [] for an empty query
    or a home with nothing in it. `exclude` is a set of (source, seq) units left out, so a
    question is never answered with itself."""
    return _rank(index_home(instance), query, top_k, snippet, exclude=exclude)


def _rank(units: List[Dict], query: str, top_k: int, snippet: int, exclude=None,
          spread: bool = False) -> List[Dict]:
    q = set(_terms(query))
    if not q:
        return []
    skip = set(exclude or ())
    scored: List[Tuple[float, int, Dict]] = []
    for i, u in enumerate(units):
        if (u["source"], u.get("seq")) in skip:
            continue
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
    if spread:
        scored = _spread(scored)
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
        r = {"source": u["source"], "date": u["date"], "score": round(score, 1), "snippet": s}
        if u.get("seq") is not None:
            r["seq"] = u["seq"]
        out.append(r)
    return out


def _shingles(text: str) -> set:
    w = _terms(text)
    return {tuple(w[i:i + 3]) for i in range(len(w) - 2)}


def _spread(scored: List[Tuple[float, int, Dict]]) -> List[Tuple[float, int, Dict]]:
    """At most one dated unit per day, and no near-duplicate of one already kept.

    SG1, measured 2026-11-07 on nomad-being's home: ranked by overlap and recency alone, the
    top four for dp's textstats question were all that day's restatements ("asked for
    details", "attempted to investigate"), which hold no details. A being that rewrites the
    same lesson many times a day crowds its own older work out of the ranking. One per day is
    a rule about spread over time, not a judgment of which entry matters."""
    out, days, seen = [], set(), []
    for s in scored:
        u = s[2]
        day = (u.get("date") or "")[:10]
        if day and day in days:
            continue
        sh = _shingles(u["text"])
        if sh and any(len(sh & x) / len(sh | x) > 0.5 for x in seen):
            continue
        out.append(s)
        if day:
            days.add(day)
        seen.append(sh)
    return out


def _kind(source: str) -> str:
    head = source.split("/", 1)[0]
    if head.startswith("journal"):
        return "journal"
    if head.startswith("todo"):
        return "todo"
    return head


def coverage(units: List[Dict]) -> Dict[str, int]:
    """How many units of each kind were searched (P6: absence is reported with its coverage)."""
    c: Dict[str, int] = {}
    for u in units:
        k = _kind(u["source"])
        c[k] = c.get(k, 0) + 1
    return c


def term_directory(units: List[Dict], query: str, max_terms: int = 3, min_units: int = 2) -> List[Dict]:
    """Per query word: how many units hold it, of which kinds, over what dates, and where it
    first appears. A low-resolution map of what exists (PRD P2), so the being can reach for
    more than the few snippets shown. Rarest-first among the words that matched enough."""
    rows = []
    unit_terms = [set(_terms(u["text"])) for u in units]
    for term in dict.fromkeys(_terms(query)):
        hits = [u for u, ts in zip(units, unit_terms) if term in ts]
        if len(hits) < min_units:
            continue
        dated = sorted((u for u in hits if u.get("date")), key=lambda u: u["date"])
        first = dated[0] if dated else hits[0]
        rows.append({"term": term, "count": len(hits), "kinds": coverage(hits),
                     "first_date": dated[0]["date"] if dated else "",
                     "last_date": dated[-1]["date"] if dated else "",
                     "first_source": first["source"], "first_seq": first.get("seq")})
    rows.sort(key=lambda r: r["count"])
    return rows[:max_terms]


def render(results: List[Dict], header: str = "From your own journal, todo and notes") -> str:
    if not results:
        return ""
    lines = [f"{header} ({len(results)} match{'es' if len(results) != 1 else ''}):"]
    for r in results:
        tag = _tag(r["source"], r.get("seq"), r["date"])
        lines.append(f"- [{tag}] {r['snippet']}")
    return "\n".join(lines)


def _tag(source: str, seq=None, date: str = "") -> str:
    return source + (f" seq {seq}" if seq is not None else "") + (f" @ {date}" if date else "")


def question_recall(instance: Path, turns: List[Dict], top_k: int = 4, snippet: int = 260) -> Dict:
    """Beat-start recall keyed on what was said to the being (SG1: the question is the page fault).

    `turns` are the pending turns, each {"cid", "seq", "from", "ts", "text"}. The words of
    those turns are the query; the turns themselves are excluded from their own results.
    Returns {"text", "query", "record"}: the block shown to the being, the query string (for
    long-term memory too), and what the beat records about it (source, the turns it came
    from, coverage, what was listed). The block names how it was found and what was searched,
    and says nothing about what to do with it: an affordance, not a decision (PRD §9a).

    Layout: matches, then the word directory, then what was searched. The beat's window fit
    keeps the TAIL of recall under pressure, so the low-resolution map survives longest."""
    query = " ".join(str(t.get("text") or "") for t in turns)
    who = ", ".join(dict.fromkeys(str(t.get("from")) for t in turns))
    newest = max(turns, key=lambda t: str(t.get("ts") or "")) if turns else {}
    when = str(newest.get("ts") or "")[:16].replace("T", " ")
    where = ", ".join(dict.fromkeys(f'"{t.get("cid")}"' for t in turns))
    record = {"source": "pending", "turns": [[t.get("cid"), t.get("seq")] for t in turns],
              "terms": sorted(set(_terms(query)))[:20]}
    try:
        units = index_home(instance)
    except Exception as e:
        record["error"] = f"{type(e).__name__}: {e}"[:200]
        return {"text": f"(searching your home for the words of what {who} said failed: "
                        f"{type(e).__name__})", "query": query, "record": record}
    exclude = {(f"conversations/{t.get('cid')}.jsonl", t.get("seq")) for t in turns}
    results = _rank(units, query, top_k, snippet, exclude=exclude, spread=True)
    rows = term_directory(units, query)
    cov = coverage(units)
    record.update({"coverage": cov,
                   "listed": [[r["source"], r.get("seq"), r["date"]] for r in results],
                   "directory": [[r["term"], r["count"]] for r in rows]})
    lines = []
    if results:
        lines.append(f"From your own home, by word overlap with what {who} said in {where} at {when} "
                     f"(at most one entry per day; not judged for relevance):")
        for r in results:
            lines.append(f"- [{_tag(r['source'], r.get('seq'), r['date'])}] {r['snippet']}")
    else:
        lines.append(f"No entry in your home shares a word with what {who} said in {where} at {when}.")
    if rows:
        lines.append("Where those words appear in your home:")
        for r in rows:
            kinds = ", ".join(f"{k} {n}" for k, n in sorted(r["kinds"].items(), key=lambda kv: -kv[1]))
            span = f", {r['first_date'][:10]} to {r['last_date'][:10]}" if r["first_date"] else ""
            lines.append(f'- "{r["term"]}": {r["count"]} entries ({kinds}){span}; first at '
                         f'{_tag(r["first_source"], r["first_seq"], r["first_date"])}')
    lines.append("Searched " + str(sum(cov.values())) + " entries: "
                 + ", ".join(f"{k} {n}" for k, n in sorted(cov.items(), key=lambda kv: -kv[1])) + ".")
    return {"text": "\n".join(lines), "query": query, "record": record}
