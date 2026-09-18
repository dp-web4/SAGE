#!/bin/bash
# McNugget Gemma 4 E4B — Federation-raised gameplayer
# Raising sessions focused on puzzle reasoning, spatial understanding,
# and game-playing capability. Fed by fleet KB accumulated from ARC-AGI-3.
#
# Designed to run via launchd every 6 hours.

set -e

# Resolve a working python3 (see resolve_python.sh). Explicit `|| exit 1`:
# these scripts do not all `set -e`, and a quiet fallthrough here is exactly
# how raising died unnoticed for 29 days.
. "$(dirname "$0")/resolve_python.sh" || exit 1

SAGE_DIR="/Users/dennispalatov/repos/SAGE"
PYTHONPATH="$SAGE_DIR"
export PYTHONPATH

# Fix OpenMP duplicate library crash on macOS
export KMP_DUPLICATE_LIB_OK=TRUE
export OMP_NUM_THREADS=1

# Sprint 2 R1: source-stamp router records from raising sessions
export SAGE_SESSION_SOURCE=raising

cd "$SAGE_DIR"

echo "[McNugget-G4] $(date -u +'%Y-%m-%d %H:%M UTC') — Starting gameplayer raising session"

# Pull latest (stash first to avoid dirty-tree failures).
# Track whether THIS run actually stashed anything; only pop if so.
# Unconditional `git stash pop` could pop a stale stash from a prior
# run and silently inject merge markers into the working tree.
STASH_BEFORE=$(git stash list | wc -l)
git stash 2>/dev/null || true
git pull --rebase origin main 2>&1 || {
    echo "[McNugget-G4] WARNING: git pull failed, continuing with local state"
}
if [ "$(git stash list | wc -l)" -gt "$STASH_BEFORE" ]; then
    git stash pop
fi

# Ensure daemon is running
source "$SAGE_DIR/sage/scripts/ensure_daemon.sh"

# Run raising session with gemma4:e4b
# Note: instance resolved automatically from --machine + --model
"$SAGE_PY" -m sage.raising.scripts.ollama_raising_session \
    --machine mcnugget \
    --model gemma4:e4b \
    -c 2>&1

# Instance directory
INSTANCE_DIR="sage/instances/mcnugget-gemma4-e4b"

# Snapshot state
echo "[McNugget-G4] Snapshotting state..."
"$SAGE_PY" -m sage.scripts.snapshot_state --machine mcnugget --instance mcnugget-gemma4-e4b 2>/dev/null || true

# Read session info
SESSION_NUM=$("$SAGE_PY" -c "
import json
with open('$SAGE_DIR/$INSTANCE_DIR/identity.json') as f:
    print(json.load(f)['identity']['session_count'])
" 2>/dev/null || echo "?")

PHASE=$("$SAGE_PY" -c "
import json
with open('$SAGE_DIR/$INSTANCE_DIR/identity.json') as f:
    print(json.load(f)['development']['phase_name'])
" 2>/dev/null || echo "?")

# Dream consolidation
echo "[McNugget-G4] Running dream consolidation..."
"$SAGE_PY" -m sage.raising.scripts.dream_consolidation \
    --instance "$INSTANCE_DIR" \
    --session "$SESSION_NUM" 2>&1 || {
    echo "[McNugget-G4] Dream consolidation skipped"
}

# Commit if changed
CHANGED=0
if [ -d "$INSTANCE_DIR" ]; then
    if ! git diff --quiet "$INSTANCE_DIR/" 2>/dev/null; then
        CHANGED=1
    fi
    if [ -n "$(git ls-files --others --exclude-standard "$INSTANCE_DIR/" 2>/dev/null)" ]; then
        CHANGED=1
    fi
fi

if [ "$CHANGED" -eq 0 ]; then
    echo "[McNugget-G4] No new data to commit."
    exit 0
fi

git add "$INSTANCE_DIR/" 2>/dev/null || true

git commit -m "[McNugget-G4-Raising] Session $SESSION_NUM ($PHASE) — $(date -u +'%Y-%m-%d %H:%M UTC')

Federation-raised gameplayer session via Gemma 4 E4B
Machine: McNugget (Mac Mini M4)
Model: Gemma 4 E4B (google-gemma4 family)
Phase: $PHASE
Role: gameplayer (ARC-AGI-3 competition)
AI-Instance: OllamaIRP (automated)
Human-Supervised: no"

# Same silenced closing pull that lost ten sessions in mcnugget_raising_fluid.sh
# (see that script and SAGE@05fac6d4a). Dormant script, fixed for the same reason.
git pull --rebase --autostash origin main 2>&1 | sed 's/^/[McNugget-Gameplayer] pull: /'
git push origin main 2>&1 || {
    echo "[McNugget-G4] WARNING: push failed, will retry next session"
}
echo "[McNugget-G4] Session $SESSION_NUM committed and pushed."
