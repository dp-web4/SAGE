"""Read-only bounded pilot closeout; no inference, delivery, or live-state changes.

Only explicit path spellings are matched. Conversation selection/seen/utterance
are observations, not task acceptance or completion. All activity is reported;
unrelated acts cannot be attributed to the pilot without separate evidence.
"""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math

PHASES = ("explore", "posture", "account", "reflect", "answer", "act_after_answer")
READ_EFFECTORS = {"memory_read", "search", "git_read"}
EDIT_EFFECTORS = {"memory_write", "memory_insert", "memory_edit", "edit_file",
                  "git_restore", "git_clean", "retire_note"}


def summarize(lines, *, first_beat, paths, conversation, sequence, count=2):
    if not 1 <= count <= 10 or not paths:
        raise ValueError("requires a bounded count and explicit fixture paths")
    out = []
    started = False
    prior = None
    previous_cursor = None
    for raw in lines:
        row = json.loads(raw)
        if not isinstance(row, dict):
            raise ValueError("record must be an object")
        marked = (row.get("conversations_marked") or {}).get("marked", {})
        cursor = marked.get(conversation)
        cursor = cursor if type(cursor) is int else None
        if not started:
            if row.get("ts") != first_beat:
                previous_cursor = cursor
                continue
            started = True
        if row.get("schema") != "heartbeat/v2":
            raise ValueError("requires heartbeat/v2")
        stamp = datetime.strptime(row["ts"], "%Y-%m-%dT%H:%M:%SZ")
        if prior is not None and stamp <= prior:
            raise ValueError("window records must have increasing unique timestamps")
        prior = stamp
        selected = row.get("selected")
        phases = {}
        for phase in PHASES:
            body = row.get(phase)
            if body is None:
                phases[phase] = {"record": "null" if phase in row else "missing"}
                continue
            trace = body.get("trace") if isinstance(body, dict) else None
            if not isinstance(trace, list):
                phases[phase] = {"record": "no_valid_trace"}
                continue
            counts = {"receipts": len(trace), "fixture_reads": 0, "fixture_edits": 0,
                      "fixture_path_receipts_by_effector": {},
                      "say_to_requested_conversation": 0, "say_mentions_fixture": 0,
                      "other_receipts": 0, "malformed_receipts": 0}
            for event in trace:
                if (not isinstance(event, dict) or not isinstance(event.get("args"), dict)
                        or not isinstance(event.get("effector"), str)):
                    counts["malformed_receipts"] += 1
                    continue
                eff, args = event.get("effector"), event["args"]
                path_match = isinstance(args.get("path"), str) and args["path"] in paths
                if path_match:
                    by_effector = counts["fixture_path_receipts_by_effector"]
                    by_effector[eff] = by_effector.get(eff, 0) + 1
                if path_match and eff in READ_EFFECTORS | EDIT_EFFECTORS:
                    counts["fixture_reads" if eff in READ_EFFECTORS else "fixture_edits"] += 1
                else:
                    counts["other_receipts"] += 1
                if eff == "say" and args.get("to") == conversation:
                    counts["say_to_requested_conversation"] += 1
                    text = args.get("text")
                    counts["say_mentions_fixture"] += isinstance(text, str) and any(p in text for p in paths)
            phases[phase] = {"record": "trace", **counts}
        elapsed = row.get("elapsed_s")
        end = (stamp + timedelta(seconds=elapsed)).isoformat() + "Z" if (
            type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= 0) else None
        out.append({"ts": row["ts"], "reported_end": end,
                    "record_sha256": hashlib.sha256(raw).hexdigest(),
                    "request_selected": selected.get("turn") == f"{conversation}:{sequence}" if isinstance(selected, dict) else None,
                    "selected_expects_reply": selected.get("expects_reply") if isinstance(selected, dict) else None,
                    "request_seen_cursor": cursor,
                    "previous_request_seen_cursor": previous_cursor,
                    "cursor_at_or_past_request": cursor >= sequence if cursor is not None else None,
                    "marked_this_beat": previous_cursor < sequence <= cursor
                    if previous_cursor is not None and cursor is not None else None,
                    "preempted": bool(row.get("preempted")), "killed": bool(row.get("killed")),
                    "phases": phases})
        previous_cursor = cursor
        if len(out) == count:
            break
    return {"schema": "pilot-window/v1", "requested_beats": count, "observed_beats": len(out),
            "window_complete": len(out) == count, "beats": out,
            "limit": "Explicit contiguous recorded window, not verified delivery or an enforced stop. "
                     "Read/edit counts classify known effectors with an exact args.path match and count attempts, not effects. "
                     "All matching path receipts are also grouped by effector, including unclassified ones. "
                     "Paths inside diffs, commands or directories are not resolved; zero is not proof of no effect. "
                     "Account reply text without a trace is not counted as an utterance. "
                     "Cursor crossings require both adjacent recorded cursors; missing baselines stay unknown. "
                     "Seen/selected/utterance are not task completion; missing evidence stays visible. "
                     "Reported end derives from recorded start plus elapsed, not an independent clock."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log")
    parser.add_argument("--first-beat", required=True)
    parser.add_argument("--path", action="append", required=True)
    parser.add_argument("--conversation", required=True)
    parser.add_argument("--sequence", type=int, required=True)
    parser.add_argument("--count", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        with open(args.log, "rb") as stream:
            out = summarize(stream, first_beat=args.first_beat, paths=args.path,
                            conversation=args.conversation, sequence=args.sequence, count=args.count)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        parser.error("input does not satisfy the bounded observation contract")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
