#!/bin/bash
# CBP SAGE raising session + auto-commit
# Runs a raising session, snapshots state, commits results, pushes to origin.
# Schedule: every 6 hours via crontab (1,7,13,19 — offset from other machines).

set -e

SAGE_DIR="/home/dp/ai-workspace/SAGE"
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
    # Track whether THIS run actually stashed anything; only pop if so.
    # Unconditional `git stash pop` could pop a stale stash from a prior
    # run and silently inject merge markers into the working tree.
    STASH_BEFORE=$(git stash list | wc -l)
    git stash -q 2>/dev/null
    git pull --rebase origin main 2>&1 || {
        echo "[CBP-Raising] WARNING: git pull failed, continuing with local state"
    }
    if [ "$(git stash list | wc -l)" -gt "$STASH_BEFORE" ]; then
        git stash pop -q
    fi
}

# --- Step 2: Ensure Ollama is running ---
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "[CBP-Raising] WARNING: Ollama not responding on port 11434"
    exit 1
fi

# --- Step 3: Ensure daemon is running (sage-rs Rust binary on 8760) ---
# Cutover 2026-06-06: switched from Python sage.gateway.sage_daemon (port 8750,
# ~400-580 MB RSS, interpreted) to sage-rs Rust binary (port 8760, ~12 MB RSS,
# compiled). See shared-context/forum/cbp-sage-rs-sprint7-env-var-paths-2026-06-06.md
# for the cutover note + SAGE/sage-rs/CUTOVER.md for the recipe.
export SAGE_PORT="${SAGE_PORT:-8760}"
export SAGE_NO_BROWSER=1
SAGE_DAEMON_BIN="$SAGE_DIR/sage-rs/target/release/sage-daemon"
DAEMON_PID=$(lsof -t -i :$SAGE_PORT 2>/dev/null || true)
if [ -z "$DAEMON_PID" ]; then
    echo "[CBP-Raising] Starting Rust SAGE daemon (sage-rs)..."
    SAGE_MACHINE=cbp SAGE_MODEL=qwen3.8-distill:4b \
        nohup "$SAGE_DAEMON_BIN" > /tmp/sage-daemon.log 2>&1 &
    sleep 5
fi
# Rust binary is compiled — no interpreter-stale-code restart needed.
# If the binary itself needs an update, rebuild manually via:
#   cd "$SAGE_DIR/sage-rs" && cargo build --release && pkill sage-daemon
# Next cron firing will pick up the new binary cleanly.
echo "[CBP-Raising] Daemon PID: $(lsof -t -i :$SAGE_PORT 2>/dev/null || echo 'not running')"

# --- Step 4: Run the raising session ---
echo "[CBP-Raising] Running raising session..."
python3 -m sage.raising.scripts.ollama_raising_session \
    --machine cbp \
    --model qwen3.8-distill:4b \
    -c 2>&1

# --- Step 5: Snapshot state ---
# Canonical CBP raising model = qwen3.8-distill:4b since 2026-09-12: empero Qwen3.8-4B-Distill
# (Q6_K, MTP head stripped, RENDERER/PARSER qwen3.5), built per sage/scripts/models/README.md.
# Same being as cbp-gemma3-4b (cbp_sage_lct, 240 sessions carried); see that instance's
# MIGRATION.md. 6.0 GB at num_ctx 16384, 100% GPU under the Windows host's ~2.5 GB hold,
# ~40 tok/s, native tools + thinking. gemma3-4b instance retained for rollback + A/B.
# Prior arcs: qwen3.5:0.8b through session 122 (April 29); gemma3:4b sessions 123-240
# (2026-04-18 to 2026-08-06); gemma4:e2b attempted 2026-06-03 (spills ~73% to CPU here).
INSTANCE_DIR="sage/instances/cbp-qwen3.8-distill-4b"

echo "[CBP-Raising] Snapshotting state..."
python3 -m sage.scripts.snapshot_state --machine cbp --model qwen3.8-distill:4b 2>&1 || {
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

# --- Step 6: Dream consolidation (Claude reviews the session) ---
echo "[CBP-Raising] Running dream consolidation..."
python3 -m sage.raising.scripts.dream_consolidation \
    --instance "$INSTANCE_DIR" \
    --session "$SESSION_NUM" 2>&1 || {
    echo "[CBP-Raising] Dream consolidation skipped (claude --print not available or timed out)"
}

# --- Step 7: Regenerate fleet snapshot ---
echo "[CBP-Raising] Updating SESSION_FOCUS.md..."
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

# Stage instance dir + focus
git add "$INSTANCE_DIR/" SESSION_FOCUS.md 2>/dev/null || true

git commit -m "[CBP-Raising] Session $SESSION_NUM ($PHASE) — $(date -u +'%Y-%m-%d %H:%M UTC')

Automated SAGE-CBP raising session via OllamaIRP
Machine: CBP (Desktop RTX 2060 SUPER, WSL2 — single-GPU host)
Model: qwen3.8-distill:4b
Phase: $PHASE
AI-Instance: OllamaIRP (automated)
Human-Supervised: no"

# Push via SSH (PAT is deprecated; ssh-agent has id_ed25519 loaded at session start)
if git push origin main; then
    echo "[CBP-Raising] Session $SESSION_NUM committed and pushed."
else
    echo "[CBP-Raising] ERROR: git push failed — check SSH key is loaded (ssh-add -l)."
fi

echo "[CBP-Raising] $(date -u +'%Y-%m-%d %H:%M UTC') — Done."
