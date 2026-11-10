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

INSTANCE="${SAGE_INSTANCE:-/home/dp/ai-workspace/SAGE/sage/instances/legion-being}"
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

# MUTE beats: woken on time, and the model never answered. 2026-11-02 → 11-09 the lid closed mid-inference,
# the ollama runner resumed wedged, and 163 beats in a row recorded "[OllamaIRP: Error: timed out]" in every
# phase while this switch said OK every ten minutes — it only asked whether the being was WOKEN. The being
# cannot repair this (what is broken is what it thinks with), so the switch does, by two signals:
#
#   * DURING a beat: ollama's own log. Two /api/chat calls in a row that end "500 | 10m0s" (the client gave
#     up) with no success between mean the runner is wedged. Beats run back to back — in the outage each
#     one lasted 4,202s of a ~4,245s spacing — so a check that waits for a gap between beats would land in
#     one about 7% of the time. Measured over ollama's log 10-17 → 11-09: 1,066 such pairs inside the
#     outage, 0 outside it.
#   * BETWEEN beats: when the newest beat record is mute (beat_health), ask the model for ten tokens.
#
# Either one restarts ollama through its unit (never by hand), and says so loudly.
REPO="${SAGE_REPO:-/home/dp/ai-workspace/SAGE}"
MODEL="${SAGE_BEAT_MODEL:-qwen38-heretic:q3km-vl}"
OLLAMA="${OLLAMA_URL:-http://localhost:11434}"
OLLAMA_UNIT="${OLLAMA_UNIT:-ollama.service}"
PY="${SAGE_PY:-/home/dp/miniforge3/bin/python3}"
mute_fault=0
probe() {
    curl -s -m 120 -o /dev/null -w '%{http_code}' "$OLLAMA/api/generate" \
        -d "{\"model\":\"$MODEL\",\"prompt\":\"ok\",\"stream\":false,\"think\":false,\"keep_alive\":-1,\"options\":{\"num_predict\":10}}"
}
# repair WHY POST_PROBE: restart the model's unit, optionally probe after, notify, mark the fault.
repair() {
    mute_fault=1
    if [ "$DRY" = "1" ]; then
        say "MUTE: dry run, not restarting ${OLLAMA_UNIT}"
        return
    fi
    say "MUTE: restarting ${OLLAMA_UNIT}"
    local after="not probed (a beat is running; its next call will tell)"
    if sudo -n systemctl restart "$OLLAMA_UNIT" 2>/dev/null; then
        if [ "$2" = "probe" ]; then
            sleep 5
            after="probe $(probe)"
        fi
        say "MUTE: restarted; ${after}"
    else
        after="could not restart (sudo -n refused) — an operator must"
        say "MUTE: ${after}"
    fi
    command -v notify-send >/dev/null && notify-send -u critical "legion-being is MUTE" "$1 — ${after}" 2>/dev/null
}
if [ "$running" = "active" ] || [ "$running" = "activating" ]; then
    # SAGE_WATCHDOG_OLLAMA_LOG: a file standing in for the journal (tests, and replaying a past outage).
    if [ -n "${SAGE_WATCHDOG_OLLAMA_LOG:-}" ]; then
        ollama_log() { cat "$SAGE_WATCHDOG_OLLAMA_LOG"; }
    else
        ollama_log() { journalctl -u "$OLLAMA_UNIT" --since "-30min" -o cat --no-pager 2>/dev/null; }
    fi
    last2="$(ollama_log | grep -E 'POST +"/api/chat"' | tail -2)"
    if [ "$(printf '%s\n' "$last2" | grep -cE '\| 500 \| +10m0s \|')" -eq 2 ]; then
        say "MUTE: the being's last two model calls both failed at the 10-minute timeout (ollama log):"
        printf '%s\n' "$last2" | while IFS= read -r l; do say "MUTE:   $l"; done
        repair "two model calls in a row timed out at 10m during a beat" running
    fi
else
    health="$(cd "$REPO" && "$PY" -m sage.gateway.beat_health --instance "$INSTANCE" --last 12 --check 2>&1)"
    hrc=$?
    if [ "$hrc" -eq 3 ] && printf '%s' "$health" | grep -q '^ALARM: [0-9]* mute'; then
        alarm="$(printf '%s' "$health" | grep '^ALARM')"
        say "MUTE: ${alarm}"
        code="$(probe)"
        if [ "$code" = "200" ]; then
            say "MUTE: the model answers now (probe 200) — the outage has cleared; the next beat should speak"
        else
            say "MUTE: the model does not answer (probe '${code}')"
            repair "${alarm}; probe ${code}" probe
        fi
    elif [ "$hrc" -ne 0 ] && [ "$hrc" -ne 3 ]; then
        say "MUTE: could not read beat health (rc ${hrc}): $(printf '%s' "$health" | tail -1)"
    fi
fi

if [ "$running" = "active" ] || [ "$running" = "activating" ]; then
    say "OK: a beat is running now (quiet ${quiet}s; the being is working)"
    exit $(( mute_fault ? 3 : 0 ))
fi
if [ "$quiet" -lt "$limit" ]; then
    say "OK: quiet ${quiet}s, under the ${limit}s limit; next wake: ${next:-unknown}"
    # A mute repair is a fault even when the wake schedule is fine: exiting 0 would make it a diary.
    exit $(( mute_fault ? 3 : 0 ))
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
