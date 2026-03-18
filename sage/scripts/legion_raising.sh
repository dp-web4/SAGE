#!/bin/bash
# Legion SAGE raising session + auto-commit
# Runs a raising session, commits results, pushes to origin.
# Designed to run via systemd timer every 6 hours.

set -e

SAGE_DIR="/home/dp/ai-workspace/SAGE"
PYTHONPATH="$SAGE_DIR"
export PYTHONPATH
PYTHON="/home/dp/miniforge3/bin/python3"

cd "$SAGE_DIR"

# Account routing: synth token for raising sessions (synthesis pool machine)
ENV_FILE="/home/dp/ai-workspace/.env"
if [ -f "$ENV_FILE" ]; then
    CLAUDE_SYNTH_TOKEN=$(grep '^CLAUDE_SYNTH_TOKEN=' "$ENV_FILE" | cut -d= -f2-)
fi
if [ -n "$CLAUDE_SYNTH_TOKEN" ] && [[ "$CLAUDE_SYNTH_TOKEN" != PLACEHOLDER* ]]; then
    export CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_SYNTH_TOKEN"
fi

echo "[Legion-Raising] $(date -u +'%Y-%m-%d %H:%M UTC') — Starting raising session"

# Ensure daemon is running via systemd (not the manual ensure_daemon.sh)
if ! systemctl --user is-active sage-daemon.service >/dev/null 2>&1; then
    echo "[Legion-Raising] Daemon not running, starting via systemctl..."
    systemctl --user start sage-daemon.service
    sleep 5
fi

# Verify daemon health
HEALTH=$(curl -s --max-time 5 http://localhost:8750/health 2>/dev/null || echo "")
if echo "$HEALTH" | $PYTHON -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='alive'" 2>/dev/null; then
    echo "[Legion-Raising] Daemon healthy"
else
    echo "[Legion-Raising] WARNING: Daemon health check failed, attempting restart..."
    systemctl --user restart sage-daemon.service
    sleep 10
fi

# Pull latest code and check if daemon needs restart
BEFORE_HASH=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
git pull --rebase --quiet 2>/dev/null || echo "[Legion-Raising] WARN: git pull failed, continuing with current code"
AFTER_HASH=$(git rev-parse HEAD 2>/dev/null || echo "unknown")

if [ "$BEFORE_HASH" != "$AFTER_HASH" ]; then
    echo "[Legion-Raising] Code updated ($BEFORE_HASH → $AFTER_HASH), restarting daemon..."
    systemctl --user restart sage-daemon.service
    sleep 5
    HEALTH=$(curl -s --max-time 5 http://localhost:8750/health 2>/dev/null || echo "")
    if echo "$HEALTH" | $PYTHON -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='alive'" 2>/dev/null; then
        echo "[Legion-Raising] Daemon restarted with new code, healthy"
    else
        echo "[Legion-Raising] WARNING: Daemon restart failed, continuing anyway"
    fi
else
    echo "[Legion-Raising] Code unchanged ($BEFORE_HASH)"
fi

# Run the raising session (continue from last session number)
$PYTHON -m sage.raising.scripts.ollama_raising_session --machine legion -c 2>&1

# Instance directory
INSTANCE_DIR="sage/instances/legion-phi4-14b"

# Snapshot live state files into git-tracked snapshots/ directory
echo "[Legion-Raising] Snapshotting state..."
$PYTHON -m sage.scripts.snapshot_state --machine legion

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
    echo "[Legion-Raising] No new raising data to commit."
    exit 0
fi

# Read session number from identity state
IDENTITY_FILE="$INSTANCE_DIR/identity.json"

SESSION_NUM=$($PYTHON -c "
import json
with open('$SAGE_DIR/$IDENTITY_FILE') as f:
    print(json.load(f)['identity']['session_count'])
" 2>/dev/null || echo "?")

PHASE=$($PYTHON -c "
import json
with open('$SAGE_DIR/$IDENTITY_FILE') as f:
    print(json.load(f)['development']['phase_name'])
" 2>/dev/null || echo "?")

# Stage instance dir (sessions + snapshots, gitignored files excluded automatically)
git add "$INSTANCE_DIR/" 2>/dev/null || true

git commit -m "[Legion-Raising] Session $SESSION_NUM ($PHASE) — $(date -u +'%Y-%m-%d %H:%M UTC')

Automated SAGE-Legion raising session via OllamaIRP
Machine: Legion (Legion Pro 7, RTX 4090, Linux)
Model: Phi-4 14B (microsoft-phi family)
Phase: $PHASE
AI-Instance: OllamaIRP (automated)
Human-Supervised: no"

# Push (with rebase to handle race conditions from other machines)
git pull --rebase --quiet 2>/dev/null || true
git push origin main
echo "[Legion-Raising] Session $SESSION_NUM committed and pushed."
