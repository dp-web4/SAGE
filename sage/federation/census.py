#!/usr/bin/env python3
"""
Derive the fleet session census from git, not from self-reported fields.

Every number here comes from `git log`/`git ls-tree` on each instance's
`sessions/` path. Nothing is typed, and nothing is read from the three
sources measured to be stale: `snapshots/identity.json:last_session`,
`fleet.json:model_default`, and `sage-fleet-models.json`.

Why derived rather than self-registered: `sage-fleet-models.json` already
tried the self-registration design ("Each machine owns and updates its own
entry. The 4-lab maintainer reads this to keep the fleet page current.").
Every entry in it is still stamped 2026-03-08, the day it landed. A push
design fails silently, and silence is indistinguishable from "unchanged".

Basis is a declared output field, not a baked-in assumption -- there are two
independent choices and this prints all of them rather than picking one:

  scope   which instance lines sum into a machine
            line  -- the single live instance line (what the site shows)
            box   -- every instance line on that machine, archives included
  counter what counts as a session record
            strict -- session_<n>.json, the canonical raising-ledger form
            loose  -- session_*.json, including dry-run/variant suffixes
            all    -- every file under sessions/ except .gitkeep

Measured 2026-09-12: on the eight lines the site shows, strict/loose/all agree
exactly on six and differ by at most 2 on the other two. The counter choice is
effectively a no-op on the published rows; its 244-file blast radius is inside
`sprout-qwen2.5-0.5b`, a retired line the site excludes. So the counter is not
a blocker for publishing -- it is a blocker for box-sums only.

Liveness is three states, because HUB fits neither of the usual two: its loop
ran today and its ledger froze on 2026-07-29 (165 commits touching the
instance since, none adding a session file).

Usage:
    python3 -m sage.federation.census
    python3 -m sage.federation.census --scope box --counter all
    python3 -m sage.federation.census --json
"""

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INSTANCES = "sage/instances"

STRICT_RE = re.compile(r"session_\d+\.json\Z")
LOOSE_RE = re.compile(r"session_.*\.json\Z")
INDEX_RE = re.compile(r"session_(\d+)")

# An instance line is retired if its directory name carries an archive marker.
ARCHIVE_RE = re.compile(r"\.(?:bak\.)?archive-\d{8}\Z")

# Days without a new session record before a line is no longer "running".
STALE_DAYS = 14


def git(*args, ref="HEAD"):
    out = subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True, check=True,
    )
    return out.stdout


def session_files(ref):
    """{instance: [filename, ...]} for every file under an instance sessions/ dir."""
    listing = git("ls-tree", "-r", "--name-only", ref, f"{INSTANCES}/", ref=ref)
    per_instance = defaultdict(list)
    for line in listing.splitlines():
        parts = line.split("/")
        # sage/instances/<inst>/sessions/<...>/<file>
        if len(parts) < 5 or parts[3] != "sessions":
            continue
        name = parts[-1]
        if name == ".gitkeep":
            continue
        per_instance[parts[2]].append(name)
    return per_instance


def count(names, counter):
    # `all` is "every file under sessions/ except .gitkeep" -- see the basis
    # block in the module docstring. Every instance line carries one, so a
    # counter that includes it reports 12 on `thor-qwen2.5-14b` (0 session
    # records) and 284 on `sprout-qwen2.5-0.5b`. The exclusion is the filter in
    # session_files(), not a dotfile-blind glob.
    if counter == "strict":
        return sum(1 for n in names if STRICT_RE.match(n))
    if counter == "loose":
        return sum(1 for n in names if LOOSE_RE.match(n))
    return len(names)


def reached(names):
    """Highest canonical session index -- differs from the count when the ledger has gaps.

    Only `session_<n>.json` counts. `sprout-qwen2.5-0.5b` holds a
    `session_901_..._dry_run.json`, so matching any `session_<n>` prefix
    reports that line as having reached 901 against 104 records.
    """
    idx = [int(m.group(1)) for n in names if STRICT_RE.match(n) and (m := INDEX_RE.match(n))]
    return max(idx) if idx else 0


def instance_machine(inst, ref):
    """Machine name from instance.json; fall back to the directory prefix."""
    try:
        blob = git("show", f"{ref}:{INSTANCES}/{inst}/instance.json", ref=ref)
        return json.loads(blob).get("machine") or inst.split("-")[0]
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return inst.split("-")[0]


def instance_model(inst, ref):
    try:
        blob = git("show", f"{ref}:{INSTANCES}/{inst}/instance.json", ref=ref)
        return json.loads(blob).get("model")
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def last_dates(inst, ref):
    """(last session-adding commit, last commit touching the instance, merge_only).

    `--diff-merges=first-parent` is load-bearing, not a flourish. Merge commits
    show no diff by default, so plain `git log --diff-filter=A -- <sessions>`
    returns NOTHING for a ledger that entered main through a merge.
    `sprout-qwen3.8-distill-2b` is exactly that case: 661 session files, and the
    only two commits touching the path in all of reachable history are merges
    (#36, #37). Without this flag the fleet's second-largest ledger derives as
    undated and is classified `empty` -- the same false-stop this census exists
    to prevent, reintroduced by the tool meant to fix it.
    """
    sessions = f"{INSTANCES}/{inst}/sessions/"
    added = git(
        "log", ref, "--diff-merges=first-parent", "--diff-filter=AR",
        "--format=%ad", "--date=short", "-1", "--", sessions, ref=ref,
    ).strip().splitlines()
    added = added[0] if added else ""
    # Did any non-merge commit ever add here? If not, the date is merge-derived
    # and the per-session history is not on this branch at all.
    direct = git(
        "log", ref, "--no-merges", "--diff-filter=AR", "--format=%ad",
        "--date=short", "-1", "--", sessions, ref=ref,
    ).strip()
    touched = git(
        "log", ref, "--format=%ad", "--date=short", "-1",
        "--", f"{INSTANCES}/{inst}/", ref=ref,
    ).strip()
    return (added or None, touched or None, bool(added) and not direct)


def days_since(iso, today):
    if not iso:
        return None
    return (today - date.fromisoformat(iso)).days


def liveness(last_session, last_touch, today):
    """running / paused / instrumentation-broken / empty.

    instrumentation-broken is the HUB case: the harness is committing but the
    ledger is not growing. Collapsing it into `paused` reports a live loop as
    stopped, which is the failure this census exists to stop repeating.
    """
    if last_session is None:
        return "empty"
    sess_age = days_since(last_session, today)
    touch_age = days_since(last_touch, today) if last_touch else None
    if sess_age <= STALE_DAYS:
        return "running"
    if touch_age is not None and touch_age <= STALE_DAYS:
        return "instrumentation-broken"
    return "paused"


def build(ref, counter, today):
    per_instance = session_files(ref)
    rows = []
    for inst in sorted(per_instance):
        names = per_instance[inst]
        last_session, last_touch, merge_only = last_dates(inst, ref)
        rows.append({
            "instance": inst,
            "machine": instance_machine(inst, ref),
            "model": instance_model(inst, ref),
            "retired": bool(ARCHIVE_RE.search(inst)),
            "recorded": count(names, counter),
            "reached": reached(names),
            "counts": {c: count(names, c) for c in ("strict", "loose", "all")},
            "last_session": last_session,
            "last_activity": last_touch,
            "merge_derived_date": merge_only,
            "liveness": liveness(last_session, last_touch, today),
        })
    return rows


def by_machine(rows, scope):
    """Collapse instance lines into machine rows under the declared scope."""
    groups = defaultdict(list)
    for r in rows:
        groups[r["machine"]].append(r)
    out = []
    for machine, lines in sorted(groups.items()):
        if scope == "box":
            members = lines
        else:
            # The live line: most recent session record, retired lines last.
            members = [
                max(lines, key=lambda r: (not r["retired"], r["last_session"] or "", r["recorded"]))
            ]
        total = sum(r["recorded"] for r in members)
        primary = max(members, key=lambda r: (r["last_session"] or "", r["recorded"]))
        out.append({
            "machine": machine,
            "sessions": total,
            "as_of": primary["last_session"],
            "liveness": primary["liveness"],
            "model": primary["model"],
            "lines": [r["instance"] for r in members],
            "ambiguous_count": any(
                r["counts"]["strict"] != r["counts"]["all"] for r in members
            ),
            "gapped_ledger": any(
                r["reached"] != r["counts"]["strict"] for r in members
            ),
            "merge_derived_date": any(r["merge_derived_date"] for r in members),
        })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--ref", default="origin/main",
                    help="git ref to measure (default: origin/main -- the shared record)")
    ap.add_argument("--scope", choices=("line", "box"), default="line")
    ap.add_argument("--counter", choices=("strict", "loose", "all"), default="strict")
    ap.add_argument("--instances", action="store_true", help="per instance line, not per machine")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    today = datetime.now(timezone.utc).date()
    rows = build(args.ref, args.counter, today)
    basis = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ref": args.ref,
        "commit": git("rev-parse", "--short", args.ref).strip(),
        "scope": args.scope,
        "counter": args.counter,
        "source": f"git ls-tree/log on {INSTANCES}/*/sessions/",
        "stale_days": STALE_DAYS,
    }

    payload = rows if args.instances else by_machine(rows, args.scope)

    if args.json:
        print(json.dumps({"basis": basis, "rows": payload}, indent=2))
        return 0

    print(f"# fleet session census -- scope={args.scope} counter={args.counter} "
          f"ref={args.ref}@{basis['commit']}")
    print(f"# derived from {basis['source']} at {basis['generated_at']}")
    print()
    if args.instances:
        print(f"{'instance':42s} {'mach':9s} {'rec':>5s} {'rchd':>5s} "
              f"{'strict/loose/all':>17s} {'last session':>13s} {'liveness':>22s}")
        for r in payload:
            trio = f"{r['counts']['strict']}/{r['counts']['loose']}/{r['counts']['all']}"
            print(f"{r['instance']:42s} {r['machine']:9s} {r['recorded']:5d} {r['reached']:5d} "
                  f"{trio:>17s} {str(r['last_session']):>13s} {r['liveness']:>22s}")
    else:
        print(f"{'machine':10s} {'sessions':>9s} {'as of':>12s} {'liveness':>22s}  flags  lines")
        for r in payload:
            flags = []
            if r["ambiguous_count"]:
                flags.append("counter-sensitive")
            if r["gapped_ledger"]:
                flags.append("gapped-ledger")
            if r["merge_derived_date"]:
                flags.append("merge-derived-date")
            print(f"{r['machine']:10s} {r['sessions']:9d} {str(r['as_of']):>12s} "
                  f"{r['liveness']:>22s}  {','.join(flags) or '-':21s} "
                  f"{','.join(r['lines'])}")
        print()
        print(f"total: {sum(r['sessions'] for r in payload)} sessions over "
              f"{len(payload)} machines, scope={args.scope}, counter={args.counter}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
