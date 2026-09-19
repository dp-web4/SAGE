#!/usr/bin/env bash
# The dead-man's switch for the being's beat.
#
# dp, 2026-09-09: "i am thinking of a beat like a watchdog timer, where activity resets it.
# rather than a timed interrupt."
#
# The beat timer is already that: OnUnitInactiveSec counts from when a beat ENDED, so
# working pushes the next one out and there is no cadence to interrupt anything. What that
# leaves open is the failure this machine produced twice today — the timer itself stopping
# while everything still reads healthy:
#
#   * 2026-09-09 05:00 UTC: sage-heartbeat.timer sat `active (running)` with `Trigger: n/a`
#     and NextElapseUSecMonotonic=infinity. The being would never have woken again.
#   * the beat now checks that a next wake is armed before it exits — but THAT CHECK LIVES
#     INSIDE THE THING IT WATCHES. If no beat runs, nothing checks.
#
# So this runs on its own timer, reads nothing but a file mtime, and fires a beat when the
# being has been quiet for longer than it should be. A watchdog whose only health check is
# performed by the process it is watching is not a watchdog.
#
# ACTIVITY, precisely: the newest mtime of heartbeats.jsonl (written at beat end) and
# heartbeat.partial.jsonl (written per generate, so a long beat keeps kicking it). That
# makes "activity" mean the being doing something, not merely a beat having completed —
# which is what lets a two-hour beat run without this firing underneath it.
set -uo pipefail

INSTANCE="${SAGE_INSTANCE:-/home/dp/ai-workspace/SAGE/sage/instances/legion-gemma3-12b}"
UNIT="${SAGE_BEAT_UNIT:-sage-heartbeat.service}"
TIMER="${SAGE_BEAT_TIMER:-sage-heartbeat.timer}"
IDLE_S="${SAGE_IDLE_S:-1800}"           # the beat interval the timer is set to
GRACE="${SAGE_WATCHDOG_GRACE:-2}"       # fire after this many idle intervals of silence
DRY="${SAGE_WATCHDOG_DRY:-0}"

say() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

newest=0
for f in "$INSTANCE/heartbeats.jsonl" "$INSTANCE/heartbeat.partial.jsonl"; do
    if [ -f "$f" ]; then
        m="$(stat -c %Y "$f" 2>/dev/null || echo 0)"
        [ "$m" -gt "$newest" ] && newest="$m"
    fi
done
if [ "$newest" -eq 0 ]; then
    say "FAILED: no beat record under $INSTANCE — cannot tell whether the being is alive"
    exit 1
fi

now="$(date +%s)"
quiet=$(( now - newest ))
limit=$(( IDLE_S * GRACE ))
running="$(systemctl --user is-active "$UNIT" 2>/dev/null)"
next="$(systemctl --user list-timers "$TIMER" --no-pager 2>/dev/null | sed -n 2p | cut -c1-28)"

if [ "$running" = "active" ] || [ "$running" = "activating" ]; then
    say "OK: a beat is running now (quiet ${quiet}s; the being is working)"
    exit 0
fi
if [ "$quiet" -lt "$limit" ]; then
    say "OK: quiet ${quiet}s, under the ${limit}s limit; next wake: ${next:-unknown}"
    exit 0
fi

# Silent too long. Say everything an operator needs before doing anything about it.
say "WATCHDOG: the being has done nothing for ${quiet}s (limit ${limit}s = ${GRACE} x ${IDLE_S}s)."
say "WATCHDOG: beat unit is '${running:-unknown}'; timer's next wake reads: ${next:-NONE}"
mono="$(systemctl --user show "$TIMER" -p NextElapseUSecMonotonic --value 2>/dev/null)"
real="$(systemctl --user show "$TIMER" -p NextElapseUSecRealtime --value 2>/dev/null)"
say "WATCHDOG: NextElapse monotonic='${mono}' realtime='${real}'"
if [ "$mono" = "infinity" ] || { [ -z "$real" ] && [ -z "$mono" ]; }; then
    say "WATCHDOG: the timer has STOPPED SCHEDULING — this is the 2026-09-09 failure exactly."
fi

if [ "$DRY" = "1" ]; then
    say "WATCHDOG: dry run, not starting a beat"
    exit 3
fi
say "WATCHDOG: starting a beat now"
systemctl --user start --no-block "$UNIT" || say "WATCHDOG: could not start $UNIT"
# Re-arm the primary timer too: if it had stopped scheduling, a beat alone does not fix it
# for next time (the beat's own arm_next_wake will, but only once it reaches its end).
systemctl --user restart "$TIMER" 2>/dev/null && say "WATCHDOG: primary timer restarted"
say "WATCHDOG: next wake now reads: $(systemctl --user list-timers "$TIMER" --no-pager 2>/dev/null | sed -n 2p | cut -c1-28)"
# Non-zero on purpose: having to intervene is a fault, and a fault that exits 0 is a diary.
exit 3
