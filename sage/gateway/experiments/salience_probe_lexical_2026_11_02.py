"""Read-only lexical probe; retrieval overlap is not truth or evidence of recall quality.

Run from the repository root with ``python -m sage.gateway.experiments.
salience_probe_lexical_2026_11_02``. The default corpus is entirely synthetic.
An explicit --input JSON file may provide records and queries, each a list of
objects with a string ``text`` field. Only zero-based indices and scores are
printed, never input text or supplied identifiers. Explicit inputs still require
the caller to have authority to read them; this tool supplies no access control.
Indices and scores are derived from the input and are not automatically safe to
share, even though the tool does not print the source text.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from sage.gateway.relevance import Ranker

SYNTHETIC_FIXTURE = Path(__file__).with_name("salience_probe_synthetic_2026_11_02.json")
MAX_INPUT_BYTES = 1024 * 1024
MAX_COMPARISONS = 100_000


def _texts(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, dict) and isinstance(item.get("text"), str) for item in value
    ):
        raise ValueError("records and queries must be lists of objects with string text")
    return [item["text"] for item in value]


def probe(payload: Any, threshold: float = 0.2, limit: int = 8) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("input must be an object")
    if not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be finite and between 0 and 1")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
    records = _texts(payload.get("records"))
    queries = _texts(payload.get("queries"))
    if len(records) * len(queries) > MAX_COMPARISONS:
        raise ValueError("too many query/record comparisons")
    ranker = Ranker(records)
    results = []
    for query_index, query in enumerate(queries):
        hits = ranker.related(query, threshold=threshold)
        results.append({
            "query_index": query_index,
            "total_hits": len(hits),
            "hits": [{"record_index": i, "score": round(score, 6)}
                     for score, i in hits[:limit]],
        })
    return {"record_count": len(records), "query_count": len(queries), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=SYNTHETIC_FIXTURE,
                        help="explicit authorized JSON input; default is the synthetic fixture")
    parser.add_argument("--threshold", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    try:
        with args.input.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("input exceeds the size limit")
        result = probe(json.loads(raw), args.threshold, args.limit)
    except (OSError, ValueError, UnicodeError, RecursionError):
        # Do not echo input paths, record text, identifiers or parse fragments.
        parser.exit(2, "Unable to read or validate probe input.\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
