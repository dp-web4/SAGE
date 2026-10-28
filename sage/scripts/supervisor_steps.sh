# supervisor_steps.sh — sourced by mcnugget_supervisor.sh (and its tests). Each function runs ONE step,
# keeps that step's exit status, and reports success only on the step's own documented success line.
#
# WHY (NOVA's HOLD on #513, 2026-10-22..28): the supervisor ran these as `$(bash … 2>&1 | tail -1)` under
# `set -u` alone. The trailing `tail` succeeded whatever the script exited, and the fleet line took any
# 40-hex string off whatever the last line was, so a refused snapshot, or a worktree sync that stopped on
# the being's work, could be logged as fresh. A stranded worktree already cost McNugget three weeks.
#
# Contract of every function here:
#   stdout: ONE status token for the fleet line ("hestia 519ac557", "hestia FAILED (rc=3)", ...)
#   stderr: the step's FULL output, untrimmed, for the local log
#   exit:   0 when the step succeeded by its own contract, 1 otherwise. Never anything destructive.

# _step_run <outvar> <rcvar> <cmd...>: run cmd capturing stdout+stderr and its OWN exit status (no pipe).
_step_run() {
    local __out __rc
    __out="$("${@:3}" 2>&1)" && __rc=0 || __rc=$?
    printf -v "$1" '%s' "$__out"
    printf -v "$2" '%s' "$__rc"
}

# snapshot_status <label> <prefix> <script>: a governance snapshot. Success = exit 0 AND a line
# "<prefix> now at <40hex>" or "<prefix> already at <40hex>" (governance_snapshot*.sh's own output).
snapshot_status() {
    local label="$1" prefix="$2" script="$3" out rc rev
    if [ ! -f "$script" ]; then
        echo "$label FAILED (script missing: $script)"; return 1
    fi
    _step_run out rc bash "$script"
    printf '[%s snapshot rc=%s]\n%s\n' "$label" "$rc" "$out" >&2
    rev="$(printf '%s\n' "$out" | sed -nE "s/^${prefix} (now|already) at ([0-9a-f]{40})( .*)?$/\\2/p" | tail -n 1)"
    if [ "$rc" -ne 0 ]; then
        echo "$label FAILED (rc=$rc)"; return 1
    fi
    if [ -z "$rev" ]; then
        echo "$label FAILED (rc=0 but no '$prefix now|already at <commit>' line)"; return 1
    fi
    echo "$label ${rev:0:8}"
}

# worktree_status <script> <worktree> <ref> <member>: the being's worktree fast-forward. Success = exit 0
# AND "already at …" or "synced to …" (sync_being_worktree.sh). Its refusals (exit 3-7, "NOT SYNCED: …")
# are reported as NOT SYNCED with the first reason line; the worktree is never touched by this function.
worktree_status() {
    local script="$1" wt="$2" ref="$3" member="$4" out rc ok why
    if [ ! -f "$script" ]; then
        echo "being worktree FAILED (script missing: $script)"; return 1
    fi
    _step_run out rc bash "$script" "$wt" "$ref" "$member"
    printf '[being worktree sync rc=%s]\n%s\n' "$rc" "$out" >&2
    ok="$(printf '%s\n' "$out" | grep -E '^(already at|synced to) ' | tail -n 1)"
    if [ "$rc" -eq 0 ] && [ -n "$ok" ]; then
        echo "being worktree ${ok:0:60}"; return 0
    fi
    why="$(printf '%s\n' "$out" | grep -m1 -E '^NOT SYNCED: ' | cut -c13-72)"
    if [ "$rc" -ne 0 ]; then
        echo "being worktree NOT SYNCED (rc=$rc${why:+: $why})"
    else
        echo "being worktree FAILED (rc=0 but no 'already at|synced to' line)"
    fi
    return 1
}
