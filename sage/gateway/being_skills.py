"""Skills: procedures a being can find when the situation calls for them, and write for itself.

dp, 2026-10-27: "consider that we need a 'skills' structure, and membot-type index for them, i.e. what skills
might be applicable in the given situation? model it on your own skills in claude-code."

THE MODEL (Claude Code's skills). A skill is a directory holding SKILL.md: a short header naming it and saying
what it is for and when it applies, then the procedure. The session sees every skill's one-line description
all the time and loads a skill's body only when it is used, so knowing that a procedure exists costs a line,
and following it costs only when it is needed.

HERE:
- **Two places.** Fleet skills ship with SAGE (sage/gateway/skills/<name>/SKILL.md): written by seats, reviewed
  like code, read-only to a being. Its own live in its home (skills/<name>/SKILL.md), written only through the
  `skill` verb, which keeps every earlier version in skills_log.jsonl (being_self's rules). A being cannot
  take a fleet skill's name: its own sit beside the fleet's, never in front of them.
- **The header.** `name`, `description` (what it is for, one or two sentences) and optional `when`: words or
  phrases that show up in the being's state when the skill applies (a refusal's rule, a receipt's line, a
  verb's name). `when` is what a small window needs that a large one does not: a mechanical match, instead of
  asking the model to weigh every description every beat.
- **The index (the "membot-type index").** Every beat lists the skills compactly, the ones whose `when`
  words appear in this beat's state first, marked. Over the budget, the matching ones and a count. Matching is
  mechanical and hermetic, as `recall` is (relevance / home_recall terms): no model, no embedding, no
  membot session. The being's membot cartridge is one mounted session whose save overwrites the file; a second
  cartridge for skills would put its memory at risk for an index this size. `match()` is the one place a
  different ranker would go if this one is measured to miss.
- **The verb.** `skill` with no arguments lists them all; `name` reads one; `query` searches all of them,
  bodies included; `name` + `description` + `body` writes one of the being's own.

Nothing here makes a being follow a skill. The index says what exists and what matched; reading and following
are its acts.
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FLEET_DIR = Path(__file__).resolve().parent / "skills"
OWN_DIR = "skills"
SKILL_FILE = "SKILL.md"
SKILLS_LOG = "skills_log.jsonl"
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
DESCRIPTION_MAX_CHARS = 300
WHEN_MAX_CHARS = 300
BODY_MAX_CHARS = 6000
WHY_MAX_CHARS = 300
#: The beat's block: every skill while it fits, else the matching ones and a count.
INDEX_CHARS = 1400
INDEX_DESC_CHARS = 140
#: `query` returns at most this many.
QUERY_TOP = 5

_UNCHANGED = "unchanged: "


def parse(text: str) -> Tuple[Dict[str, str], str]:
    """(header, body) of a SKILL.md: a header between `---` lines of `key: value`, then the body. A file
    without a header is all body, with no description."""
    meta: Dict[str, str] = {}
    t = (text or "").lstrip("﻿")
    if t.startswith("---"):
        end = t.find("\n---", 3)
        if end != -1:
            for line in t[3:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip()
            nl = t.find("\n", end + 4)
            return meta, (t[nl + 1:] if nl != -1 else "").strip()
    return meta, t.strip()


def _when(meta: Dict[str, str]) -> List[str]:
    return [w.strip().lower() for w in re.split(r"[,;]", meta.get("when", "")) if len(w.strip()) >= 2]


def _load(d: Path, source: str) -> List[dict]:
    out = []
    if not d.is_dir():
        return out
    for sub in sorted(d.iterdir()):
        f = sub / SKILL_FILE
        if not (sub.is_dir() and NAME.match(sub.name) and f.is_file()):
            continue
        try:
            meta, body = parse(f.read_text(errors="replace"))
        except OSError:
            continue
        out.append({"name": sub.name, "description": meta.get("description", ""), "when": _when(meta),
                    "source": source, "body": body, "path": f})
    return out


def index(instance) -> List[dict]:
    """Every skill: the fleet's, then the being's own. A being's skill with a fleet skill's name is skipped
    (the verb refuses to write one; a hand-placed one does not shadow the reviewed text)."""
    fleet = _load(FLEET_DIR, "fleet")
    taken = {s["name"] for s in fleet}
    own = [s for s in _load(Path(instance) / OWN_DIR, "yours") if s["name"] not in taken]
    return fleet + own


def _pattern(w: str) -> str:
    """An edge of the word that is itself punctuation needs no boundary, so a prefix such as `scope-` matches
    the `scope-<id>` a refusal prints; a word that starts with `/` is a path and matches what extends it, so
    `/dev/video` matches `/dev/video0` (cbp review of #576)."""
    head = r"(?<![a-z0-9])" if w[:1].isalnum() else ""
    tail = r"(?![a-z0-9])" if w[-1:].isalnum() and not w.startswith("/") else ""
    return head + re.escape(w) + tail


def match(skills: List[dict], situation: str) -> List[Tuple[int, dict, List[str]]]:
    """[(hits, skill, the `when` words found)] for every skill with at least one `when` word in the situation,
    most hits first. Whole-word, case-insensitive."""
    low = (situation or "").lower()
    out = []
    for s in skills:
        found = [w for w in s["when"] if re.search(_pattern(w), low)]
        if found:
            out.append((len(found), s, found))
    out.sort(key=lambda x: -x[0])
    return out


def _entry(s: dict, found: Optional[List[str]] = None) -> str:
    d = s["description"] or "(no description)"
    if len(d) > INDEX_DESC_CHARS:
        d = d[:INDEX_DESC_CHARS - 1].rstrip() + "…"
    mine = " (yours)" if s["source"] == "yours" else ""
    hit = f"  <- matches now: {', '.join(found[:3])}" if found else ""
    return f"- {s['name']}{mine}: {d}{hit}"


def render(instance, situation: str) -> str:
    """The beat's block. Empty when there are no skills at all."""
    skills = index(instance)
    if not skills:
        return ""
    hits = match(skills, situation)
    hit_names = {s["name"] for _, s, _ in hits}
    head = (f"## Skills ({len(skills)}): procedures you can read with skill name=<name>; skill with no "
            "arguments lists them all, query searches them. Yours are written with skill too.")
    lines = [_entry(s, f) for _, s, f in hits] + [_entry(s) for s in skills if s["name"] not in hit_names]
    shown, used = [], len(head)
    for i, ln in enumerate(lines):
        if used + len(ln) + 1 > INDEX_CHARS and shown:
            rest = len(lines) - i
            shown.append(f"- … {rest} more (skill with no arguments lists them all)")
            break
        shown.append(ln)
        used += len(ln) + 1
    return head + "\n" + "\n".join(shown)


def listing(instance) -> str:
    skills = index(instance)
    if not skills:
        return "There are no skills yet. To write one of your own, give name, description and body."
    return (f"Skills ({len(skills)}). Read one with name; search them with query.\n"
            + "\n".join(_entry(s) + (f" [when: {', '.join(s['when'])}]" if s["when"] else "") for s in skills))


def read(instance, name: str) -> Tuple[bool, str]:
    s = next((x for x in index(instance) if x["name"] == name), None)
    if s is None:
        names = ", ".join(x["name"] for x in index(instance)) or "none yet"
        return False, f"there is no skill called {name!r}. Skills: {names}."
    where = "a fleet skill (shipped with SAGE; read-only)" if s["source"] == "fleet" else "your own skill"
    return True, (f"skill {s['name']}, {where}\ndescription: {s['description']}\n"
                  + (f"when: {', '.join(s['when'])}\n" if s["when"] else "") + "\n" + s["body"])


def search(instance, query: str) -> str:
    from sage.gateway.relevance import Ranker
    skills = index(instance)
    if not skills:
        return "There are no skills yet."
    rk = Ranker([f"{s['name']} {s['description']} {' '.join(s['when'])} {s['body']}" for s in skills])
    ranked = rk.related(query, threshold=0.05)[:QUERY_TOP]
    if not ranked:
        return f"no skill matches {query!r}. skill with no arguments lists them all."
    return (f"Skills matching {query!r}, best first:\n"
            + "\n".join(_entry(skills[i]) for _, i in ranked))


def skill(instance, args: Dict) -> Tuple[bool, str, bool]:
    """The verb. Returns (ok, message for the being, changed)."""
    a = {k: ("" if v is None else str(v).strip()) for k, v in (args or {}).items()}
    name = a.get("name", "").lower()
    writing = bool(a.get("body") or a.get("description"))
    if not name and a.get("query"):
        return True, search(instance, a["query"]), False
    if not name:
        return True, listing(instance), False
    if _truthy(a.get("retire", "")):
        with _home_lock(Path(instance)):
            ok, msg = _retire(instance, name, a.get("why", ""))
        return ok, msg, ok
    if not writing:
        ok, text = read(instance, name)
        return ok, text, False
    with _home_lock(Path(instance)):
        ok, msg = _write(instance, name, a)
    return ok, msg, bool(ok and not msg.startswith(_UNCHANGED))


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("true", "yes", "1")


def _retire(instance, name: str, why: str) -> Tuple[bool, str]:
    """Take one of the being's own skills out of its index (dp, 2026-10-28: "does it have ways to update or
    remove skills?"; it could replace one, never remove one). The whole text goes into skills_log.jsonl
    FIRST, so nothing is lost, and only a logged retirement removes the file: if the log line cannot be
    written, the skill stays. Writing the same name later starts a new skill."""
    if not NAME.match(name):
        return False, f"{name!r} is not a skill name. Nothing was changed."
    if any(s["name"] == name for s in _load(FLEET_DIR, "fleet")):
        return False, (f"{name!r} is a fleet skill (shipped with SAGE, read-only), so it is not yours to retire. "
                       "Nothing was changed. If it is wrong, say so to your seat.")
    d = Path(instance) / OWN_DIR / name
    path = d / SKILL_FILE
    if not path.is_file():
        mine = [s["name"] for s in _load(Path(instance) / OWN_DIR, "yours")]
        return False, (f"you have no skill called {name!r}; yours are: {', '.join(mine) or 'none yet'}. "
                       "Nothing was changed.")
    prev = path.read_text(errors="replace")
    try:
        lp = Path(instance) / SKILLS_LOG
        torn = False
        if lp.exists() and lp.stat().st_size > 0:
            with open(lp, "rb") as lf:
                lf.seek(-1, os.SEEK_END)
                torn = lf.read(1) != b"\n"
        with open(lp, "a") as f:
            f.write(("\n" if torn else "") + json.dumps({"at": _iso(), "op": "retire", "name": name, "from": prev,
                                                         "to": None, "why": str(why)[:WHY_MAX_CHARS]}) + "\n")
    except OSError as e:
        return False, f"the retirement could not be recorded in {SKILLS_LOG} ({type(e).__name__}), so the skill stays; nothing changed"
    try:
        path.unlink()
        try:
            d.rmdir()
        except OSError:
            pass                # other files of the being's own in that directory stay where they are
    except OSError as e:
        return False, (f"retirement of {name} was recorded but the file could not be removed ({type(e).__name__}); "
                       "it is still listed. Tell your seat.")
    return True, (f"retired your skill {name}: it is no longer listed or matched. Its whole text is kept in "
                  f"{SKILLS_LOG}. Writing a skill with that name again starts a new one.")


def _home_lock(root: Path):
    from sage.gateway.reference_f1a import _home_lock as lock
    return lock(root)


def own_paths(name: str) -> Tuple[str, ...]:
    """Every path (relative to the home) a write or a retire of skill `name` touches, for the gate: the skill's
    directory too, which a first write creates and a retire removes."""
    return (f"{OWN_DIR}/{name}", f"{OWN_DIR}/{name}/{SKILL_FILE}.tmp", f"{OWN_DIR}/{name}/{SKILL_FILE}", SKILLS_LOG)


def _write(instance, name: str, a: Dict[str, str]) -> Tuple[bool, str]:
    if not NAME.match(name):
        return False, ("a skill's name is 2-40 characters of lowercase letters, digits and dashes, starting "
                       f"with a letter or digit (e.g. reading-a-refusal); {name!r} is not. Nothing was changed.")
    if any(s["name"] == name for s in _load(FLEET_DIR, "fleet")):
        return False, (f"{name!r} is a fleet skill (shipped with SAGE, read-only). Give yours a name of its "
                       "own. Nothing was changed.")
    description, body, when = a.get("description", ""), a.get("body", ""), a.get("when", "")
    if not description or not body:
        return False, ("a skill needs a description (what it is for and when it applies, in a sentence or "
                       "two) and a body (the procedure). Nothing was changed.")
    for field, val, cap in (("description", description, DESCRIPTION_MAX_CHARS), ("when", when, WHEN_MAX_CHARS),
                            ("body", body, BODY_MAX_CHARS)):
        if len(val) > cap:
            return False, f"{field} holds at most {cap} characters; this is {len(val)}. Nothing was changed."
    if "\n---" in description or "\n" in description or "\n" in when:
        return False, "description and when are one line each. Nothing was changed."
    text = f"---\nname: {name}\ndescription: {description}\n" + (f"when: {when}\n" if when else "") + f"---\n\n{body}\n"
    d = Path(instance) / OWN_DIR / name
    path, tmp = d / SKILL_FILE, d / (SKILL_FILE + ".tmp")
    prev = path.read_text(errors="replace") if path.exists() else None
    if prev == text:
        return True, f"{_UNCHANGED}your skill {name} already reads exactly that; nothing changed."
    try:
        d.mkdir(parents=True, exist_ok=True)
        tmp.write_text(text)
        os.replace(tmp, path)
    except OSError as e:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return False, f"could not write skills/{name}/{SKILL_FILE} ({type(e).__name__}); nothing changed"
    try:
        lp = Path(instance) / SKILLS_LOG
        torn = False
        if lp.exists() and lp.stat().st_size > 0:
            with open(lp, "rb") as lf:
                lf.seek(-1, os.SEEK_END)
                torn = lf.read(1) != b"\n"
        with open(lp, "a") as f:
            f.write(("\n" if torn else "") + json.dumps({"at": _iso(), "name": name, "from": prev, "to": text,
                                                         "why": a.get("why", "")[:WHY_MAX_CHARS]}) + "\n")
    except OSError as e:
        try:
            if prev is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(prev)
        except OSError as e2:
            return False, (f"skill {name} was written but could not be recorded in {SKILLS_LOG} "
                           f"({type(e).__name__}) and could not be undone ({type(e2).__name__}). Tell your seat.")
        return False, f"the change could not be recorded in {SKILLS_LOG} ({type(e).__name__}), so it was undone; nothing changed"
    verb = "replaced" if prev is not None else "wrote"
    return True, (f"{verb} your skill {name}" + (" (the earlier version is kept in skills_log.jsonl)" if prev else "")
                  + ". It is listed in every beat's skills, and shown first when its when-words appear.")


def _iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# -- the moment a skill forms: something that failed, then worked, in one beat ---------------------------------

#: Verbs where "failed, then worked" is measurable from the act's own result, and what names the target.
#: Not request_run: its ok=True means the request was FILED, and nothing has run yet (#585 reviews).
WORKED_OUT_VERBS = {"run": "path", "memory_edit": "path", "camera": None, "patch_apply": None}
#: A retried edit of its own records is bookkeeping, not a procedure (replayed on Sprout: `memory_edit todo.md`).
BOOKKEEPING = ("todo.md", "journal.md")


def _failed(effector: str, env) -> Optional[bool]:
    """True/False for an act whose outcome the result states; None when it does not say."""
    if env is None:
        return None
    if not getattr(env, "ok", False):
        return True
    if effector == "run":
        r = getattr(env, "result", None)
        code = r.get("exit") if isinstance(r, dict) else None
        return None if code is None else code != 0
    return False


def worked_out(trace) -> Optional[str]:
    """One line of fact for the reflect turn when this beat holds an act that FAILED and then, on the same
    target, WORKED: the moment a procedure was found, and the only moment its steps are all in view.
    dp, 2026-10-28: "once it figures something out, to retain it as a skill for future use". None otherwise.
    It names what happened and that `skill` can keep it; whether to write one, and what, is the being's."""
    seen: Dict[tuple, List[bool]] = {}
    found: Dict[tuple, tuple] = {}                                 # per target; the latest worked-out one is told
    for item in trace or []:
        try:
            intent, env = item
        except (TypeError, ValueError):
            continue
        eff = getattr(intent, "effector", None)
        if eff not in WORKED_OUT_VERBS:
            continue
        arg = WORKED_OUT_VERBS[eff]
        target = str((getattr(intent, "args", None) or {}).get(arg) or "") if arg else ""
        target = posixpath.normpath(target) if target else ""   # `./a.py` and `a.py` are one target
        if target.rsplit("/", 1)[-1] in BOOKKEEPING:
            continue
        f = _failed(eff, env)
        if f is None:
            continue
        key = (eff, target)
        hist = seen.setdefault(key, [])
        if not f and hist and any(hist):
            found.pop(key, None)
            found[key] = (eff, target, sum(hist), len(hist) + 1)
        if f:
            hist.append(f)
            found.pop(key, None)                                   # it broke again: its last outcome is a failure
        else:
            hist.clear()                                           # a success ends a struggle; count the last one
    if not found:
        return None
    eff, target, fails, tries = list(found.values())[-1]
    what = f"{eff} {target}".strip()
    return (f"This beat, `{what}` failed {fails} time{'s' if fails != 1 else ''} and then worked, on try {tries}. "
            "If you want the steps that got it working kept for next time, `skill` can hold them as a skill of "
            "your own (name, description, when, body).")
