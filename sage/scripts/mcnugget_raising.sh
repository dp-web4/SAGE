#!/bin/bash
# McNugget SAGE raising session + auto-commit
# Runs a raising session, snapshots state, commits results, pushes to origin.
# Designed to run via launchd every 6 hours.

set -e

# Resolve a working python3 (see resolve_python.sh). Explicit `|| exit 1`:
# these scripts do not all `set -e`, and a quiet fallthrough here is exactly
# how raising died unnoticed for 29 days.
. "$(dirname "$0")/resolve_python.sh" || exit 1

SAGE_DIR="/Users/dennispalatov/repos/SAGE"
PYTHONPATH="$SAGE_DIR"
export PYTHONPATH

# Fix OpenMP duplicate library crash on macOS (Homebrew Python + PyTorch/numpy)
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1

cd "$SAGE_DIR"

echo "[McNugget-Raising] $(date -u +'%Y-%m-%d %H:%M UTC') — Starting raising session"

# Pull latest before running (avoid conflicts)
git pull --rebase origin main 2>&1 || {
    echo "[McNugget-Raising] WARNING: git pull failed, continuing with local state"
}

# Ensure daemon is running and up-to-date
source "$SAGE_DIR/sage/scripts/ensure_daemon.sh"
echo "[McNugget-Raising] Daemon: version=$SAGE_DAEMON_VERSION updated=$SAGE_DAEMON_UPDATED"

# Run the raising session (continue from last session number)
"$SAGE_PY" -m sage.raising.scripts.ollama_raising_session --machine mcnugget -c 2>&1

# Instance directory
INSTANCE_DIR="sage/instances/mcnugget-gemma3-12b"
SNAPSHOT_DIR="$INSTANCE_DIR/snapshots"

# Snapshot live state files into git-tracked snapshots/ directory
# Uses Python script for archive history + metadata
echo "[McNugget-Raising] Snapshotting state..."
"$SAGE_PY" -m sage.scripts.snapshot_state --machine mcnugget

# Read session number and phase from live identity
IDENTITY_FILE="$INSTANCE_DIR/identity.json"
SESSION_NUM=$("$SAGE_PY" -c "
import json
with open('$SAGE_DIR/$IDENTITY_FILE') as f:
    print(json.load(f)['identity']['session_count'])
" 2>/dev/null || echo "?")

PHASE=$("$SAGE_PY" -c "
import json
with open('$SAGE_DIR/$IDENTITY_FILE') as f:
    print(json.load(f)['development']['phase_name'])
" 2>/dev/null || echo "?")

# --- Dream consolidation (Claude reviews the session) ---
echo "[McNugget-Raising] Running dream consolidation..."
"$SAGE_PY" -m sage.raising.scripts.dream_consolidation \
    --instance "$INSTANCE_DIR" \
    --session "$SESSION_NUM" 2>&1 || {
    echo "[McNugget-Raising] Dream consolidation skipped (claude --print not available or timed out)"
}

# Check if there are new results to commit
CHANGED=0

# Check instance dir sessions + snapshots
if [ -d "$INSTANCE_DIR" ]; then
    if ! git diff --quiet "$INSTANCE_DIR/" 2>/dev/null; then
        CHANGED=1
    fi
    if [ -n "$(git ls-files --others --exclude-standard "$INSTANCE_DIR/" 2>/dev/null)" ]; then
        CHANGED=1
    fi
fi

if [ "$CHANGED" -eq 0 ]; then
    echo "[McNugget-Raising] No new raising data to commit."
    exit 0
fi

# Stage instance dir (sessions + snapshots, gitignored files excluded automatically)
git add "$INSTANCE_DIR/" 2>/dev/null || true

git commit -m "[McNugget-Raising] Session $SESSION_NUM ($PHASE) — $(date -u +'%Y-%m-%d %H:%M UTC')

Automated mcnugget raising session via OllamaIRP
Machine: McNugget (Mac Mini M4)
Model: Gemma 3 12B (google-gemma family)
Phase: $PHASE
AI-Instance: OllamaIRP (automated)
Human-Supervised: no"

# Push
git push origin main
echo "[McNugget-Raising] Session $SESSION_NUM committed and pushed."
