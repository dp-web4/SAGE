"""What in the being's own record is ABOUT the same thing as what it is doing now. Mechanical, no model.

Two keys, in order:
- **The same named thing.** A device node or a scope request id named in both texts. These are exact, and
  they are what a goal circles: measured on Sprout 2026-10-14..27, 1,192 journal lines and most request_runs
  named /dev/video0.
- **Otherwise, the same words.** Term overlap weighted by how rare each term is in the collection searched
  (idf), divided by the smaller text's total weight, so a short request is not drowned by a long one. Tuned
  on Sprout's 1,010 request_runs: at 0.3 a camera-device request matched 10-14 earlier ones, all about the
  device; at 0.2, 43-74, with unrelated ones mixed in.

Terms come from home_recall, so `recall` and this agree on what a word is. Read-only, hermetic.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, List, Sequence, Set, Tuple

from sage.gateway.home_recall import _terms

_IDS = re.compile(r"scope-[0-9a-f]{12}|/dev/[A-Za-z]+\d*", re.I)
#: The word-overlap bar (see the module docstring for how it was set).
WORD_THRESHOLD = 0.3


#: Not named things: plumbing nearly every script mentions (`2>/dev/null`). Counting them made any two
#: scripts "the same subject" at full score (legion's review of #574).
PSEUDO_DEVICES = frozenset(f"/dev/{n}" for n in (
    "null", "zero", "full", "random", "urandom", "stdin", "stdout", "stderr", "tty", "shm", "fd", "pts", "ptmx"))


def ids(text: str) -> Set[str]:
    """Exact named things in a text: device nodes and scope request ids, lowercased."""
    return {m.group(0).lower() for m in _IDS.finditer(text or "")} - PSEUDO_DEVICES


class Ranker:
    """Scores a query against a fixed collection of texts."""

    def __init__(self, texts: Sequence[str]):
        self.texts = list(texts)
        self.terms = [set(_terms(t)) for t in self.texts]
        self.ids = [ids(t) for t in self.texts]
        df = Counter(t for d in self.terms for t in d)
        n = len(self.terms)
        self._idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
        self._n = n

    def idf(self, t: str) -> float:
        return self._idf.get(t, math.log(self._n + 1.5))

    def score(self, query: str, i: int) -> Tuple[float, Set[str]]:
        """(score, the named things shared). A shared named thing scores 1.0; otherwise idf overlap."""
        q_ids = ids(query)
        shared_ids = q_ids & self.ids[i]
        if shared_ids:
            return 1.0, shared_ids
        q = set(_terms(query))
        d = self.terms[i]
        shared = q & d
        if not shared:
            return 0.0, set()
        num = sum(self.idf(t) for t in shared)
        den = min(sum(self.idf(t) for t in q), sum(self.idf(t) for t in d)) or 1.0
        return num / den, set()

    def related(self, query: str, threshold: float = WORD_THRESHOLD,
                among: Iterable[int] = None) -> List[Tuple[float, int]]:
        """[(score, index)] at or over the threshold, best first, later index first on ties."""
        idx = range(len(self.texts)) if among is None else among
        out = [(s, i) for i in idx for s in (self.score(query, i)[0],) if s >= threshold]
        out.sort(key=lambda x: (-x[0], -x[1]))
        return out


# -- request_run: the earlier asks on the same subject ------------------------------------------------------

#: How far back a subject is looked for: two weeks of a busy being's requests.
EARLIER_LOOKBACK_TURNS = 3000


def earlier_requests(turns: Sequence[dict], member: str, query: str,
                     threshold: float = WORD_THRESHOLD) -> List[dict]:
    """The being's earlier request_runs on the same subject as `query` (its new request's path, why and
    the named things in its file), oldest first, each with the seat's answer if one names it:
    [{seq, ts, file, answer_seq, answer}] where answer is the answer's first line ('' if unanswered).

    `turns` is the seat conversation in order. Only the being's own requests are matched; the seat's
    answers are bound to them by the seq they name (conversations._ANSWER_NAMES), never by position."""
    from sage.gateway.conversations import _ANSWER_NAMES
    reqs, answers, by_file = [], {}, {}
    for t in turns:
        text = str(t.get("text", ""))
        if t.get("from") == member:
            if text.startswith("[request_run] "):
                # the head: path and why, without the dispatcher's own lines (size, sha, annotations)
                head = text.split("\n(", 1)[0]
                reqs.append({"seq": t.get("seq"), "ts": str(t.get("ts") or ""),
                             "file": head.split("\n", 1)[0][len("[request_run] "):].strip(), "head": head})
            continue
        first = text.strip().split("\n", 1)[0][:200]
        named = [int(n) for mm in _ANSWER_NAMES.finditer(text) for n in re.findall(r"\d+", mm.group(1))]
        for n in named:
            answers.setdefault(n, (t.get("seq"), first))
        if named:
            for r in reqs:
                if r["seq"] in named:
                    by_file.setdefault(r["file"], []).append((t.get("seq"), first))
    if not reqs:
        return []
    rk = Ranker([r["head"] for r in reqs])
    hit = sorted(i for _, i in rk.related(query, threshold))
    out = []
    for i in hit:
        r = reqs[i]
        a = answers.get(int(r["seq"])) if isinstance(r["seq"], int) else None
        if a is None and isinstance(r["seq"], int):
            # THE SEAT ANSWERS A REPEATED REQUEST ONCE, naming one seq of it (seat_run_requests); the
            # copies are answered by that answer. Bound to the next answer for the same file after it.
            a = next((x for x in by_file.get(r["file"], ()) if isinstance(x[0], int) and x[0] > r["seq"]), None)
        out.append({"seq": r["seq"], "ts": r["ts"], "file": r["file"],
                    "answer_seq": a[0] if a else None, "answer": a[1] if a else ""})
    return out


def earlier_requests_said(found: List[dict], shown: int = 3) -> str:
    """One paragraph for the receipt: how many, since when, how they were answered, and the latest few."""
    if not found:
        return ""
    ran = sum(1 for f in found if f["answer"].startswith("[request_run] I ran"))
    declined = sum(1 for f in found if f["answer"].startswith("[request_run] I did not run"))
    other = sum(1 for f in found if f["answer"]) - ran - declined
    waiting = sum(1 for f in found if not f["answer"])
    tally = ", ".join(p for p in (f"the seat ran {ran}" if ran else "",
                                  f"declined {declined}" if declined else "",
                                  f"answered {other} in words" if other else "",
                                  f"{waiting} not answered" if waiting else "") if p)
    files = len({f["file"] for f in found})
    lines = [f"You have asked the seat about this same subject {len(found)} time"
             f"{'s' if len(found) != 1 else ''} before, since {found[0]['ts'][:10] or 'earlier'}, "
             f"with {files} different file{'s' if files != 1 else ''} ({tally}). The latest:"]
    for f in found[-shown:]:
        said = f["answer"] or "(not answered yet)"
        lines.append(f"- seq {f['seq']} ({f['file']}): " + (f"seq {f['answer_seq']}: " if f["answer_seq"] else "")
                     + said)
    return "\n".join(lines)
