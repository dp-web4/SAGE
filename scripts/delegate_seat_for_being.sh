#!/bin/bash
# Give this machine's seat standing authority to RULE its own being's scope escalations
# (hestia #952), and keep that authority alive. dp, 2026-09-22: "set it up so that you can rule
# being's escalations, i'm seldom here in time to respond ... that should be automatic for being
# escalations, fleet-wide."
#
# The ruling itself is already automatic: escalate.py wakes the seat's auto session, which runs
# `hestia scope arbitrate ... --as <seat>` under the arbiter protocol. What was missing on every
# machine but Legion is the DELEGATION that lets that call succeed. Without it the daemon answers
# hestia.scope_arbitrate_undelegated and the request sits in dp's queue for 8 h, then expires.
#
# Idempotent. Does nothing when a live delegation already covers the being under SAGE_ROOT and is
# not within RENEW_DAYS of expiry. Otherwise: stops the hestia daemon (it holds an exclusive writer
# lease on the vault for its whole life; the CLI cannot write while it runs), grants, vouches the
# seat's operational key once (`witness onboard`, or a ruling's signature does not verify), and
# starts the daemon again.
#
# TRAP, measured on Sprout 2026-09-22: a daemon restart DROPS every pending scope request (they are
# memory-only, 8 h). Run this right after a ruling or when nothing is pending; the timer runs it
# at 04:07 local for that reason. Never run it from inside a beat.
#
# Required (no defaults — a fleet script names nothing it was not told):
#   SAGE_BEING    <machine>-being          the member whose requests this seat may rule
#   SAGE_ROOT     the SAGE checkout the being's requests fall under (its home AND its mis-rooted asks)
#   SEAT          the seat's registry member id, e.g. claude-code
# Optional:
#   HESTIA_UNIT   systemd unit name (default: hestia); HESTIA_SCOPE user|system (default: user)
#   HESTIA_PASSPHRASE_FILE (default: ~/.hestia/.passphrase) — read into the environment of each
#                 hestia call only; never printed
#   EXPIRES_H     delegation lifetime in hours (default 720); RENEW_DAYS renew when closer than this (default 7)
set -euo pipefail
for v in SAGE_BEING SAGE_ROOT SEAT; do [ -n "${!v:-}" ] || { echo "delegate: $v is required" >&2; exit 2; }; done
H="${HESTIA_BIN:-$HOME/.local/bin/hestia}"; UNIT="${HESTIA_UNIT:-hestia}"; SCOPE="${HESTIA_SCOPE:-user}"
PF="${HESTIA_PASSPHRASE_FILE:-$HOME/.hestia/.passphrase}"; EXPIRES_H="${EXPIRES_H:-720}"; RENEW_DAYS="${RENEW_DAYS:-7}"
[ -r "$PF" ] || { echo "delegate: passphrase file $PF unreadable" >&2; exit 2; }
ACTION="scope.decide:${SAGE_BEING}:${SAGE_ROOT%/}"
sc() { if [ "$SCOPE" = system ]; then sudo systemctl "$@"; else systemctl --user "$@"; fi; }
hx() { HESTIA_PASSPHRASE="$(cat "$PF")" "$H" "$@"; }
log() { echo "[delegate $(date -u +%FT%TZ)] $*"; }

KEY=$(hx delegate agent-id "$SEAT" 2>/dev/null | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
[ -n "$KEY" ] || { log "cannot derive agent-id for seat '$SEAT'"; exit 1; }

# Live delegation for this key + action, and its expiry.
LINE=$(hx delegate list 2>/dev/null | grep -F "agent=$KEY" | grep -F "$ACTION" | head -1 || true)
if [ -n "$LINE" ]; then
  EXP=$(echo "$LINE" | grep -oE 'expires=[0-9-]+ [0-9:]+' | cut -d= -f2)
  EXP_S=$(date -u -d "$EXP" +%s 2>/dev/null || echo 0); NOW_S=$(date -u +%s)
  if [ $(( (EXP_S - NOW_S) / 86400 )) -ge "$RENEW_DAYS" ]; then
    log "ok: $SEAT may rule $SAGE_BEING under $SAGE_ROOT until $EXP UTC"; exit 0
  fi
  log "renewing: expires $EXP UTC"
fi

# Signature check: does the daemon accept a ruling from this seat? A 'scope_request_unknown' on a
# bogus id means signature, delegation and authority all passed; anything about the key means
# the seat's operational key is not yet vouched.
NEED_VOUCH=0
if hx scope arbitrate scope-000000000000 --deny --as "$SEAT" --reason probe 2>&1 | grep -qiE "not '.*'s registry binding key|bad_signature|not a key it vouched"; then NEED_VOUCH=1; fi

if pgrep -f "sage.gateway.heartbeat --member $SAGE_BEING" >/dev/null; then log "a beat is running; not restarting the daemon now"; exit 3; fi
log "stopping $UNIT (vault writer lease) — any pending scope request is dropped by this restart"
sc stop "$UNIT"
trap 'sc start "$UNIT"' EXIT
hx delegate grant "$KEY" --action "$ACTION" --expires "$EXPIRES_H" | sed 's/^/  /'
if [ "$NEED_VOUCH" = 1 ]; then hx witness onboard "$SEAT" | sed 's/^/  /'; fi
sc start "$UNIT"; trap - EXIT; sleep 3
hx delegate list | grep -F "$ACTION" | sed 's/^/  live: /'
# Prove the whole ladder: signature -> delegation -> authority. Only the id should be unknown.
if hx scope arbitrate scope-000000000000 --deny --as "$SEAT" --reason probe 2>&1 | grep -q "scope_request_unknown"; then
  log "verified: $SEAT can rule $SAGE_BEING's requests under $SAGE_ROOT"
else
  log "WARN: the ruling probe did not reach 'request unknown'; a real ruling may still be refused"; exit 1
fi
