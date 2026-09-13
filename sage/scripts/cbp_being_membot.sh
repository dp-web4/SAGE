#!/bin/bash
# cbp-being's OWN long-term memory: a membot brain-cartridge server on its own port (8010) with
# its own cartridge mount, exactly as sage/gateway/systemd/membot-being.service.example prescribes.
# Never share the seat sessions' membot: their conversation hooks write into whatever cartridge is
# mounted there (measured on Legion 2026-09-03). The port separates processes; --mount separates
# memories, and the mount is the one that matters.
# Run from cron @reboot (this box runs its being from cron; see cbp_heartbeat.sh) or by hand:
#   sage/scripts/cbp_being_membot.sh            # start if not running
#   sage/scripts/cbp_being_membot.sh status
MEMBOT_DIR="/home/dp/ai-workspace/membot"
PORT=8010
MOUNT="cbp-being"
LOG="/home/dp/ai-workspace/SAGE/sage/instances/cbp-qwen3.8-distill-4b/membot.log"
export HOME=/home/dp
export MEMBOT_EMBED_BACKEND=auto
export PYTHONUNBUFFERED=1
pid=$(lsof -t -i :$PORT 2>/dev/null | head -1)
case "${1:-start}" in
  status) [ -n "$pid" ] && echo "membot for $MOUNT: running pid $pid on :$PORT" || echo "membot for $MOUNT: not running"; exit 0;;
  stop)   [ -n "$pid" ] && kill "$pid" && echo "stopped $pid"; exit 0;;
esac
if [ -n "$pid" ]; then echo "already running pid $pid on :$PORT"; exit 0; fi
cd "$MEMBOT_DIR" || { echo "no $MEMBOT_DIR"; exit 1; }
nohup "$MEMBOT_DIR/.venv/bin/python" membot_server.py --transport http --port $PORT --writable --mount "$MOUNT" >> "$LOG" 2>&1 &
sleep 3
pid=$(lsof -t -i :$PORT 2>/dev/null | head -1)
[ -n "$pid" ] && echo "started membot for $MOUNT: pid $pid on :$PORT (log: $LOG)" || { echo "failed to start; see $LOG"; tail -20 "$LOG"; exit 1; }
