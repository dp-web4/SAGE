#!/bin/bash
# Nomad SAGE raising session + auto-commit
# Runs a GOVERNED raising session, snapshots state, commits results, pushes to origin.
# Schedule: every 6 hours via crontab (0,6,12,18).
#
# v2.0 (2026-04-19): Switched from ollama_raising_session to fluid runner.
# The old runner fed the attractor loop for 25 sessions (S96-S120).
# Fluid runner: no exemplar injection for <=4B, attractor counter-prompting,
# MRH-informed prompt composition.
#
# v3.0 (2026-09-09): Switched BACK to ollama_raising_session, for governance (see the
# step-3 comment). v2.0's finding is not discarded: its exemplar rule is now enforced in
# the canonical runner itself, by parsed model size rather than a substring list that
# could never match `e2b`. What is NOT yet carried across is v2.0's attractor
# counter-prompting, so watch this being for attractor recurrence (S96-S120 is the
# reference shape) and port it if it returns.

set -e

SAGE_DIR="/mnt/c/projects/ai-agents/SAGE"
export PYTHONPATH="$SAGE_DIR"
LOG_DIR="/tmp/nomad-raising-logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/raising-$(date +%Y%m%d-%H%M).log"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "[Nomad-Raising] $(date -u +'%Y-%m-%d %H:%M UTC') — Starting raising session (governed runner)"

cd "$SAGE_DIR"

# --- Step 1: Pull latest code ---
echo "[Nomad-Raising] Pulling latest code..."
git pull --ff-only origin main 2>&1 || {
    echo "[Nomad-Raising] WARNING: git pull --ff-only failed, trying merge..."
    git pull --no-rebase --no-edit origin main 2>&1 || {
        echo "[Nomad-Raising] WARNING: git pull failed, continuing with local state"
    }
}

# --- Step 2: Source router shadow env + ensure daemon (Rust) ---
# Cutover to Rust sage-daemon on 8760 (2026-06-06 evening): Sprout shipped
# the consciousness-identity fix (SAGE @ d44b42765) addressing the "every
# machine speaks as Sprout" issue we flagged earlier today. Python daemon
# retired here.
export SAGE_MACHINE="${SAGE_MACHINE:-nomad}"
export SAGE_MODEL="${SAGE_MODEL:-gemma4:e2b}"
export SAGE_PORT="${SAGE_PORT:-8760}"
export SAGE_NO_BROWSER=1
if [ -f "$SAGE_DIR/sage/gateway/router-shadow.env" ]; then
    set -a; source "$SAGE_DIR/sage/gateway/router-shadow.env"; set +a
    echo "[Nomad-Raising] Router shadow: SAGE_ROUTER_SHADOW=$SAGE_ROUTER_SHADOW"
fi
source "$SAGE_DIR/sage/scripts/ensure_daemon_rs.sh"
echo "[Nomad-Raising] Daemon: version=$SAGE_DAEMON_VERSION running=$SAGE_DAEMON_RUNNING updated=$SAGE_DAEMON_UPDATED"

# --- Step 3: Run the FLUID raising session ---
# Canonical Nomad raising model = gemma4:e2b (per private-context/machines/fleet/nomad.json
# as of 2026-06-03; sweep default also matches raising per fleetwide policy).
# Prior arc raised gemma3:4b through session 172 (sessions/ archived at
# sage/instances/nomad-gemma3-4b.archive-20260603). Switched 2026-06-03 because
# CBP simultaneously moved to gemma3:4b (its RTX 2060 SUPER can't fit e2b — Windows
# compositor holds ~2.2GB), and Nomad's RTX 4060 Laptop fits e2b GPU-only (verified
# at 16k context, 7553/8188 MiB, 100% GPU). Migration preserves fleet model diversity.
# CUTOVER 2026-09-09: from run_session_identity_anchored_fluid.py to the canonical
# ollama_raising_session, which sage/raising/CLAUDE.md already names as the primary-track
# runner ("scripts/ollama_raising_session (via 6-hour cron)"). Nomad was the last machine
# on the identity-anchored runner.
#
# THE REASON IS GOVERNANCE, not tidiness. The old runner's --tools flag executes through
# sage/tools/ create_default_registry, which contains no reference to hestia, the gate or
# the witness chain: web_search, web_fetch and peer_ask all reach off-box with nothing
# judging them and nothing recorded. The canonical runner offers tools through
# _maybe_offer_tools -> BeingGateClient + HestiaF1aDispatcher as member `<machine>-being`,
# so every intent is judged by the shared law and every allowed act is witnessed.
#
# SAGE_TOOLS=1 turns that governed offer on (the flag defaults OFF). It is safe to run
# unattended as of SAGE bc07ef425, which landed the membot store-confirmation guards: an
# unconfirmed store can no longer trigger the destructive save that emptied a peer being's
# cartridge on 2026-09-08.
#
# The runner is stage-agnostic by design: it resolves session count from the snapshot
# identity and computes phase from it, so this being continues where it is rather than
# restarting a curriculum.
export SAGE_TOOLS=1
export SAGE_INSTANCE="${SAGE_INSTANCE:-nomad-gemma4-e2b}"
echo "[Nomad-Raising] Running governed raising session (SAGE_TOOLS=$SAGE_TOOLS)..."
python3 -m sage.raising.scripts.ollama_raising_session \
    --machine nomad \
    --model gemma4:e2b \
    -c \
    2>&1

# --- Step 4: Snapshot state ---
INSTANCE_DIR="sage/instances/nomad-gemma4-e2b"

echo "[Nomad-Raising] Snapshotting state..."
python3 -m sage.scripts.snapshot_state --machine nomad --model gemma4:e2b 2>&1 || {
    echo "[Nomad-Raising] WARNING: snapshot_state failed, continuing"
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

# --- Step 5: Regenerate fleet snapshot ---
echo "[Nomad-Raising] Updating SESSION_FOCUS.md..."
python3 -m sage.scripts.generate_primer 2>/dev/null || true

# --- Step 6: Commit and push ---
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
    echo "[Nomad-Raising] No new raising data to commit."
    exit 0
fi

# Stage instance dir + focus
git add "$INSTANCE_DIR/" SESSION_FOCUS.md SESSION_MAP.yaml 2>/dev/null || true

git commit -m "[Nomad-Raising] Session $SESSION_NUM ($PHASE) — $(date -u +'%Y-%m-%d %H:%M UTC')

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"

# Push via SSH (PAT is deprecated)
git push origin main 2>&1 || {
    echo "[Nomad-Raising] WARNING: push failed, will retry next session"
}

echo "[Nomad-Raising] $(date -u +'%Y-%m-%d %H:%M UTC') — Done."
