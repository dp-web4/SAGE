#!/bin/bash
# CBP SAGE raising session + auto-commit
# Runs a raising session, snapshots state, commits results, pushes to origin.
# Schedule: every 6 hours via crontab (1,7,13,19 — offset from other machines).

set -e

SAGE_DIR="/mnt/c/exe/projects/ai-agents/SAGE"
export PYTHONPATH="$SAGE_DIR"
LOG_DIR="/tmp/cbp-raising-logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/raising-$(date +%Y%m%d-%H%M).log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "[CBP-Raising] $(date -u +'%Y-%m-%d %H:%M UTC') — Starting raising session"

cd "$SAGE_DIR"

# --- Step 1: Pull latest code ---
echo "[CBP-Raising] Pulling latest code..."
git pull --ff-only origin main 2>&1 || {
    echo "[CBP-Raising] WARNING: git pull --ff-only failed, trying rebase..."
    git stash -q 2>/dev/null
    git pull --rebase origin main 2>&1 || {
        echo "[CBP-Raising] WARNING: git pull failed, continuing with local state"
    }
    git stash pop -q 2>/dev/null || true
}

# --- Step 2: Ensure Ollama is running ---
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "[CBP-Raising] WARNING: Ollama not responding on port 11434"
    exit 1
fi

# --- Step 3: Ensure daemon is running and up to date ---
export SAGE_PORT="${SAGE_PORT:-8750}"
export SAGE_NO_BROWSER=1
DAEMON_PID=$(lsof -t -i :$SAGE_PORT 2>/dev/null || true)
if [ -z "$DAEMON_PID" ]; then
    echo "[CBP-Raising] Starting SAGE daemon..."
    nohup python3 -u -m sage.gateway.sage_daemon > /tmp/sage-daemon.log 2>&1 &
    sleep 5
else
    # Check if daemon is running stale code (started before last pull)
    DAEMON_START=$(stat -c %Y /proc/$DAEMON_PID/exe 2>/dev/null || echo 0)
    LAST_COMMIT=$(git log -1 --format=%ct 2>/dev/null || echo 0)
    if [ "$LAST_COMMIT" -gt "$DAEMON_START" ] 2>/dev/null; then
        echo "[CBP-Raising] Daemon is stale — restarting with latest code..."
        kill $DAEMON_PID 2>/dev/null
        sleep 2
        nohup python3 -u -m sage.gateway.sage_daemon > /tmp/sage-daemon.log 2>&1 &
        sleep 5
    fi
fi
echo "[CBP-Raising] Daemon PID: $(lsof -t -i :$SAGE_PORT 2>/dev/null || echo 'not running')"

# --- Step 4: Run the raising session ---
echo "[CBP-Raising] Running raising session..."
python3 -m sage.raising.scripts.ollama_raising_session \
    --machine cbp \
    --model tinyllama:latest \
    --turns 6 \
    -c 2>&1

# --- Step 5: Snapshot state ---
INSTANCE_DIR="sage/instances/cbp-tinyllama-latest"

echo "[CBP-Raising] Snapshotting state..."
python3 -m sage.scripts.snapshot_state --machine cbp 2>&1 || {
    echo "[CBP-Raising] WARNING: snapshot_state failed, continuing"
}

# Read session number and phase from identity
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

# --- Step 6: Regenerate session primer ---
echo "[CBP-Raising] Updating SESSION_PRIMER.md..."
python3 -m sage.scripts.generate_primer 2>/dev/null || true

# --- Step 7: Commit and push ---
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

# Push
PAT=$(grep GITHUB_PAT /mnt/c/exe/projects/ai-agents/.env 2>/dev/null | cut -d= -f2)
if [ -n "$PAT" ]; then
    git push "https://dp-web4:${PAT}@github.com/dp-web4/SAGE.git" main
    echo "[CBP-Raising] Session $SESSION_NUM committed and pushed."
else
    echo "[CBP-Raising] ERROR: No GITHUB_PAT found, cannot push."
fi

echo "[CBP-Raising] $(date -u +'%Y-%m-%d %H:%M UTC') — Done."
