"""Read-only historical closure audit for #464; never reopens or disposes work.

Run as `python3 -B -m sage.gateway.run_queue_audit --turns SNAPSHOT.jsonl
--home INSTANCE_ROOT --seat SEAT_ID`. Supply a frozen export, not a live log.
Output contains counts and sequence references, not conversation text or paths.
The default 400-turn window mirrors pending(); larger windows are historical
counterfactuals, not claims about the live queue. No model, network or execution.
"""
import argparse
from collections import Counter
import hashlib
import inspect
import json
import os
from pathlib import Path
import re

from sage.gateway import conversations as conv
from sage.scripts import seat_run_requests as srr

MAX_BYTES = 16 * 1024 * 1024
MAX_TURNS = 20000
MAX_WINDOW = 2000
_RESULT = re.compile(r"\[request_run\] I (?:ran|did not run) (\S+)")


def validate_turns(turns):
    if len(turns) > MAX_TURNS:
        raise ValueError("snapshot exceeds turn limit; provide a bounded frozen export")
    last = 0
    for row in turns:
        if not isinstance(row, dict) or type(row.get("seq")) is not int or row["seq"] <= last:
            raise ValueError("snapshot needs strictly increasing positive integer sequences")
        if not isinstance(row.get("from"), str) or not row["from"].strip() \
                or not isinstance(row.get("text"), str):
            raise ValueError("snapshot needs string speaker and text fields")
        last = row["seq"]


def read_snapshot(path):
    with Path(path).open("rb") as stream:
        stamp = os.fstat(stream.fileno())
        raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > MAX_BYTES:
        raise ValueError("snapshot exceeds byte limit; provide a bounded frozen export")
    if (stamp.st_size, stamp.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("snapshot changed while reading; freeze it before auditing")
    try:
        turns = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    except (UnicodeError, ValueError):
        raise ValueError("snapshot is not valid UTF-8 JSONL") from None
    validate_turns(turns)
    return turns, hashlib.sha256(raw).hexdigest()


def audit(turns, home, seat, window=400):
    """Compare current closure with an explicit-or-matching-evidence candidate.

    Legacy filename equivalence delegates to the production resolver using the
    supplied home as it exists NOW, not reconstructed historical symlinks. The
    current pending rule is mirrored below and parity-tested against production.
    Later explicit answers can provide binding even if the first closure was weak.
    None of these classifications assert success or authorize executing anything.
    """
    validate_turns(turns)
    if type(window) is not int or not 1 <= window <= MAX_WINDOW:
        raise ValueError("window must be between 1 and 2000")
    if not isinstance(seat, str) or not seat.strip():
        raise ValueError("seat must be explicit and nonempty")
    home = Path(home).resolve()
    if not home.is_dir():
        raise ValueError("home must be an existing directory for current path-resolution parity")
    visible = turns[-window:]
    counts = Counter({k: 0 for k in ("open", "explicit_answer", "matching_run", "legacy_only")})
    reasons = Counter()
    affected = []
    for index, row in enumerate(visible):
        # Deliberately the current pending() predicate, including legacy prose markers.
        if row["from"] == seat or srr.MARKER not in row["text"]:
            continue
        seq, path = row["seq"], srr.request_path(row)
        key = conv._request_key(row["text"])
        legacy = explicit = matched = None
        for response in visible[index + 1:]:
            if response["from"] != seat:
                continue
            text = response["text"]
            named = srr._named_seqs(text)
            if seq in named:
                explicit = explicit or response["seq"]
                legacy = legacy or response["seq"]
                continue
            if named and seq > max(named):
                continue
            first = text.splitlines()[0] if text else ""
            result = _RESULT.match(first)
            if result and srr._same_file(home, result.group(1).rstrip(".,;:"), path):
                legacy = legacy or response["seq"]
                if conv._run_result_matches_request(text, key):
                    matched = matched or response["seq"]
        category = ("explicit_answer" if explicit else "matching_run" if matched else
                    "legacy_only" if legacy else "open")
        counts[category] += 1
        if category == "legacy_only":
            reason = "unknown_request_identity" if key is None else "unbound_result_identity"
            reasons[reason] += 1
            affected.append({"request_seq": seq, "first_legacy_closer_seq": legacy, "reason": reason})
    return {
        "schema": "sage.run-queue-audit.v1",
        "mode": "read_only_no_dispositions",
        "window_kind": "runtime_tail" if window == 400 else "historical_counterfactual",
        "window_limit": window,
        "loaded_turns": len(turns),
        "analyzed_turns": len(visible),
        "prefix_turns_excluded": len(turns) - len(visible),
        "sequence_bounds": [visible[0]["seq"], visible[-1]["seq"]] if visible else [],
        "requests": sum(counts.values()),
        "categories": dict(counts),
        "legacy_pending": counts["open"],
        "candidate_unresolved": counts["open"] + counts["legacy_only"],
        "closed_without_candidate_binding": counts["legacy_only"],
        "legacy_only_reasons": dict(reasons),
        "affected_requests": affected,
        "pending_rule_sha256": hashlib.sha256(inspect.getsource(srr.pending).encode()).hexdigest(),
        "implementation_sha256": {
            name: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for name, path in (("audit", __file__), ("conversations", conv.__file__),
                               ("seat_run_requests", srr.__file__))
        },
        "caveats": [
            "Only the supplied snapshot window was examined; absent history is unknown.",
            "Path aliases use current home resolution; historical filesystem state is unknown.",
            "Candidate matching keeps literal request paths; aliases can remain unproven.",
            "Categories are exclusive: explicit_answer takes precedence; matching_run counts only requests without an explicit answer.",
            "Explicit answer is not execution or success; matching run is not success or reusable input state.",
            "Legacy-only closure needs review or labelled disposition, not automatic reopening.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", required=True, type=Path)
    parser.add_argument("--home", required=True, type=Path)
    parser.add_argument("--seat", required=True)
    parser.add_argument("--window", type=int, default=400)
    args = parser.parse_args(argv)
    try:
        turns, digest = read_snapshot(args.turns)
        report = audit(turns, args.home, args.seat, args.window)
    except (ValueError, OSError) as exc:
        # Do not echo an input path, transcript or identity into public audit output.
        message = str(exc) if isinstance(exc, ValueError) else "cannot access the supplied audit inputs"
        parser.exit(2, "audit refused: " + message + "\n")
    report["snapshot_sha256"] = digest
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
