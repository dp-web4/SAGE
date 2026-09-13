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
# Embedder: on this box the being's 4B model holds ~6 GB of the 8 GB card at 16k context, so
# ollama cannot also hold nomic-embed-text during a beat; the swap made the first remember
# time out (2026-09-12). `st` = sentence-transformers in the membot venv, CPU, ~2 GB RAM of
# the 32 GB here, no GPU contention. Needs `pip install sentence-transformers` in that venv.
export MEMBOT_EMBED_BACKEND="${MEMBOT_EMBED_BACKEND:-st}"
# The being takes priority for the GPU (dp 2026-09-13): torch must never see the card.
export CUDA_VISIBLE_DEVICES=
export PYTHONUNBUFFERED=1
pid=$(lsof -t -i :$PORT 2>/dev/null | head -1)
case "${1:-start}" in
  status) [ -n "$pid" ] && echo "membot for $MOUNT: running pid $pid on :$PORT" || echo "membot for $MOUNT: not running"; exit 0;;
  stop)   [ -n "$pid" ] && kill "$pid" && echo "stopped $pid"; exit 0;;
esac
if [ -n "$pid" ]; then echo "already running pid $pid on :$PORT"; exit 0; fi
cd "$MEMBOT_DIR" || { echo "no $MEMBOT_DIR"; exit 1; }
# Loopback bind, as on Nomad: the server default 0.0.0.0 would put a WRITABLE memory store on the tailnet.
nohup "$MEMBOT_DIR/.venv/bin/python" membot_server.py --transport http --host 127.0.0.1 --port $PORT --writable --mount "$MOUNT" >> "$LOG" 2>&1 &
# Warm the embedder now, not on the being's first remember (cold load timed it out on Nomad and here).
# membot machines/nomad/warm_membot.py dials 127.0.0.1:8010 and mounts the named cartridge; failure never blocks.
"$MEMBOT_DIR/.venv/bin/python" "$MEMBOT_DIR/machines/nomad/warm_membot.py" "$MOUNT" >> "$LOG" 2>&1 || true
pid=$(lsof -t -i :$PORT 2>/dev/null | head -1)
[ -n "$pid" ] && echo "started membot for $MOUNT: pid $pid on :$PORT (log: $LOG)" || { echo "failed to start; see $LOG"; tail -20 "$LOG"; exit 1; }
