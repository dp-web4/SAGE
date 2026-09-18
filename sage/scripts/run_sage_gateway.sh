#!/usr/bin/env bash
# run_sage_gateway.sh — launchd entrypoint for the Python gateway daemon.
#
# Exists because a .plist cannot source a resolver. com.web4.sage.mcnugget
# hardcoded /opt/homebrew/bin/python3 in ProgramArguments, which is the same
# fragility that killed raising for 29 days when brew unlinked python@3.14 —
# except a plist fails even more quietly, since launchd just records exit=1.
#
# It also fixes a second bug. The plist pairs KeepAlive=true with
# ThrottleInterval=10, and launchd respawns on ANY exit, success included. So a
# transient shutdown race — new instance starting before the old one released
# the port — became a permanent 10-second crash loop: 8417 "OSError: [Errno 48]
# Address already in use" and a 16MB error log. Waiting for the port to clear
# turns that storm into a quiet wait.
set -u
cd "$(dirname "$0")/../.." || exit 1          # -> SAGE repo root
. sage/scripts/resolve_python.sh || exit 1

PORT="${SAGE_GATEWAY_PORT:-8750}"
for _ in $(seq 1 60); do
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 || break
    sleep 2
done
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "run_sage_gateway: port $PORT still held after 120s by PID(s) $(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN | tr '\n' ' ')— not starting a second gateway." >&2
    exit 0
fi
echo "run_sage_gateway: starting gateway on :$PORT via $SAGE_PY"
exec "$SAGE_PY" -m sage.gateway.sage_daemon
