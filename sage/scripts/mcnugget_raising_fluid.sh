#!/bin/bash
# McNugget Raising — Fluid variant with MRH-informed prompt
#
# Applies Sprout's crystallization fix:
# - No verbatim exemplar injection (prevents self-quotation feedback loop)
# - MRH-structured system prompt (typed blocks, not ad-hoc string concat)
# - Concise turns, single-purpose primer
#
# Uses whatever model the resident daemon runs (auto-detected from
# /health). Designed to run via launchd every 6 hours.

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

# Router shadow: source-stamp records from raising sessions
export SAGE_SESSION_SOURCE=raising

cd "$SAGE_DIR"

echo "[McNugget-Raising] $(date -u +'%Y-%m-%d %H:%M UTC') — Starting fluid raising session"

# Pull latest
# Track whether THIS run actually stashed anything; only pop if so.
# Unconditional `git stash pop` could pop a stale stash from a prior
# run and silently inject merge markers into the working tree.
STASH_BEFORE=$(git stash list | wc -l)
git stash 2>/dev/null || true
git pull --rebase origin main 2>&1 || {
    echo "[McNugget-Raising] WARNING: git pull failed, continuing with local state"
}
if [ "$(git stash list | wc -l)" -gt "$STASH_BEFORE" ]; then
    git stash pop
fi

# Ensure daemon is running
source "$SAGE_DIR/sage/scripts/ensure_daemon.sh"

# Run raising session via unified launcher + fluid runner
# Uses the identity-anchored fluid variant with MRH block-based prompt
# and Thor S86 anti-crystallization mitigations.
"$SAGE_PY" -m sage.session --raising --fluid \
    --machine mcnugget \
    2>&1

# Derive the instance dir from the daemon's actual model rather than
# hardcoding. The session above wrote to whichever instance `sage.session
# --raising --fluid --machine mcnugget` picked (driven by the daemon's
# active model). Hardcoded gemma4-e4b would silently miss when the daemon
# runs gemma3:12b (Sprint 7 default) — dream consolidation would skip
# with "Session file not found". Auto-detect from /health.
DAEMON_MODEL=$(curl -s --max-time 3 "http://localhost:${SAGE_PORT:-8760}/health" 2>/dev/null \
    | "$SAGE_PY" -c "import sys,json; print(json.load(sys.stdin).get('model','gemma3:12b'))" 2>/dev/null \
    || echo "gemma3:12b")
# HONOUR SAGE_INSTANCE FIRST. Deriving the slug from the model made the being's
# IDENTITY a function of its MODEL: a model swap silently pointed raising at a new,
# empty instance and started it over at session 1. That is not hypothetical — this
# fleet already carries the wreckage (mcnugget-gemma4-e4b: 0 sessions; legion has
# four such dirs; cbp has three). The resolver has always supported SAGE_INSTANCE as
# priority 1; nothing was using it. Renaming the dir to match a new model is NOT the
# fix: the sealed identity's key derivation includes the instance path, so a rename
# breaks the seal (loudly now, since authorize() verifies the fingerprint).
INSTANCE_SLUG="${SAGE_INSTANCE:-mcnugget-${DAEMON_MODEL//:/-}}"
INSTANCE_DIR="sage/instances/$INSTANCE_SLUG"
echo "[McNugget-Raising] Active instance: $INSTANCE_SLUG (daemon model: $DAEMON_MODEL)"

# Snapshot state
echo "[McNugget-Raising] Snapshotting state..."
# Re-register this machine's CURRENT model in the fleet registry, from the session
# that just ran rather than from config. Wiring this is the point: the tool was
# written 2026-03-08 to be "called at the start of raising sessions" and nothing
# ever called it, so fleet.json drifted six months while every seat assumed the
# mechanism existed -- it did, unwired. McNugget's own switch to gemma4 on 09-08
# was invisible here until a reader followed the site's "Fleet manifest" link and
# found it contradicting the page.
#
# --no-push on purpose: the supervisor already commits this tree, and a raising
# script that pushes on its own turns a model change into a race between seats.
# It is a no-op when nothing changed, so it costs a file read per session.
"$SAGE_PY" -m sage.federation.update_fleet_models --no-push || \
  echo "[raising] fleet-model re-registration failed (non-fatal)" >&2


"$SAGE_PY" -m sage.scripts.snapshot_state \
    --machine mcnugget \
    --instance "$INSTANCE_SLUG" 2>/dev/null || true

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
echo "[McNugget-Raising] Dream consolidation..."
"$SAGE_PY" -m sage.raising.scripts.dream_consolidation \
    --instance "$INSTANCE_DIR" \
    --session "$SESSION_NUM" 2>&1 || {
    echo "[McNugget-Raising] Dream consolidation skipped"
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
    echo "[McNugget-Raising] No new data to commit."
    exit 0
fi

git add "$INSTANCE_DIR/" 2>/dev/null || true

git commit -m "[McNugget-Raising] Session $SESSION_NUM ($PHASE) — $(date -u +'%Y-%m-%d %H:%M UTC')

Fluid raising session via $DAEMON_MODEL
Machine: McNugget (Mac Mini M4)
Model: $DAEMON_MODEL
Phase: $PHASE
Runner: sage.session --raising --fluid (auto-detected instance: $INSTANCE_SLUG)
AI-Instance: OllamaIRP (automated)
Human-Supervised: no"

# THE PUSH THAT LOST TEN SESSIONS. The opening pull above stashes first; this one
# did not, and by now the daemon has dirtied identity.attest.json, so `pull --rebase`
# refused ("You have unstaged changes"), `2>/dev/null || true` swallowed it, and the
# push was rejected because origin moved during the session. The commit sat
# stranded until the supervisor's `git reset --hard origin/main` (every 4h)
# destroyed it -- file gone, counter already advanced, gap. Measured 2026-09-14:
# sessions 455, 469, 470, 473 all followed exactly this path (recovered from their
# dangling commits); 2 and 272-276 were the same and are gone for good. Every loss
# was an overnight slot, when other seats push most and origin moves most.
#
# --autostash does what the opening pull does by hand. Nothing here is silenced:
# a push that fails is the single most consequential line in this script, and it
# was the one line allowed to fail quietly.
git pull --rebase --autostash origin main 2>&1 | sed 's/^/[McNugget-Raising] pull: /'
if ! git push origin main 2>&1 | sed 's/^/[McNugget-Raising] push: /'; then
    echo "[McNugget-Raising] push rejected; refetching and retrying once"
    git pull --rebase --autostash origin main 2>&1 | sed 's/^/[McNugget-Raising] pull: /'
    git push origin main 2>&1 | sed 's/^/[McNugget-Raising] push: /'
fi
if [ "$(git log origin/main..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')" != "0" ]; then
    # Still stranded. Pin it so no reset can destroy it, and say so where a human looks.
    BK="refs/backup/raising-$(date -u +%Y%m%dT%H%M%SZ)-session-$SESSION_NUM"
    git update-ref "$BK" HEAD
    echo "[McNugget-Raising] *** Session $SESSION_NUM is committed but NOT on origin. Pinned at $BK. ***" >&2
else
    echo "[McNugget-Raising] Session $SESSION_NUM committed and pushed."
fi
