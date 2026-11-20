"""SAGE#686: beat-start recall's `_spread` is bounded by what is shown, and shows exactly the same.

cbp-being, 2026-11-08..10: a pending turn whose words were mostly short numbers scored nearly
all of a ~30k-unit home, and `_spread` compared each unit's shingles against every unit placed
before it — ~19 CPU-minutes before the first model call, every beat. `_rank` only shows the first
`top_k` of the ordering, so `_spread(limit=k)` must equal `_spread()[:k]` while doing O(n*k)
comparisons. Hermetic: synthetic units only, no home, no model."""
import os
import random
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import home_recall as hr  # noqa: E402

WORDS = "camera light room motor sensor door table window floor lamp wall chair desk shelf".split()


def _scored(rng: random.Random, n: int):
    units, base = [], [" ".join(rng.choice(WORDS) for _ in range(12)) for _ in range(6)]
    for i in range(n):
        if rng.random() < 0.4:
            text = rng.choice(base) + " " + rng.choice(WORDS)            # a near-duplicate
        else:
            text = " ".join(rng.choice(WORDS) for _ in range(rng.randint(2, 14)))
        day = rng.choice(["2026-11-08", "2026-11-09", "2026-11-10", ""])
        units.append({"source": rng.choice(["journal.md", "todo.md", "conversations/dp.jsonl"]),
                      "date": f"{day} 0{rng.randint(0, 9)}:00" if day else "", "text": text})
    scored = [(float(rng.randint(10, 60)), i, u) for i, u in enumerate(units)]
    scored.sort(key=lambda s: (-s[0], -s[1]))
    return scored


def test_bounded_spread_is_exactly_the_shown_prefix_of_the_unbounded_one():
    rng = random.Random(686)
    for _ in range(200):
        scored = _scored(rng, rng.randint(0, 60))
        full = hr._spread(scored)
        for k in range(1, 7):
            assert hr._spread(scored, limit=k) == full[:k]


def test_rank_shows_the_same_entries_as_before():
    # The same _rank call with the pre-#686 (unbounded) spread, in the same process: snippet
    # centring iterates a set of query terms, so outputs are only comparable within one process.
    rng = random.Random(14276)
    units = [u for _, _, u in _scored(rng, 300)]
    bounded = hr._spread
    for q in ("camera light", "door window floor", "motor"):
        for k in (1, 4, 6):
            got = hr._rank(units, q, k, 80, spread=True)
            hr._spread = lambda scored, limit=None: bounded(scored)
            try:
                want = hr._rank(units, q, k, 80, spread=True)
            finally:
                hr._spread = bounded
            assert got == want


class _Counting(set):
    calls = 0

    def __and__(self, other):
        _Counting.calls += 1
        return set.__and__(self, other)


def test_the_work_is_bounded_by_what_is_shown():
    # 3000 distinct units on one day and kind: all but the first are held, none near another.
    # Unbounded, every held unit joins `seen` and is compared with all before it (~4.5M).
    n = 3000
    scored = [(10.0, i, {"source": "journal.md", "date": "2026-11-10 01:00",
                         "text": f"entry w{i} x{i} y{i} z{i}"}) for i in range(n)]
    real = hr._shingles
    hr._shingles = lambda text: _Counting(real(text))
    try:
        _Counting.calls = 0
        hr._spread(scored, limit=4)
        assert _Counting.calls <= n * 4, _Counting.calls
    finally:
        hr._shingles = real
