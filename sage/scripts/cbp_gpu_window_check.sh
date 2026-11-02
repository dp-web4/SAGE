#!/bin/bash
# ExecCondition for sage-heartbeat.service: may this beat start, under the CBP GPU
# courtesy-window scheme (shared-context/machines/cbp-gpu-windows.md)?
#
#   0 = start (no window held, or the window lapsed — expiry is the default)
#   1 = rest  (a requester holds the window; the beat skips and says why in heartbeat.log)
#
# The window NEVER unloads the being's model (the 2026-09-13 policy); it defers beats only.
# Composes with the movie-pause sentinel (ConditionPathExists): both must pass for a beat.
WINDOW="/home/dp/.local/state/cbp-gpu-window"
LOG="/home/dp/ai-workspace/SAGE/sage/instances/cbp-qwen3.8-distill-4b/heartbeat.log"
[ -f "$WINDOW" ] || exit 0
w_until="$(sed -n 's/^until_epoch=//p' "$WINDOW" 2>/dev/null | head -1)"
w_holder="$(sed -n 's/^holder=//p' "$WINDOW" 2>/dev/null | head -1)"
w_reason="$(sed -n 's/^reason=//p' "$WINDOW" 2>/dev/null | head -1)"
if [ -n "$w_until" ] && [ "$w_until" -eq "$w_until" ] 2>/dev/null \
   && [ "$(date +%s)" -lt "$w_until" ]; then
    echo "[cbp-heartbeat] $(date -u +'%Y-%m-%dT%H:%MZ') resting: GPU window held by ${w_holder:-unknown} until $(date -u -d @"$w_until" +'%H:%MZ' 2>/dev/null) (${w_reason:-no reason given})" >> "$LOG"
    exit 1
fi
exit 0
