#!/usr/bin/env bash
# sage-rs-deploy: keep the RUNNING sage-daemon built from the sage-rs that is on main.
#
# WHY. On 2026-09-18 McNugget's sage-daemon was found running a binary built 2026-06-06:
# fourteen sage-rs commits and three months behind, including the consciousness-loop state
# publishing and the conversations slice the fleet believed was live there. The process had
# even been restarted on 09-07 -- onto the same stale binary, because a restart is not a
# deploy. hestia has had a deploy timer since August and self-updates several times a day on
# the same box; sage-rs had nothing, so the daemon that actually runs the being was the
# stalest thing present and nothing said so. "Merged" is not "in force"; this makes the
# distance between the two a schedule instead of a memory. Shape and vocabulary are
# deliberately hestia-deploy's, so one habit reads both logs.
#
# THE SHAPE
#   $HOME_D/SAGE      the deploy checkout, hard-reset to origin/main every cycle. Nothing else
#                     touches it, which is what makes the reset safe: the same reset on a tree
#                     that sessions commit to destroyed ten raising sessions on this seat.
#   $HOME_D/target    its own cargo target, so a worktree build never contends with a deploy
#                     build and a deployed binary is never stamped -dirty.
#   $SAGE_DAEMON_BIN  the file the unit execs. Default $HOME_D/bin/sage-daemon. This script
#                     never edits unit files; pointing the unit at this path (and setting
#                     SAGE_ROOT, below) is a one-time operator act per seat.
#
# SAGE_ROOT. The daemon finds its DATA root by walking four parents up from its own
# executable (main.rs sage_root). A binary installed outside <root>/sage-rs/target/release
# therefore needs SAGE_ROOT=<the working SAGE repo> in the unit's environment. Binary from the
# clean checkout, data from the working repo: that separation is the point.
#
# WHAT ONE CYCLE DOES. Sync the checkout. TARGET is the newest commit touching sage-rs/ -- not
# HEAD, because SAGE takes raising-session commits all day and restarting a being's daemon for
# a commit that did not change its code is cost with no benefit. The daemon is CURRENT iff
# TARGET is an ancestor of both the running build (/health) and the on-disk build. Otherwise:
# build release, read the new binary's stamp WITHOUT EXECUTING IT, install atomically, restart,
# wait for /health to report the new sha, and roll back to the previous binary if it does not.
#
# NEVER EXECUTE THE BINARY TO ASK ITS VERSION. sage-daemon has no --version flag; running it
# starts a second daemon that defaults SAGE_MACHINE to sprout and resolves another being's
# instance paths. Measured the hard way while writing this. The stamp is read with strings(1).
#
# STAYING OUT OF THE WAY. Only the restart is observable, and only when sage-rs moved. A cycle
# is HELD while a raising session is running (daemon and session both write the instance
# directory) or while $HOME_D/hold exists and is younger than HOLD_MAX_SECS; a held cycle
# retries on the next mark, and a forgotten hold file expires rather than stopping deploys.
#
# Modes:  (none)        full cycle
#         --check       sync + report; exit 0 current, 3 stale, 2 could not determine
#         --build-only  sync + build, no install, no restart
#         anything else usage, exit 2, BEFORE the lock is taken
#
# Exit:   0 current or deployed · 1 failed (rolled back if possible) · 2 usage/undetermined
#         3 stale (--check only) · 4 held

main() {
set -uo pipefail

MODE="${1:-}"
case "$MODE" in ""|--check|--build-only) ;; *)
  echo "usage: sage_rs_deploy.sh [--check|--build-only]" >&2; exit 2 ;; esac

HOME_D="${SAGE_DEPLOY_HOME:-$HOME/.sage-deploy}"
REPO_URL="${SAGE_DEPLOY_REPO_URL:-git@github.com:dp-web4/SAGE.git}"
CK="$HOME_D/SAGE"
export CARGO_TARGET_DIR="$HOME_D/target"
BIN="${SAGE_DAEMON_BIN:-$HOME_D/bin/sage-daemon}"
PORT="${SAGE_PORT:-8760}"
LOG="$HOME_D/deploy.log"
HOLD="$HOME_D/hold"; HOLD_MAX_SECS="${HOLD_MAX_SECS:-21600}"
LOCK="$HOME_D/lock";  LOCK_MAX_SECS=3600
WAIT_SECS="${SAGE_DEPLOY_WAIT_SECS:-90}"
KEEP_PREV=3

case "$(uname -s)" in
  Darwin) DEFAULT_RESTART="launchctl kickstart -k gui/$(id -u)/${SAGE_DEPLOY_LABEL:-com.web4.sage-daemon.$(hostname -s | tr 'A-Z' 'a-z')}" ;;
  *)      DEFAULT_RESTART="systemctl --user restart ${SAGE_DEPLOY_UNIT:-sage-daemon.service}" ;;
esac
RESTART="${SAGE_DEPLOY_RESTART:-$DEFAULT_RESTART}"

mkdir -p "$HOME_D/bin"
say() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG"; }
age() { echo $(( $(date +%s) - $(stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null || echo 0) )); }

# ── lock (mkdir is atomic everywhere; flock is not on macOS) ────────────────────────────
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ "$(age "$LOCK")" -gt "$LOCK_MAX_SECS" ]; then
    say "WARN breaking a lock older than ${LOCK_MAX_SECS}s"; rmdir "$LOCK" 2>/dev/null; mkdir "$LOCK" || exit 2
  else
    say "another cycle holds the lock; skipping"; exit 0
  fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

# ── sync ────────────────────────────────────────────────────────────────────────────────
if [ ! -d "$CK/.git" ]; then
  say "cloning the deploy checkout into $CK"
  git clone -q "$REPO_URL" "$CK" >>"$LOG" 2>&1 || { say "FAIL clone of $REPO_URL"; exit 1; }
fi
git -C "$CK" fetch -q origin >>"$LOG" 2>&1 || { say "FAIL fetch (network?) — not asserting currency"; exit 2; }
git -C "$CK" reset -q --hard origin/main
HEAD9="$(git -C "$CK" rev-parse --short=9 HEAD)"
TARGET="$(git -C "$CK" log -1 --format=%H -- sage-rs/)"
TARGET9="$(git -C "$CK" rev-parse --short=9 "$TARGET")"

# ── what is running, what is on disk — neither by executing the binary ─────────────────
stamp_of() {  # <ver>+<sha9>[-dirty]@<date> embedded by build.rs; read, never run
  [ -f "$1" ] || { echo none; return; }
  # No early-exit reader in this pipeline, on purpose. The first version used `grep -m1 ...
  # || echo unstamped`: grep quit after its match, strings died of SIGPIPE, `pipefail` called
  # that a failure, and the fallback fired ALONGSIDE the real stamp -- every stamp logged as
  # two lines, "0.1.0+<sha>@<date>" then "unstamped". The first deploy still compared the
  # right sha only because sed happened to read line one. `sed -n 1p` consumes all its input.
  local s; s="$(strings "$1" 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\+[0-9a-f]{9}(-dirty)?@[0-9TZ:-]+' | sed -n '1p' || true)"
  echo "${s:-unstamped}"
}
sha_of() { echo "$1" | sed -nE 's/^[^+]*\+([0-9a-f]{9}).*/\1/p'; }
RUNNING="$(curl -s -m 4 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -oE '"build":"[^"]+"' | cut -d'"' -f4)"
RUNNING="${RUNNING:-none}"
ONDISK="$(stamp_of "$BIN")"
covers() {  # is TARGET an ancestor of the build this stamp names?
  local s; s="$(sha_of "$1")"; [ -n "$s" ] || return 1
  case "$1" in *-dirty*) return 1 ;; esac
  git -C "$CK" cat-file -e "$s" 2>/dev/null || return 1
  git -C "$CK" merge-base --is-ancestor "$TARGET" "$s"
}
say "target=$TARGET9 (newest sage-rs commit; main $HEAD9) running=$RUNNING ondisk=$ONDISK bin=$BIN"

if covers "$RUNNING" && covers "$ONDISK"; then
  say "CURRENT $RUNNING"; exit 0
fi
BEHIND="$(git -C "$CK" rev-list --count "$(sha_of "$RUNNING" | grep . || echo "$TARGET")..HEAD" -- sage-rs/ 2>/dev/null || echo '?')"
say "STALE running=$RUNNING ondisk=$ONDISK target=$TARGET9 (running is $BEHIND sage-rs commit(s) behind)"
[ "$MODE" = "--check" ] && exit 3

# ── hold ────────────────────────────────────────────────────────────────────────────────
if [ "$MODE" != "--build-only" ]; then
  if [ -f "$HOLD" ] && [ "$(age "$HOLD")" -lt "$HOLD_MAX_SECS" ]; then
    say "HELD by $HOLD ($(age "$HOLD")s old; expires at ${HOLD_MAX_SECS}s)"; exit 4
  fi
  if pgrep -f 'sage\.session --raising|ollama_raising_session|sage\.raising\.scripts' >/dev/null 2>&1; then
    say "HELD a raising session is running; daemon and session both write the instance directory. Next mark retries."; exit 4
  fi
fi

# ── build ───────────────────────────────────────────────────────────────────────────────
say "build $HEAD9 (release, target dir $CARGO_TARGET_DIR)"
T0=$(date +%s)
if ! (cd "$CK/sage-rs" && cargo build --release -p sage-daemon) >>"$LOG" 2>&1; then
  say "FAIL build of $HEAD9 — the running daemon is untouched"; exit 1
fi
NEW="$CARGO_TARGET_DIR/release/sage-daemon"
NEWSTAMP="$(stamp_of "$NEW")"
say "built $NEWSTAMP in $(( $(date +%s) - T0 ))s"
if [ "$(sha_of "$NEWSTAMP")" != "$HEAD9" ] || ! covers "$NEWSTAMP"; then
  say "FAIL the new binary stamps itself $NEWSTAMP, expected a clean build of $HEAD9 — not installing"; exit 1
fi
[ "$MODE" = "--build-only" ] && exit 0

# ── install: copy beside the destination, re-sign, rename over it ───────────────────────
TS="$(date +%Y%m%d-%H%M%S)"
cp "$NEW" "$BIN.new" || { say "FAIL copy to $BIN.new"; exit 1; }
# cp invalidates the ad-hoc signature on Apple Silicon and the kernel SIGKILLs the result.
[ "$(uname -s)" = "Darwin" ] && codesign --force --sign - "$BIN.new" >>"$LOG" 2>&1
PREV=""
if [ -f "$BIN" ]; then PREV="$BIN.prev-$TS"; cp -p "$BIN" "$PREV"; fi
mv -f "$BIN.new" "$BIN"
say "installed $NEWSTAMP${PREV:+ (previous saved as $(basename "$PREV"))}"

wait_for() {  # poll /health until it reports the sha we expect
  local want="$1" i got
  for i in $(seq 1 "$WAIT_SECS"); do
    got="$(curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -oE '"build":"[^"]+"' | cut -d'"' -f4)"
    [ "$(sha_of "${got:-}")" = "$want" ] && { echo "$i"; return 0; }
    sleep 1
  done; return 1
}
say "restart: $RESTART"
eval "$RESTART" >>"$LOG" 2>&1
if SECS="$(wait_for "$HEAD9")"; then
  say "daemon up on $NEWSTAMP after ${SECS}s"
  say "DEPLOYED $RUNNING -> $NEWSTAMP (sage-rs $TARGET9)"
  ls -t "$BIN".prev-* 2>/dev/null | tail -n +$((KEEP_PREV + 1)) | while read -r old; do rm -f "$old"; done
  exit 0
fi

# ── rollback ────────────────────────────────────────────────────────────────────────────
say "FAIL daemon did not come up on $HEAD9 within ${WAIT_SECS}s"
if [ -n "$PREV" ] && [ -f "$PREV" ]; then
  cp -p "$PREV" "$BIN.new"; [ "$(uname -s)" = "Darwin" ] && codesign --force --sign - "$BIN.new" >>"$LOG" 2>&1
  mv -f "$BIN.new" "$BIN"; eval "$RESTART" >>"$LOG" 2>&1
  if wait_for "$(sha_of "$(stamp_of "$BIN")")" >/dev/null; then say "ROLLBACK restored $(stamp_of "$BIN"); the daemon is serving again"
  else say "ROLLBACK FAILED — the daemon is DOWN on $(stamp_of "$BIN"); needs a human"; fi
else
  say "no previous binary to roll back to — the daemon may be DOWN; needs a human"
fi
exit 1
}
# The whole script is one function so bash has parsed all of it before running any of it: the
# cycle hard-resets the checkout this file may be running from.
main "$@"
