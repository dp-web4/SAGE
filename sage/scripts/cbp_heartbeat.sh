#!/bin/bash
# CBP being heartbeat: one governed exploration beat for member `cbp-being`.
# Cron every 30 min (this box runs its raising from cron too; the systemd user bus is not
# reachable from cron-fired seats here, see sage/gateway/systemd/sage-heartbeat.service.example).
# Needs: the hestia daemon (the member connects to it), ollama serving qwen3.8-distill:4b.
# Long-term memory (recall/remember) needs the being's OWN membot on port 8010 with
# `--mount cbp-being` (membot-being.service.example); until that runs, those two effectors
# fail per call and the beat continues.
set -o pipefail
SAGE_DIR="/home/dp/ai-workspace/SAGE"
INSTANCE="sage/instances/cbp-qwen3.8-distill-4b"
MODEL="qwen3.8-distill:4b"
LOG="$SAGE_DIR/$INSTANCE/heartbeat.log"
export HOME=/home/dp
export PATH="/home/dp/.local/bin:/usr/local/bin:/usr/bin:/bin"
export PYTHONUNBUFFERED=1
cd "$SAGE_DIR" || exit 1

# GPU courtesy windows (scheme: shared-context/machines/cbp-gpu-windows.md). A bounded,
# self-expiring suspension: if a requester holds the window, this beat rests and says so.
# The window NEVER unloads the being's model (the 2026-09-13 policy) — it defers beats only.
# An expired or malformed window is ignored, so a forgotten window cannot strand the being.
WINDOW="/home/dp/.local/state/cbp-gpu-window"
if [ -f "$WINDOW" ]; then
    w_until="$(sed -n 's/^until_epoch=//p' "$WINDOW" 2>/dev/null | head -1)"
    w_holder="$(sed -n 's/^holder=//p' "$WINDOW" 2>/dev/null | head -1)"
    w_reason="$(sed -n 's/^reason=//p' "$WINDOW" 2>/dev/null | head -1)"
    if [ -n "$w_until" ] && [ "$w_until" -eq "$w_until" ] 2>/dev/null \
       && [ "$(date +%s)" -lt "$w_until" ]; then
        echo "[cbp-heartbeat] $(date -u +'%Y-%m-%dT%H:%MZ') resting: GPU window held by ${w_holder:-unknown} until $(date -u -d @"$w_until" +'%H:%MZ' 2>/dev/null) (${w_reason:-no reason given})" >> "$LOG"
        exit 0
    fi
fi

if ! curl -s -m 5 http://localhost:11434/api/tags >/dev/null; then
    echo "[cbp-heartbeat] $(date -u +'%Y-%m-%dT%H:%MZ') ollama not responding; skipping beat" >> "$LOG"
    exit 0
fi
echo "[cbp-heartbeat] $(date -u +'%Y-%m-%dT%H:%MZ') beat start" >> "$LOG"
timeout 1500 python3 -m sage.gateway.heartbeat \
    --member cbp-being --model "$MODEL" --instance "$INSTANCE" --max-steps 8 "$@" >> "$LOG" 2>&1
echo "[cbp-heartbeat] $(date -u +'%Y-%m-%dT%H:%MZ') beat end rc=$?" >> "$LOG"
