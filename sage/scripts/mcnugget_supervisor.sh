#!/bin/bash
# McNugget autonomous supervisor — runs every 4 hours via launchd.
#
# Pulls repos, checks/launches sweeps, reads fleet forums, does work,
# documents and pushes. Designed to keep McNugget productive without
# manual intervention.
#
# Model: phi4-fa (phi4:14b, num_ctx 4096) — switched from gemma3-fa 2026-05-15
# Stack: v14 canonical (6 flags). v17.x OFF (confirmed harmful on mid-models).
#        v18 reset OFF by default (4.3× wall time cost for +1 level).

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
SWEEP_DIR="$HOME/mcnugget-sweep"

export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1
export PYTHONPATH="$DEV_SAGE"

# Model config
MODEL="phi4-fa"

# v14 canonical flags
export SAGE_COLD_START=1
export SAGE_OBJECT_SPACE=1
export SAGE_RULE_HARVESTER=1
export SAGE_COGNITIVE_EXTRACTION=1
export SAGE_GAMEPLAY_CONVERSATIONS=1
export SAGE_COGNITIVE_ROUTER=1

# v17.x combo: OFF (confirmed harmful on mid-models per fleet bisection)
# v18 reset: OFF by default (use dedicated v18 sweep scripts when needed)

export SAGE_MACHINE=mcnugget
export SAGE_LLM_BACKEND=ollama
export SAGE_OLLAMA_MODEL="$MODEL"

TIMESTAMP=$(date -u +'%Y-%m-%d %H:%M UTC')
echo "[McNugget-Supervisor] $TIMESTAMP — Starting cycle"
echo "[McNugget-Supervisor] Model: $MODEL, Stack: v14 canonical"

# === 1. PULL ALL REPOS ===
for repo in "$DEV_SAGE" "$SAGE_DIR" "$SHARED" "$PRIVATE" "$MEMORY" "$HESTIA"; do
    if [ -d "$repo" ]; then
        cd "$repo"
        git fetch origin 2>/dev/null
        git reset --hard origin/main 2>/dev/null
    fi
done
echo "[McNugget-Supervisor] Repos synced"

# === 2. CHECK SWEEPS ===
SWEEP_RUNNING=$(ps aux | grep sweep_all_25 | grep -v grep | wc -l | tr -d ' ')
SWEEP_LOG="$SWEEP_DIR/sweep.log"

if [ "$SWEEP_RUNNING" -gt 0 ]; then
    echo "[McNugget-Supervisor] Sweep in progress — not interfering"
    if [ -f "$SWEEP_LOG" ]; then
        DONE=$(grep -c "^L=" "$SWEEP_LOG" 2>/dev/null || echo 0)
        STARS=$(grep -c "★" "$SWEEP_LOG" 2>/dev/null || echo 0)
        echo "[McNugget-Supervisor] Progress: $DONE/25 games, $STARS level advances"
    fi
else
    # Check if dev-SAGE advanced since last sweep
    LAST_COMMIT_FILE="$SWEEP_DIR/.last_sweep_commit"
    CURRENT_COMMIT=$(cd "$DEV_SAGE" && git rev-parse --short HEAD)
    LAST_SWEEP_COMMIT=""
    if [ -f "$LAST_COMMIT_FILE" ]; then
        LAST_SWEEP_COMMIT=$(cat "$LAST_COMMIT_FILE" 2>/dev/null)
    fi

    if [ "$LAST_SWEEP_COMMIT" != "$CURRENT_COMMIT" ]; then
        echo "[McNugget-Supervisor] dev-SAGE advanced: ${LAST_SWEEP_COMMIT:-none} → $CURRENT_COMMIT"
        # Check ollama
        if curl -s http://localhost:11434/api/version >/dev/null 2>&1; then
            echo "[McNugget-Supervisor] Launching new sweep with $MODEL"
            mkdir -p "$SWEEP_DIR"/{episodes,tier1_diag,diagnostic_games}

            export SAGE_EPISODE_STORE_DIR="$SWEEP_DIR/episodes"
            export SAGE_TIER1_DIAG_DIR="$SWEEP_DIR/tier1_diag"
            export SAGE_GAME_DIAG_DIR="$SWEEP_DIR/diagnostic_games"

            cd "$SAGE_DIR"
            nohup "$SAGE_PY" \
                "$DEV_SAGE/arc-agi-3/experiments/sweep_all_25.py" \
                --model "$MODEL" --max-steps 600 --max-revisions 100 \
                > "$SWEEP_LOG" 2>&1 &
            echo "[McNugget-Supervisor] Sweep launched PID: $!"
            echo "$CURRENT_COMMIT" > "$LAST_COMMIT_FILE"
        else
            echo "[McNugget-Supervisor] Ollama not running — skipping sweep"
        fi
    else
        echo "[McNugget-Supervisor] No new code to sweep (last: $LAST_SWEEP_COMMIT)"
    fi
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
if [ "${SWEEP_RUNNING:-0}" -gt 0 ]; then
    SWEEP_NOTE="running (${DONE:-?}/25 games, ${STARS:-0} advances)"
else
    SWEEP_NOTE="idle"
fi
ENTRY="- $(date -u +'%H:%M UTC') — repos synced; ${RECENT_FORUM:-0} forum posts/24h; inbox: ${INBOX_N:-0}; sweep: $SWEEP_NOTE"
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
for repo in "$SHARED" "$DEV_SAGE" "$SAGE_DIR" "$PRIVATE"; do
    cd "$repo"
    if ! git diff --quiet 2>/dev/null || [ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then
        git add -A 2>/dev/null
        git commit -m "[McNugget-Supervisor] Autonomous cycle — $TIMESTAMP" 2>/dev/null
        git push origin main 2>&1 || true
    fi
done

echo "[McNugget-Supervisor] Cycle complete — $(date -u +'%Y-%m-%d %H:%M UTC')"
