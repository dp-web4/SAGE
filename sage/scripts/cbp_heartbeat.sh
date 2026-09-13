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
if ! curl -s -m 5 http://localhost:11434/api/tags >/dev/null; then
    echo "[cbp-heartbeat] $(date -u +'%Y-%m-%dT%H:%MZ') ollama not responding; skipping beat" >> "$LOG"
    exit 0
fi
echo "[cbp-heartbeat] $(date -u +'%Y-%m-%dT%H:%MZ') beat start" >> "$LOG"
timeout 1500 python3 -m sage.gateway.heartbeat \
    --member cbp-being --model "$MODEL" --instance "$INSTANCE" --max-steps 8 "$@" >> "$LOG" 2>&1
echo "[cbp-heartbeat] $(date -u +'%Y-%m-%dT%H:%MZ') beat end rc=$?" >> "$LOG"
