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
# memory-only, 8 h) and every pending gate escalation. So "nothing pending" is CHECKED, not
# scheduled around (GPT, review of #180): `hestia gate pending --json` serves every member's
# pending scope requests beside the escalations (hestia #1109), and this script stops the daemon
# only when both counts are zero. A daemon that does not serve the scope field cannot prove the
# queue empty, and the script refuses rather than guesses — renewal is then a hand-run after a
# ruling. Never run it from inside a beat.
#
# Exit codes: 0 covered/renewed; 1 verify failed; 2 usage; 3 a beat is running;
#             4 something is pending (no stop, no vault mutation); 5 the daemon cannot report pending.
#
# Hosts: Linux with systemd (the unit control); expiry parsing is python3, not GNU date, so the
# check itself is portable. On a host without systemd set HESTIA_STOP/HESTIA_START to commands.
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
sc() {
  if [ "$1" = stop ] && [ -n "${HESTIA_STOP:-}" ]; then eval "$HESTIA_STOP"; return; fi
  if [ "$1" = start ] && [ -n "${HESTIA_START:-}" ]; then eval "$HESTIA_START"; return; fi
  if [ "$SCOPE" = system ]; then sudo systemctl "$@"; else systemctl --user "$@"; fi
}
hx() { HESTIA_PASSPHRASE="$(cat "$PF")" "$H" "$@"; }
log() { echo "[delegate $(date -u +%FT%TZ)] $*"; }

KEY=$(hx delegate agent-id "$SEAT" 2>/dev/null | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
[ -n "$KEY" ] || { log "cannot derive agent-id for seat '$SEAT'"; exit 1; }

# Live delegation for this key + action, and its expiry.
# Every id for this key+action, because `delegate grant` ADDS a delegation, it does not extend
# one: without revoking the superseded ids a "renewal" leaves two live grants for the same
# action, and the next leaves three. Measured on Sprout 2026-09-24 the first time the renewal
# path ran for real (8717267c and 395a7042 live together, identical action, different expiry).
# The duplicate is not dangerous — same seat, same action — but standing authority nobody can
# enumerate is the opposite of what a delegation is for, and `delegate revoke <id>` is the
# operator's stated remedy, which only works if there is ONE id to name.
OLD_IDS=$(hx delegate list 2>/dev/null | grep -F "agent=$KEY" | grep -F "$ACTION" \
          | grep -oE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' || true)
LINE=$(hx delegate list 2>/dev/null | grep -F "agent=$KEY" | grep -F "$ACTION" | head -1 || true)
if [ -n "$LINE" ]; then
  EXP=$(echo "$LINE" | grep -oE 'expires=[0-9-]+ [0-9:]+' | cut -d= -f2 || true)
  # python3, not GNU `date -d`: on macOS the latter falls back to 0 and every delegation reads as due.
  EXP_S=$(python3 -c 'import sys,datetime as d
for f in ("%Y-%m-%d %H:%M:%S","%Y-%m-%d %H:%M"):
    try: print(int(d.datetime.strptime(sys.argv[1],f).replace(tzinfo=d.timezone.utc).timestamp())); break
    except ValueError: pass
else: sys.exit(1)' "$EXP") || { log "cannot parse expiry '$EXP'; refusing to treat it as due"; exit 1; }
  NOW_S=$(date -u +%s)
  if [ $(( (EXP_S - NOW_S) / 86400 )) -ge "$RENEW_DAYS" ]; then
    log "ok: $SEAT may rule $SAGE_BEING under $SAGE_ROOT until $EXP UTC"; exit 0
  fi
  log "renewing: expires $EXP UTC"
fi

# Signature check: does the daemon accept a ruling from this seat? A 'scope_request_unknown' on a
# bogus id means signature, delegation and authority all passed; anything about the key means
# the seat's operational key is not yet vouched.
NEED_VOUCH=0
# The probes read the daemon's WORDS, not the CLI's exit status: under pipefail a CLI that exits
# non-zero on the very error we are looking for would make the match invisible.
probe() { hx scope arbitrate scope-000000000000 --deny --as "$SEAT" --reason probe 2>&1 || true; }
if probe | grep -qiE "not '.*'s registry binding key|bad_signature|not a key it vouched"; then NEED_VOUCH=1; fi

if pgrep -f "sage.gateway.heartbeat --member $SAGE_BEING" >/dev/null; then log "a beat is running; not restarting the daemon now"; exit 3; fi
# NOTHING PENDING — machine-checked, both queues, every member. The stop below is what drops them.
PEND=$(hx gate pending --json 2>/dev/null || echo '{}')
VERDICT=$(printf '%s' "$PEND" | python3 -c '
import json,sys
try: d=json.loads(sys.stdin.read() or "{}")
except Exception: d={}
esc=d.get("count"); sc=d.get("pending_scope_count")
if not isinstance(sc,int) or not isinstance(esc,int): print("unknown"); sys.exit(0)
if esc or sc:
    who=", ".join("%s (%s)" % (q.get("request_id"), q.get("claimed_by")) for q in d.get("pending_scope_requests") or [])
    print(f"pending esc={esc} scope={sc} {who}".strip())
else: print("clear")')
case "$VERDICT" in
  clear) log "nothing pending on the daemon (escalations 0, scope requests 0)";;
  unknown) log "the daemon does not report pending scope requests (needs hestia #1109); cannot prove the queue empty — not restarting. Renew by hand right after a ruling."; exit 5;;
  *) log "$VERDICT — a restart would drop it; not restarting, nothing granted"; exit 4;;
esac
log "stopping $UNIT (vault writer lease)"
sc stop "$UNIT"
trap 'sc start "$UNIT"' EXIT
hx delegate grant "$KEY" --action "$ACTION" --expires "$EXPIRES_H" | sed 's/^/  /'
# Supersede, do not accumulate. Only AFTER the new grant is in the vault, and only while the
# daemon is still stopped (the revoke needs the same writer lease). A revoke that fails leaves
# a harmless duplicate and says so; it must never abort the run, because the new grant — the
# thing this script exists to guarantee — has already landed by here.
for _old in $OLD_IDS; do
  if hx delegate revoke "$_old" >/dev/null 2>&1; then log "superseded: revoked $_old"
  else log "WARN: could not revoke superseded delegation $_old; it stays live until it expires"; fi
done
if [ "$NEED_VOUCH" = 1 ]; then hx witness onboard "$SEAT" | sed 's/^/  /'; fi
sc start "$UNIT"; trap - EXIT; sleep 3
hx delegate list | grep -F "$ACTION" | sed 's/^/  live: /' || log "WARN: the delegation is not in 'delegate list' after the grant"
# Prove the whole ladder: signature -> delegation -> authority. Only the id should be unknown.
if probe | grep -q "scope_request_unknown"; then
  log "verified: $SEAT can rule $SAGE_BEING's requests under $SAGE_ROOT"
else
  log "WARN: the ruling probe did not reach 'request unknown'; a real ruling may still be refused"; exit 1
fi
