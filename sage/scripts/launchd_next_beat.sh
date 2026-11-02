#!/bin/sh
# launchd_next_beat.sh — macOS successor: start the next beat as soon as the running one ends.
#
# The systemd seats arm a transient unit ordered After= the beat unit (sage.gateway.arousal
# arm_next). launchd has neither, and a helper process the beat starts is killed with the beat's
# job. So arm_next drops a file named for the heartbeat label into a QueueDirectories folder, and
# launchd starts THIS script, from its own agent, while that folder is not empty
# (sage/gateway/launchd/com.web4.sage-heartbeat-next.plist.example).
#
# It waits while the beat is running, removes the label's queue file, then kickstarts the beat
# (no -k: a running beat is never killed). The file goes BEFORE the kickstart: a request that
# lands after this point writes a new file and runs this again, so it is never lost. At worst it
# costs one extra beat for an event the just-started beat already claimed.
#
#   usage: launchd_next_beat.sh <heartbeat label> <queue dir> [max wait seconds]
set -u
LABEL="${1:?heartbeat label}"
QUEUE="${2:?queue dir}"
MAX="${3:-7200}"
LAUNCHCTL="${LAUNCHCTL:-launchctl}"   # test hook
SLEEP_S="${SLEEP_S:-2}"               # test hook
TARGET="gui/$(id -u)/$LABEL"

say() { echo "$(date -u +%FT%TZ) [next-beat] $*"; }

state() { "$LAUNCHCTL" print "$TARGET" 2>/dev/null | awk -F' = ' '$1 ~ /^[[:space:]]*state$/ { print $2; exit }'; }

[ -e "$QUEUE/$LABEL" ] || { say "nothing queued for $LABEL"; exit 0; }

waited=0
while [ "$(state)" = "running" ]; do
  if [ "$waited" -ge "$MAX" ]; then
    say "beat still running after ${MAX}s; leaving the request queued"
    exit 1
  fi
  sleep "$SLEEP_S"
  waited=$((waited + SLEEP_S))
done

rm -f "$QUEUE/$LABEL"
if "$LAUNCHCTL" kickstart "$TARGET"; then
  say "beat ended (waited ${waited}s); kickstarted $LABEL"
else
  rc=$?
  say "kickstart $LABEL failed (exit $rc); the event stays pending for the watchdog beat"
fi
exit 0
