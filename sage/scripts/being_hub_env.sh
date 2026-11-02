#!/usr/bin/env bash
# being_hub_env.sh — write a being's hub drain env (step 2 of being_hub_join.sh's "after admit"), so its beat
# reads ITS OWN hub mailbox and signs its own sends. One command per machine; run by whoever may write it.
#
# Why (2026-10-02): every admitted being except sprout and mcnugget skipped its inbox drain each beat
# ("no being hub env"), so messages to it waited unread, and its outgoing messages were signed by the seat.
# The join script documents this file but deliberately does not write it (it holds a key path).
#
# What it writes: ~/.config/hub-mesh-<being> + the env suffix, mode 600, from
#   - the SEAT's hub-mesh env file:  CHANNEL_CLIENT, HUB_URL (copied as they are);
#   - the being's published identity: sage/gateway/hub/<being>.lct_publish.json -> MY_LCT = document.id;
#   - the being's own seed:          ~/.web4/<being>/channel_key.bin (made by being_hub_join.sh mint) -> MY_KEYPAIR;
#   - HUB_MESH_STATE=~/.local/state/hub-mesh-<being>.
# It never overwrites an existing file, never prints a key, and never reads the mailbox (a read consumes it).
# It REFUSES unless the seed provably derives the published document's key (the same invariant being_hub_join.sh
# enforces at mint): a stale or moved seed would drain one member's mailbox while signing as another key.
#
# usage: being_hub_env.sh <machine>-being [--sage <SAGE checkout>]     e.g.  being_hub_env.sh cbp-being
set -euo pipefail
BEING="${1:?usage: being_hub_env.sh <machine>-being [--sage <SAGE checkout>]}"
SAGE_DIR="$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)"
[ "${2:-}" = "--sage" ] && SAGE_DIR="${3:?--sage needs a path}"
SEAT_ENV="${HUB_MESH_ENV:-$HOME/.config/hub-mesh.env}"
OUT="$HOME/.config/hub-mesh-$BEING.env"
DOC="$SAGE_DIR/sage/gateway/hub/$BEING.lct_publish.json"
SEED="$HOME/.web4/$BEING/channel_key.bin"

fail() { echo "being_hub_env: $*" >&2; exit 1; }
[ -e "$OUT" ] && fail "$OUT already exists; not overwriting. (Nothing to do if the beat drains.)"
[ -s "$SEAT_ENV" ] || fail "no seat hub-mesh env at $SEAT_ENV (set HUB_MESH_ENV)."
[ -s "$DOC" ] || fail "no published identity $DOC: was $BEING minted and joined? (being_hub_join.sh)"
[ -s "$SEED" ] || fail "no seed at $SEED: the being's own key. Mint/join it (being_hub_join.sh), or re-key: dp."
LCT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['document']['id'])" "$DOC")"
[ -n "$LCT" ] || fail "no document.id in $DOC"
# THE SEED MUST BE THIS IDENTITY (GPT on #327; same check as being_hub_join.sh seed_matches_doc)
rc=0
python3 - "$SEED" "$DOC" <<'PY' || rc=$?
import json, sys
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:
    sys.exit(2)
seed = open(sys.argv[1], "rb").read()
if len(seed) != 32:
    sys.exit(1)
own = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw().hex()
sys.exit(0 if own == json.load(open(sys.argv[2]))["document"]["public_key"]["key"].lower() else 1)
PY
case $rc in
  0) ;;
  2) fail "cannot prove the seed is $BEING's identity: python3 'cryptography' is not installed. Install it, then re-run." ;;
  *) fail "the seed at $SEED does NOT derive the key in $DOC: two different identities. Find out which one is $BEING before touching either (dp)." ;;
esac
# the two shared settings, exactly as the seat's file states them (it is shell-sourced, so source it in a subshell)
mapfile -d '' -t SHARED < <(bash -c 'set -a; source "$1"; printf "%s\0%s\0" "${CHANNEL_CLIENT:-}" "${HUB_URL:-}"' _ "$SEAT_ENV")
CC="${SHARED[0]:-}"; HU="${SHARED[1]:-}"
[ -n "$CC" ] && [ -n "$HU" ] || fail "the seat file has no CHANNEL_CLIENT/HUB_URL"
# written single-quoted, so the file sources to exactly these values; a value we cannot quote that way is refused
q() { case "$1" in *"'"*|*$'\n'*) fail "a value contains a quote or newline; refusing to write it" ;; esac; printf "'%s'" "$1"; }
QCC=$(q "$CC"); QHU=$(q "$HU"); QLCT=$(q "$LCT"); QSEED=$(q "$SEED"); QSTATE=$(q "$HOME/.local/state/hub-mesh-$BEING")
umask 077
cat > "$OUT" <<EOF
# $BEING's own hub identity (being_hub_env.sh, $(date -u +%Y-%m-%dT%H:%M:%SZ)): its beat drains this mailbox.
CHANNEL_CLIENT=$QCC
HUB_URL=$QHU
MY_LCT=$QLCT
MY_KEYPAIR=$QSEED
HUB_MESH_STATE=$QSTATE
EOF
chmod 600 "$OUT"
echo "being_hub_env: wrote $OUT (mode 600) for $BEING, MY_LCT=$LCT. The next beat's hub_inbox should show 'fetched'."
