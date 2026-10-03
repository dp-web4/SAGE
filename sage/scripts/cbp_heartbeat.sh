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
# The window defers beats; it does not keep the being's model resident (measured 2026-09-30:
# a window's run and the being's model do not fit together, so the holder has the GPU and the
# being's model reloads at its next beat). An expired or malformed window is ignored, so a
# forgotten window cannot strand the being.
# sage.gateway.gpu_window does the check (exit 3 = held). While resting it reports
# rest/heartbeat:gpu-window:<holder> to the daemon and, if events are pending (SAGE #295), arms
# a beat for the window's end. Any other exit, a crash included, runs the beat (fails open).
# The installed unit runs heartbeat.py directly (since 2026-09-28), not this script; the same
# check goes in the unit as an ExecCondition (sage-heartbeat.service.example).
WINDOW="/home/dp/.local/state/cbp-gpu-window"
python3 -m sage.gateway.gpu_window check --window "$WINDOW" >> "$LOG" 2>&1
if [ $? -eq 3 ]; then
    exit 0
fi

if ! curl -s -m 5 http://localhost:11434/api/tags >/dev/null; then
    echo "[cbp-heartbeat] $(date -u +'%Y-%m-%dT%H:%MZ') ollama not responding; skipping beat" >> "$LOG"
    exit 0
fi
echo "[cbp-heartbeat] $(date -u +'%Y-%m-%dT%H:%MZ') beat start" >> "$LOG"
timeout 1500 python3 -m sage.gateway.heartbeat \
    --member cbp-being --model "$MODEL" --instance "$INSTANCE" --max-steps 8 "$@" >> "$LOG" 2>&1
echo "[cbp-heartbeat] $(date -u +'%Y-%m-%dT%H:%MZ') beat end rc=$?" >> "$LOG"
