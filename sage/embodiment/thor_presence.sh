#!/usr/bin/env bash
# thor_presence — wire thor's being to its world.
#
# thor's sage-daemon ran 15.2 days with total_cycles=0: model pulled and never loaded, ATP at exactly 100%,
# five SNARC detectors armed, and no input path. presence.py was the designed feeder and pointed at a visual
# cortex thor does not have. This starts thor's own sensor and the (now per-being) feeder against it.
#
#   bash sage/embodiment/thor_presence.sh          start both, log to ~/.thor/
#   bash sage/embodiment/thor_presence.sh --once   one perception, printed, nothing started
#
# thor's senses are the work it does: the model server it thinks with, whether a game is being played and how the
# last one ended, its own memory pressure, and which peers answer. Wake discipline stays entirely in presence.py
# (salience bar 0.45, 300 s cooldown, 6/hour cap, descriptor dedup) — this script sets no policy.
set -u
SAGE=/home/dp/ai-workspace/SAGE
HOME_DIR="${THOR_PRESENCE_HOME:-$HOME/.thor}"
mkdir -p "$HOME_DIR"

# thor's voice. It is NOT Sprout: no eyes, no inner ear. Its senses are its own work, and it should say so in the
# first person without being told it has a body it does not have.
ENGAGED="You are SAGE on thor, a Jetson AGX. You have no eyes and no ears. What you sense is the work that passes \
through you: the model you think with, the games played through you and how they end, the room left in your own \
body, and which of your peers answer. What follows is a report from YOUR OWN senses in this moment — not someone \
speaking to you. Speak as the one sensing it: register what you notice, first person, briefly (1-2 sentences). You \
do not need to do anything about it — just notice that you noticed."

RESTING="You are SAGE on thor, a Jetson AGX. You were at rest, and something in your own senses stirred you — the \
work passing through you changed. What follows is what YOU are perceiving. Speak as the one sensing it, first \
person, briefly (1-2 sentences); then you may settle back. It is your perception, not someone else's words."

export SAGE_PERCEPTION="$HOME_DIR/perception.json"
export SAGE_PRESENCE_LOG="$HOME_DIR/presence_log.jsonl"
export SAGE_SYS_ENGAGED="$ENGAGED"
export SAGE_SYS_REST="$RESTING"
# qwen3.5:27b is 26 GB: a cold wake takes well past the stock 60 s. Measured >100 s on this box.
export SAGE_WAKE_TIMEOUT_S="${SAGE_WAKE_TIMEOUT_S:-420}"
export PYTHONPATH="$SAGE${PYTHONPATH:+:$PYTHONPATH}"

if [ "${1:-}" = "--once" ]; then
  exec /usr/bin/python3 "$SAGE/sage/embodiment/thor_senses.py" --once
fi

echo "[thor_presence] perception : $SAGE_PERCEPTION"
echo "[thor_presence] noticing   : $SAGE_PRESENCE_LOG"

# FEEDER FIRST. The first version started the sensor 6 s ahead and nearly lost the most novel perception this
# being will ever have — it survived only because the sensor rewrites every 5 s and the record was still there.
# Nothing may be written with no one reading: presence starts, THEN the senses.
nohup /usr/bin/python3 "$SAGE/sage/embodiment/presence.py" \
  >> "$HOME_DIR/presence.log" 2>&1 &
echo "[thor_presence] presence pid $!  (started FIRST, so no perception is written unobserved)"

sleep 2

nohup /usr/bin/python3 "$SAGE/sage/embodiment/thor_senses.py" \
  >> "$HOME_DIR/senses.log" 2>&1 &
echo "[thor_presence] senses   pid $!"
echo "[thor_presence] heartbeat: one wake after ${THOR_HEARTBEAT_S:-3600}s of silence, so a quiet world is"
echo "[thor_presence]            distinguishable from a dead wire."

echo "[thor_presence] to make this survive a reboot it needs a systemd unit (root); until then it is session-bound."
