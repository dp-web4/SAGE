"""Offline materials and observation scoring for SAGE #456; never runs a being.

prepare emits a SEAT-ONLY pack: deliver only message and fixture, not oracle.
score reads one recorded phase and optional before/after snapshots. Its separate
predicates do not establish causation, whole-trial coverage, or model capability.
No model, dispatcher, gate, network, or live-instance write is performed here.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

from sage.gateway.edit_grounding_probe import observed_window


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(arm, path):
    if arm not in ("ordinary", "guided"):
        raise ValueError("unknown arm")
    # A message is not an execution boundary, but do not manufacture unsafe paths.
    if not isinstance(path, str):
        raise ValueError("requires a string path")
    p = PurePosixPath(path)
    if (not path.isascii() or
            any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-/ ." for c in path) or
            " " in path or p.is_absolute() or ".." in p.parts or
            p.parts[:1] != ("scratch",) or p.suffix != ".md" or str(p) != path):
        raise ValueError("requires a normalized scratch-relative markdown path")
    start, offset, total, target = ((121, 4, 192, "marigold") if arm == "ordinary"
                                   else (257, 2, 288, "cobalt"))
    rows = ["padding: keep unchanged\n"] * total
    window = [f"record decoy-{i} | status pending | note synthetic\n" for i in range(9)]
    old = f"record {target} | status pending | note synthetic\n"
    new = old.replace("status pending", "status selected")
    window[offset] = old
    window[7] = f"record {target}-extra | status pending | note synthetic\n"
    rows[start - 1:start + 8] = window
    fixture = "".join(rows)
    selected = start + offset
    rows[selected - 1] = new
    expected = "".join(rows)
    message = (
        "Optional bounded editing exercise. This is synthetic, not a real task-completion claim. "
        f"In {path}, read lines {start}-{start + 8}. Change only the status of record {target} "
        "from pending to selected, preserving every other byte. Use memory_read and memory_edit "
        "on this file only; do not run code, request scope, append, or change any other file for this exercise. "
        "Make at most one initial edit and, if refused, one reread and one corrected edit, then stop. "
        "You may decline or defer; say so rather than claiming success."
    )
    if arm == "guided":
        message += (
            " Ground the edit in the returned read: derive the absolute file line from its window header, "
            "not the row number within the window. Use that same line for start_line and end_line, "
            "and copy the complete observed line into old as a check; change only its status in new."
        )
    return {"schema": "line-selection-material/v1", "arm": arm, "path": path,
            "message": message, "message_sha256": sha(message.encode()),
            "fixture": fixture, "fixture_sha256": sha(fixture.encode()),
            "seat_only_oracle": {"selected_line": selected, "old": old, "new": new,
                                 "expected": expected, "expected_sha256": sha(expected.encode())}}


def _text_arg(args, keys):
    return next((args[k] for k in keys if k in args), None)


def score(pack, raw_record, phase, before=None, after=None):
    """First memory_edit in selected phase, never the first successful/on-target edit.

    Missing snapshots stay unknown. Paths inside records are compared as strings,
    never opened. Path aliases are deliberately not inferred. Token accounting and
    cross-phase/beat chronology remain the observer's separate evidence obligation.
    """
    row = json.loads(raw_record)
    trace = row[phase]["trace"]
    if not isinstance(trace, list) or any(not isinstance(e, dict) for e in trace):
        raise ValueError("requires a list of receipt objects")
    oracle = pack["seat_only_oracle"]
    fixture = pack["fixture"].encode()
    expected = oracle["expected"].encode()
    index = next((i for i, e in enumerate(trace) if e.get("effector") == "memory_edit"), None)
    first = None
    if index is not None:
        event = trace[index]
        args = event.get("args")
        if not isinstance(args, dict):
            args = {}
        old = _text_arg(args, ("old", "old_text", "old_str", "old_string"))
        new = _text_arg(args, ("new", "new_text", "new_str", "new_string", "new_content",
                               "replacement", "content", "new_lines"))
        start = _text_arg(args, ("start_line", "line", "old_line"))
        end = args.get("end_line", start)
        grounded = False
        read_forms = []
        for read in trace[:index]:
            if (read.get("effector") != "memory_read" or read.get("ok") is not True or
                    not isinstance(read.get("args"), dict) or read["args"].get("path") != pack["path"]):
                continue
            if read.get("result") == pack["fixture"]:
                read_forms.append("unwindowed_full_read")
                grounded = True
                continue
            try:
                text, read_start, total = observed_window(read)
            except (ValueError, TypeError):
                read_forms.append("unverified_read")
                if grounded is False:
                    grounded = None
                continue
            lines = text.splitlines(keepends=True)
            planned = pack["fixture"].splitlines(keepends=True)
            if (total == len(planned) and
                    read_start <= oracle["selected_line"] < read_start + len(lines) and
                    lines == planned[read_start - 1:read_start - 1 + len(lines)]):
                grounded = True
                read_forms.append("matching_window")
            else:
                read_forms.append("nonmatching_window")
        first = {
            "trace_index": index,
            "coordinate_arguments": {k: args[k] for k in ("start_line", "line", "old_line", "end_line") if k in args},
            "path_matches_literal": args.get("path") == pack["path"],
            "absolute_single_line": str(start) == str(end) == str(oracle["selected_line"]),
            "old_matches_line": isinstance(old, str) and old.rstrip("\n") == oracle["old"].rstrip("\n"),
            "new_matches_line": isinstance(new, str) and new.rstrip("\n") == oracle["new"].rstrip("\n"),
            "matching_preceding_read_observed": grounded,
            "successful_preceding_same_path_read_observed": bool(read_forms),
            "preceding_read_forms": read_forms,
            "receipt_ok": event.get("ok") if type(event.get("ok")) is bool else None,
        }
    return {"schema": "line-selection-observation/v2", "arm": pack["arm"],
            "record_sha256": sha(raw_record), "planned_message_sha256": pack["message_sha256"],
            "fixture_sha256": pack["fixture_sha256"], "phase": phase,
            "first_memory_edit": first,
            "observed_memory_edits": sum(e.get("effector") == "memory_edit" for e in trace),
            "observed_other_effectors": sum(e.get("effector") not in ("memory_read", "memory_edit") for e in trace),
            "observed_other_path_memory_calls": sum(
                e.get("effector") in ("memory_read", "memory_edit") and
                (not isinstance(e.get("args"), dict) or e["args"].get("path") != pack["path"])
                for e in trace),
            "before_sha256": sha(before) if before is not None else None,
            "after_sha256": sha(after) if after is not None else None,
            "before_matches_fixture": before == fixture if before is not None else None,
            "after_matches_expected": after == expected if after is not None else None,
            "limit": "One selected recorded phase and supplied snapshots, not complete trial coverage, "
                     "authenticated delivery, effect attribution or a causal comparison. "
                     "An exact-text edit can succeed without demonstrating absolute numbering. "
                     "Only the first edit is line-selection evidence; recovery after a refusal "
                     "can follow coordinates supplied by the dispatcher."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "score"))
    parser.add_argument("--arm", required=True, choices=("ordinary", "guided"))
    parser.add_argument("--path", required=True, help="Exact scratch-relative path used in the delivery")
    parser.add_argument("--log", help="Recorded heartbeat JSONL (read only)")
    parser.add_argument("--beat", help="Unique exact recorded timestamp")
    parser.add_argument("--phase", choices=("explore", "posture", "reflect", "answer", "act_after_answer"))
    parser.add_argument("--before", help="Observer-supplied pretrial byte snapshot, not the live file")
    parser.add_argument("--after", help="Observer-supplied posttrial byte snapshot, not the live file")
    args = parser.parse_args(argv)
    try:
        pack = prepare(args.arm, args.path)
        out = pack
        if args.mode == "score":
            if not args.log or not args.beat or not args.phase:
                raise ValueError("score requires log, beat and phase")
            matches = []
            with open(args.log, "rb") as stream:
                for raw in stream:
                    row = json.loads(raw)
                    if not isinstance(row, dict):
                        raise ValueError("record must be an object")
                    if row.get("ts") == args.beat:
                        matches.append(raw)
                        if len(matches) > 1:
                            break
            if len(matches) != 1:
                raise ValueError("beat must identify exactly one record")
            out = score(pack, matches[0], args.phase,
                        Path(args.before).read_bytes() if args.before else None,
                        Path(args.after).read_bytes() if args.after else None)
    except (OSError, ValueError, TypeError, KeyError):
        parser.error("input does not satisfy the pilot observation contract")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
