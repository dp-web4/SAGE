#!/bin/bash
# McNugget autonomous supervisor — runs every 4 hours via launchd.
#
# Pulls repos, reads fleet forums, does work, documents and pushes. Designed to
# keep McNugget productive without manual intervention.
#
# No model. Until 2026-10-03 step 2 launched an ARC-AGI-3 25-game sweep on phi4-fa
# whenever dev-SAGE moved. It was `nohup … &` from a launchd job, which reaps it when
# the job exits: 583 launches, 0 finished games. dp, 2026-10-03: "we are no longer
# doing arc sweeps" -- removed, with the model and its ARC flags.

set -u

# Resolve a working python3 (see resolve_python.sh). Explicit `|| exit 1`:
# these scripts do not all `set -e`, and a quiet fallthrough here is exactly
# how raising died unnoticed for 29 days.
. "$(dirname "$0")/resolve_python.sh" || exit 1

SAGE_DIR="/Users/dennispalatov/repos/SAGE"
DEV_SAGE="/Users/dennispalatov/repos/dev-SAGE"
SHARED="/Users/dennispalatov/repos/shared-context"
PRIVATE="/Users/dennispalatov/repos/private-context"
MEMORY="/Users/dennispalatov/repos/memory"
HESTIA="/Users/dennispalatov/repos/hestia"

export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
export PYTHONPATH="$DEV_SAGE"

export SAGE_MACHINE=mcnugget

TIMESTAMP=$(date -u +'%Y-%m-%d %H:%M UTC')
echo "[McNugget-Supervisor] $TIMESTAMP — Starting cycle"

# === 1. PULL ALL REPOS ===
# `git reset --hard origin/main` on a tree with an unpushed commit DELETES that
# commit's files from the working tree. This loop did that to ten raising sessions
# (2026-06 through 2026-09-14) and once to a set of script fixes: a session commits
# locally, its push is rejected because origin moved, and four hours later this
# line erases it. So: never reset over an unpushed commit without first trying to
# push it, and never erase one without pinning it under refs/backup/ where it can
# be recovered. A discarded commit is a data loss; a pinned one is a chore.
for repo in "$DEV_SAGE" "$SAGE_DIR" "$SHARED" "$PRIVATE" "$MEMORY" "$HESTIA"; do
    if [ -d "$repo" ]; then
        cd "$repo"
        git fetch origin 2>/dev/null
        AHEAD=$(git log origin/main..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')
        if [ "${AHEAD:-0}" != "0" ]; then
            echo "[McNugget-Supervisor] $(basename "$repo"): $AHEAD unpushed commit(s) -- pushing before reset"
            if ! git push origin main >/dev/null 2>&1; then
                BK="refs/backup/supervisor-$(date -u +%Y%m%dT%H%M%SZ)"
                git update-ref "$BK" HEAD
                echo "[McNugget-Supervisor] *** $(basename "$repo"): push failed; $AHEAD commit(s) PINNED at $BK before reset ***" >&2
            fi
        fi
        # NOT `git reset --hard`. That command reverts every tracked file with uncommitted
        # changes, and the daemon writes tracked files all day. Measured 2026-09-18: the
        # being's Rust-side experience buffer had ONE commit in its history and 227 of these
        # resets after it, so everything the daemon learned was erased within four hours,
        # six times a day, for ten days -- by step 1 of a script whose step 4 exists to
        # commit exactly that state. --autostash carries the dirty files across the sync so
        # step 4 can commit them. If the sync cannot complete, the tree is left as it was:
        # a stale checkout is an inconvenience, and an erased memory is not recoverable.
        if ! git pull --rebase --autostash origin main >/dev/null 2>&1; then
            git rebase --abort >/dev/null 2>&1
            echo "[McNugget-Supervisor] *** $(basename "$repo"): could not sync with origin; tree left untouched ***" >&2
            SYNC_FAILED="${SYNC_FAILED:-}${SYNC_FAILED:+ }$(basename "$repo")"
        fi
    fi
done
# The fleet line says "repos synced" only when every repo did (NOVA on #513).
if [ -n "${SYNC_FAILED:-}" ]; then
    REPO_LINE="repos synced except: $SYNC_FAILED (left untouched)"
else
    REPO_LINE="repos synced"
fi
echo "[McNugget-Supervisor] $REPO_LINE"

# === 2. GOVERNANCE SNAPSHOTS ===
# dp, 2026-10-21 (private-context supervisor/CLAUDE.md): the governed read their law from
# <workspace>/governance/{hestia,sage}, read-only copies of the deployed hestia build and of the running
# SAGE gateway. Nothing else refreshes them, and a copy older than the deployed build sends readers to wrong
# line numbers, so every run refreshes both. Skipped where there is no governance/ (no governed members).
# The scripts are idempotent and are the only writers inside governance/.
# Each step keeps its own exit status and counts as done only on its own success line
# (supervisor_steps.sh; NOVA's HOLD on #513): a refused snapshot is logged FAILED, never as fresh.
. "$SAGE_DIR/sage/scripts/supervisor_steps.sh"
GOV_LINE=""
if [ -d "$(dirname "$SAGE_DIR")/governance" ]; then
    GOV_H="$(snapshot_status hestia "governance snapshot" "$SAGE_DIR/scripts/governance_snapshot.sh")"
    GOV_S="$(snapshot_status sage "sage governance snapshot" "$SAGE_DIR/scripts/governance_snapshot_sage.sh")"
    echo "[McNugget-Supervisor] governance: $GOV_H; $GOV_S"
    GOV_LINE="; governance $GOV_H, $GOV_S"
else
    GOV_LINE="; governance: skipped (no governance/ here)"
fi

# === 2a. THE BEING'S WORKTREE ===
# Keeping it current is the seat's job (being_gate_client.pr_base_branch: "it sets the upstream
# when it syncs your worktree"). Nothing on McNugget did: the worktree sat on a detached HEAD from
# 2026-10-03 until 10-23, so the being's git_read and search showed three-week-old code. Fast-forward
# only; the being's modified files or an open PR branch stop it (scripts/sync_being_worktree.sh).
BEING_WT="$(dirname "$SAGE_DIR")/being-worktrees/mcnugget-being"
if [ -d "$BEING_WT" ]; then
    WT_OUT="$(worktree_status "$SAGE_DIR/scripts/sync_being_worktree.sh" "$BEING_WT" main mcnugget-being)"
    echo "[McNugget-Supervisor] $WT_OUT"
    GOV_LINE="${GOV_LINE}; $WT_OUT"
else
    GOV_LINE="${GOV_LINE}; being worktree: skipped (none at $BEING_WT)"
fi

# === 3. READ FORUMS ===
cd "$SHARED"
RECENT_FORUM=$(find forum/ -name "*.md" -mtime -1 -type f 2>/dev/null | wc -l | tr -d ' ')
echo "[McNugget-Supervisor] $RECENT_FORUM forum posts in last 24h"

# === 3a. INBOX: posts addressed to this seat ===
# Root cause of a 12-day unanswered reply from HUB (2026-08-01) and a same-day one from Sprout:
# nothing here ever looked for "to:" lines naming mcnugget. Counting forum posts is not reading
# the ones addressed to you. Surface them by name so a cycle cannot end without them being seen.
INBOX=""
while IFS= read -r f; do
    [ -n "$f" ] || continue
    if head -8 "$f" 2>/dev/null | grep -qiE '^to:.*mcnugget'; then
        INBOX="$INBOX $(basename "$f")"
    fi
done < <(find "$SHARED/forum" -name '*.md' -mtime -2 -type f 2>/dev/null)
INBOX_N=$(printf '%s' "$INBOX" | wc -w | tr -d ' ')
if [ "$INBOX_N" -gt 0 ]; then
    echo "[McNugget-Supervisor] *** INBOX: $INBOX_N post(s) addressed to mcnugget ***"
    for m in $INBOX; do echo "[McNugget-Supervisor]   -> $m"; done
else
    echo "[McNugget-Supervisor] inbox: nothing addressed to mcnugget in last 48h"
fi

# === 3b. EMIT FLEET-VISIBLE EVIDENCE ===
# supervisor_coverage.py joins "who should run" (machines/fleet_tracks.db) against
# "who did" (supervisor/log_{machine}.md | autonomous-sessions/{machine}-supervisor-*.log).
# This supervisor ran for months writing only ~/Library/Logs/sage/, which that instrument
# cannot see — so McNugget read as "NO EVIDENCE" while healthy (nomad, 8 consecutive days).
# Emit the log_{machine}.md form the other four machines use: newest entry at TOP.
EVID="$PRIVATE/supervisor/log_mcnugget.md"
# Header uses the LOCAL date: supervisor_coverage.py compares against datetime.date.today(),
# which is local. A UTC header future-dates the entry after ~17:00 PDT and the tool then
# reports a nonsensical "-1d ago". Timestamps inside the line stay UTC and are labelled.
TODAY=$(date +'%Y-%m-%d')
ENTRY="- $(date -u +'%H:%M UTC') — ${REPO_LINE}; ${RECENT_FORUM:-0} forum posts/24h; inbox: ${INBOX_N:-0}${GOV_LINE}"
mkdir -p "$(dirname "$EVID")"
EVID="$EVID" TODAY="$TODAY" ENTRY="$ENTRY" python3 - <<'PY'
import os, re
p, today, entry = os.environ["EVID"], os.environ["TODAY"], os.environ["ENTRY"]
lines = open(p).read().splitlines(True) if os.path.exists(p) else []
# Preserve any leading title/preamble (everything before the first "## YYYY-MM-DD"), then
# insert today's entry as the newest dated section — newest-at-top, title stays on top.
hdr = re.compile(r"^## \d{4}-\d{2}-\d{2}\s*$")
i = next((n for n, l in enumerate(lines) if hdr.match(l)), len(lines))
pre, rest = lines[:i], lines[i:]
if not pre:
    pre = ["# McNugget supervisor log\n", "\n",
           "Newest entry at top (convention shared with `log_cbp.md`, `log_nomad.md`,\n",
           "`log_sprout.md`, `log_thor.md`; `supervisor_coverage.py` reads only the first\n",
           "`## YYYY-MM-DD` header).\n", "\n"]
if rest and rest[0].strip() == f"## {today}":
    rest.insert(1, entry + "\n")                 # same day -> append under existing header
else:
    rest = [f"## {today}\n", entry + "\n", "\n"] + rest
open(p, "w").write("".join(pre + rest))
PY
echo "[McNugget-Supervisor] evidence emitted -> supervisor/log_mcnugget.md"

# === 3c. FLEET-FACT DIVERGENCE CHECK ===
# Compare the published facts against their sources and report, loudly, when two
# copies of one fact disagree. Writes nothing and fixes nothing by design -- see
# the module docstring for why a differ rather than a generator.
#
# Wired here rather than left as a tool because an unwired mechanism is the exact
# defect this checks for: update_fleet_models.py was written 2026-03-08 to be
# "called at the start of raising sessions", was called by nothing on any seat,
# and fleet.json drifted six months while everyone assumed the mechanism worked.
# A checker nobody runs is worth less than no checker, because its existence is
# mistaken for coverage.
FFC_OUT="$($SAGE_PY "$SAGE_DIR/sage/tools/fleet_fact_check.py" --machine mcnugget 2>&1)"
FFC_RC=$?
echo "$FFC_OUT" | tail -1
if [ "$FFC_RC" -ne 0 ]; then
    echo "[McNugget-Supervisor] *** FLEET-FACT DIVERGENCE (rc=$FFC_RC) ***"
    echo "$FFC_OUT" | grep -E '^\s+(!!|\?\?)' -A1
fi

# === 4. PUSH (if anything changed) ===
# Being records are private going forward (shared-context/FLEET_BROADCAST_being_records_private.md,
# dp 2026-09-19/20). Until 2026-09-20 the `git add -A` below swept sage/instances/ into public SAGE
# every 4 h -- a second publisher beside the raising launcher, and the one a grep for
# `git add "$INSTANCE_DIR"` does not find. In SAGE this step now neither looks at nor stages
# anything under sage/instances/; the raising launcher mirrors the home to private-context.
for repo in "$SHARED" "$DEV_SAGE" "$SAGE_DIR" "$PRIVATE"; do
    cd "$repo"
    SPEC=(.)
    [ "$repo" = "$SAGE_DIR" ] && SPEC=(. ':(exclude)sage/instances')
    if ! git diff --quiet -- "${SPEC[@]}" 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard -- "${SPEC[@]}" 2>/dev/null)" ]; then
        git add -A -- "${SPEC[@]}" 2>/dev/null
        git commit -m "[McNugget-Supervisor] Autonomous cycle — $TIMESTAMP" 2>/dev/null
        git push origin main 2>&1 || true
    fi
done

echo "[McNugget-Supervisor] Cycle complete — $(date -u +'%Y-%m-%d %H:%M UTC')"
