#!/bin/bash
# CBP SAGE raising session + auto-commit
# Runs a raising session, snapshots state, commits results, pushes to origin.
# Schedule: 07:00 daily via crontab.

set -e

SAGE_DIR="/home/dp/ai-agents/SAGE"
export PYTHONPATH="$SAGE_DIR"

cd "$SAGE_DIR"

echo "[CBP-Raising] $(date -u +'%Y-%m-%d %H:%M UTC') — Starting raising session"

# Hardbound session governance
source /mnt/c/exe/projects/ai-agents/hardbound/scripts/hardbound_session_start.sh "$SAGE_DIR" "cbp-claude" 2>/dev/null || true

# Pull latest before running (avoid conflicts)
git pull --rebase origin main 2>&1 || {
    echo "[CBP-Raising] WARNING: git pull failed, continuing with local state"
}

# Run the raising session (continue from last session number)
python3 -m sage.raising.scripts.ollama_raising_session --machine cbp -c 2>&1

# Instance directory
INSTANCE_DIR="sage/instances/cbp-tinyllama-latest"

# Snapshot live state into git-tracked snapshots/ directory
echo "[CBP-Raising] Snapshotting state..."
python3 -m sage.scripts.snapshot_state --machine cbp

# Read session number and phase from live identity
IDENTITY_FILE="$INSTANCE_DIR/identity.json"
SESSION_NUM=$(python3 -c "
import json
with open('$SAGE_DIR/$IDENTITY_FILE') as f:
    print(json.load(f)['identity']['session_count'])
" 2>/dev/null || echo "?")

PHASE=$(python3 -c "
import json
with open('$SAGE_DIR/$IDENTITY_FILE') as f:
    print(json.load(f)['development']['phase_name'])
" 2>/dev/null || echo "?")

# Regenerate session primer with updated fleet state
echo "[CBP-Raising] Updating SESSION_PRIMER.md..."
python3 -m sage.scripts.generate_primer 2>/dev/null || true

# Check if there are new results to commit
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
    echo "[CBP-Raising] No new raising data to commit."
    exit 0
fi

# Stage instance dir + primer
git add "$INSTANCE_DIR/" SESSION_PRIMER.md 2>/dev/null || true

git commit -m "[CBP-Raising] Session $SESSION_NUM ($PHASE) — $(date -u +'%Y-%m-%d %H:%M UTC')

Automated SAGE-CBP raising session via OllamaIRP
Machine: CBP (Desktop RTX 2060 SUPER, WSL2)
Model: TinyLlama 1.1B
Phase: $PHASE
AI-Instance: OllamaIRP (automated)
Human-Supervised: no"

# Hardbound session end
source /mnt/c/exe/projects/ai-agents/hardbound/scripts/hardbound_session_end.sh "$SAGE_DIR" "cbp-claude" "cbp raising session $SESSION_NUM" "success" 2>/dev/null || true

# Push
PAT=$(grep GITHUB_PAT /mnt/c/exe/projects/ai-agents/.env 2>/dev/null | cut -d= -f2)
if [ -n "$PAT" ]; then
    git push "https://dp-web4:${PAT}@github.com/dp-web4/SAGE.git" main
    echo "[CBP-Raising] Session $SESSION_NUM committed and pushed."
else
    git push origin main
    echo "[CBP-Raising] Session $SESSION_NUM committed and pushed."
fi
