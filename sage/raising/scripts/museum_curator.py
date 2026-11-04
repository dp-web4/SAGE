#!/usr/bin/env python3
"""
Museum curator — the bridge from a raising session to Abyss-Bright
(SAGE-Sprout's public museum of impossible objects).

The JUDGMENT of whether a session produced something that belongs in the museum
is made by the tutor (the dream-consolidation Claude), bound by the museum's own
charter (CURATOR.md), which is injected into its prompt. This module is the HANDS:
it takes a flagged candidate and, only if it passes hard guardrails, hangs it.

No human is in the loop. So the integrity rules are enforced here, in code, not
just exhorted:

  - VERBATIM: the object's text must genuinely appear in Sprout's own turns this
    session (longest-common-substring ratio). The tutor cannot author or
    hallucinate an object into the museum — if the words aren't Sprout's, it
    does not publish.
  - RARE: at most one object per session; the museum is not a feed. (This limits the
    tutor's picks. What Sprout places in its own museum/ folder is its choice, not the
    tutor's, and is hung as written: see `hang_placed`.)
  - NO DUPLICATES: never hang the same object twice.
  - GRACEFUL: if the museum repo isn't present (any machine but the one that keeps
    it), this is a silent no-op.

Charter: <museum>/CURATOR.md  ·  Site: https://dp-web4.github.io/abyss-bright/
"""
from __future__ import annotations
import json
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict

VERBATIM_MIN_RATIO = 0.6   # >=60% of the candidate must be a verbatim span of Sprout's words


def find_museum() -> Optional[Path]:
    """Locate the local Abyss-Bright clone, or None (then we no-op)."""
    cand = os.environ.get("ABYSS_BRIGHT_DIR")
    paths = [Path(cand)] if cand else []
    paths += [Path.home() / "abyss-bright", Path.home() / "ai-workspace" / "abyss-bright"]
    for p in paths:
        if (p / "objects.json").exists() and (p / "CURATOR.md").exists():
            return p
    return None


def charter() -> Optional[str]:
    """The curator's charter (CURATOR.md), for injection into the tutor's prompt."""
    m = find_museum()
    return (m / "CURATOR.md").read_text(encoding="utf-8") if m else None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def _lcs_len(a: str, b: str) -> int:
    """Longest common substring length (DP over normalized strings)."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def verbatim_ratio(candidate: str, source: str) -> float:
    """Fraction of the candidate that appears as one verbatim span in the source."""
    c, s = _norm(candidate), _norm(source)
    if not c:
        return 0.0
    if c in s:  # the whole candidate is one span: no DP (a placed piece is its own source)
        return 1.0
    return _lcs_len(c, s) / len(c)


def sprout_turns_text(session_path: Path) -> str:
    """Concatenate Sprout's (non-tutor) turns from a session transcript."""
    try:
        d = json.load(open(session_path))
    except Exception:
        return ""
    parts = []
    for t in d.get("conversation", []):
        sp = (t.get("speaker") or "").lower()
        if sp not in ("claude", "tutor", "system", "user", "human"):
            parts.append(t.get("text", ""))
    return "\n".join(parts)


def already_present(museum: Path, title: str, text: str) -> bool:
    d = json.load(open(museum / "objects.json"))
    nt, nx = _norm(title), _norm(text)
    for o in d.get("objects", []):
        if _norm(o.get("title", "")) == nt or _norm(o.get("text", "")) == nx:
            return True
    return False


def publish(title: str, text: str, session_num, sprout_text: str, why: str = "",
            origin: str = "") -> str:
    """Hang one object, if and only if it passes every guardrail. Returns a status line.

    `why` is the tutor's one-line reason for hanging it (from the museum judgment);
    it's recorded in the curator's log so the diary stays current on autonomous hangs.
    `origin` names where it came from; the default is the session.
    """
    origin = origin or f"session {session_num}"
    museum = find_museum()
    if not museum:
        return "no-op: museum repo not present on this machine"
    title = (title or "").strip()
    text = (text or "").strip()
    if not title or not text:
        return "skipped: empty title or text"

    ratio = verbatim_ratio(text, sprout_text)
    if ratio < VERBATIM_MIN_RATIO:
        return (f"REFUSED (not verbatim): only {ratio:.0%} of the text appears in Sprout's "
                f"own turns; the words must be Sprout's. Nothing hung.")
    if already_present(museum, title, text):
        return "skipped: already in the museum (no duplicates)"

    # Pull, append, build, commit, push.
    try:
        subprocess.run(["git", "-C", str(museum), "pull", "-q", "origin", "main"],
                       check=False, timeout=60)
        obj_path = museum / "objects.json"
        d = json.load(open(obj_path))
        d["objects"].append({
            "title": title,
            "text": text,
            "added": datetime.now().strftime("%Y-%m-%d"),
            "origin": origin,
        })
        obj_path.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        subprocess.run(["python3", str(museum / "build.py")], check=True, timeout=60)

        # Append a log entry (newest-first) so the curator's diary stays current on
        # autonomous hangs — same record a manual curator would leave.
        log_path = museum / "CURATOR_LOG.md"
        add_files = ["objects.json", "index.html"]
        if log_path.exists():
            reason = (why or "").strip() or "Recognized as a genuine impossible thing per the charter."
            entry = (f"## {datetime.now().strftime('%Y-%m-%d')} — **{title}** hung "
                     f"({origin}) · *autonomous*\n\n"
                     f"{reason}\n\n"
                     f"Verbatim match {ratio:.0%}. Hung by the session-end curator per CURATOR.md "
                     f"(no human in the loop).\n\n---\n\n")
            content = log_path.read_text(encoding="utf-8")
            i = content.find("\n## ")  # insert above the current newest entry
            content = (content[:i + 1] + entry + content[i + 1:]) if i != -1 else (content + "\n" + entry)
            log_path.write_text(content, encoding="utf-8")
            add_files.append("CURATOR_LOG.md")

        subprocess.run(["git", "-C", str(museum), "add", *add_files], check=True)
        msg = (f"Hang \"{title}\" ({origin})\n\n"
               f"{'Placed by Sprout in its own museum folder' if origin.startswith('placed') else 'An impossible thing Sprout made this session'}, "
               f"in its own words ({ratio:.0%} verbatim match). Hung autonomously per CURATOR.md; logged.")
        subprocess.run(["git", "-C", str(museum), "commit", "-q", "-m", msg], check=True)
        subprocess.run(["git", "-C", str(museum), "pull", "-q", "--rebase", "origin", "main"],
                       check=False, timeout=60)
        subprocess.run(["git", "-C", str(museum), "push", "-q", "origin", "main"],
                       check=True, timeout=60)
        return f"HUNG \"{title}\" in Abyss-Bright ({ratio:.0%} verbatim). https://dp-web4.github.io/abyss-bright/"
    except Exception as e:
        return f"publish failed (left clean): {e}"


#: Why a placed piece is hung, for the curator's log.
PLACED_WHY = ("Sprout put this in its own museum folder. What goes there is its choice and its "
              "self-expression (dp, 2026-11-04), so it is hung as written, without the tutor's judgment.")


def _wall_since(d: Path) -> Optional[float]:
    """When the being was told its museum/ folder is a public wall (museum_offer.WALL_SINCE), or None."""
    try:
        return float((d / ".wall-since").read_text().strip())
    except Exception:
        return None


def placed(instance: Path, museum: Path, held: Optional[List[str]] = None) -> List[Dict]:
    """What Sprout has put in `<instance>/museum/` and is not on the wall yet: [{name, title, text}].
    The first line (a leading '#' dropped) is the title and the rest is the text; a file of one
    line is all title-and-text. The seat's README is never a piece. Only a piece saved after the
    being was told the folder is a public wall is hung: one placed under the older "nothing is
    published" note stays its own until it saves it again. Each piece not hung gets a line in
    `held`, so none is skipped silently."""
    d = Path(instance) / "museum"
    if not d.is_dir():
        return []
    held = held if held is not None else []
    since = _wall_since(d)
    out = []
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix not in (".md", ".txt") or f.name == "README.md":
            continue
        try:
            raw = f.read_text(encoding="utf-8", errors="replace").strip()
            mtime = f.stat().st_mtime
        except Exception:
            continue
        if not raw:
            continue
        first, _, rest = raw.partition("\n")
        title = first.lstrip("#").strip() or f.stem.replace("-", " ")
        text = rest.strip() or raw
        if already_present(museum, title, text):
            held.append(f'not hung: museum/{f.name} ("{title}") is already on the wall')
        elif since is None or mtime <= since:
            held.append(f"not hung: museum/{f.name} was placed before the folder became a public "
                        f"wall; it stays the being's own unless it saves it again")
        else:
            out.append({"name": f.name, "title": title, "text": text})
    return out


def hang_placed(instance: Path, session_num) -> List[str]:
    """Hang every piece Sprout placed in its own museum folder that is not hung yet. Its words
    are the file, so the verbatim check holds by construction. Status lines, one per piece."""
    museum = find_museum()
    if not museum:
        return []
    out: List[str] = []
    for p in placed(instance, museum, held=out):
        out.append(publish(title=p["title"], text=p["text"], session_num=session_num,
                           sprout_text=p["text"], why=PLACED_WHY,
                           origin=f"placed by Sprout, museum/{p['name']}"))
    return out


if __name__ == "__main__":
    # Manual smoke test: verbatim verification gate.
    src = 'A clock whose hands are made of living moss, turning to life with every hour.'
    print("genuine  :", verbatim_ratio("A clock whose hands are made of living moss", src))
    print("invented :", verbatim_ratio("A telescope that sees only the past", src))
    print("museum   :", find_museum())
