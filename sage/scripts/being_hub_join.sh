#!/usr/bin/env bash
# <machine>-being joins the hub as itself, roster name <machine>-sage: the FLEET CANONICAL process
# (sage/gateway/hub/README.md "Canonical join process"), generalised from cbp_being_hub_join.sh so
# that no seat has to copy a script and hand-edit seven paths to provision its being. Every
# per-machine value is derived or overridable; nothing is invented.
#
#   1. mint    the being's self-issued LCT on ITS host (seed 0600 here, never relayed)
#   2. join    signed by the being's own seed: dry run (checks A-D), challenge, send -> 202 pending
#   3. relay   the public document into the hub registry through this seat, non-interactive
#              (needs HESTIA_PASSPHRASE or $HESTIA_HOME/.passphrase; the operator's, not a session's)
#   4. admit   dp, on the hub box's admin plane: POST /admin/api/joins/<request_id>/admit
#   5. gate 0  member pin == registry document key == own key (checked here after admit)
#
#   usage: being_hub_join.sh [all|mint|join|relay|check]        (run as the operator, never sudo)
#   env:   SAGE_MACHINE   the seat's fleet name (default: hostname, lowercased)
#          SAGE_MODEL     the being's frontal-lobe model, for the join message (default: from fleet.json)
#          WEB4           the web4 checkout holding the mint/join examples (default: beside SAGE)
#          REST, HUB_ID   the hub (defaults: tailnet name, the fleet hub id)
#          BEING_MESSAGE  the human-readable join message (default built from the above)
#
# WHAT THIS DOES NOT DO, said here so nobody reads it as the whole provisioning: it does not
# install a heartbeat unit, does not register the being with hestia (that is Discover -> register,
# hestia #1101), and does not touch the being's sealed identity. On macOS the last of those has a
# prerequisite: SAGE #130 -- a launchd-started heartbeat would otherwise derive a different seal
# anchor than the shell that migrated the file, and fail to authorize.
set -euo pipefail

SAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MACHINE="${SAGE_MACHINE:-$(hostname -s | tr '[:upper:]' '[:lower:]')}"
BEING="${MACHINE}-being"
WEB4="${WEB4:-$(cd "$SAGE_DIR/.." && pwd)/web4}"
TARGET="${CARGO_TARGET_DIR:-$WEB4/target}"
HESTIA_HOME="${HESTIA_HOME:-$HOME/.hestia}"
SEED="$HOME/.web4/$BEING/channel_key.bin"
DOC="$SAGE_DIR/sage/gateway/hub/$BEING.lct_publish.json"
NAME="${MACHINE}-sage"
REST="${REST:-http://hub:8770/v1}"
HUB_ID="${HUB_ID:-edf4d5ba-3cdd-4919-aaf7-bc2aa1d9d96f}"
MINT="$TARGET/debug/examples/mint_being_lct"
JOIN="$TARGET/debug/examples/join_being"
OUT="$(mktemp -d)/$BEING-join"
step="${1:-all}"

model_from_fleet() {
  python3 - "$SAGE_DIR/sage/federation/fleet.json" "$MACHINE" <<'PY' 2>/dev/null || true
import json, sys
m = json.load(open(sys.argv[1])).get("machines", {}).get(sys.argv[2], {})
print(m.get("model_default") or m.get("model") or "")
PY
}
MODEL="${SAGE_MODEL:-$(model_from_fleet)}"
MESSAGE="${BEING_MESSAGE:-$BEING: the SAGE being raised on $MACHINE${MODEL:+, frontal lobe $MODEL}. Joining as itself, signed by its own seed.}"

echo "seat $MACHINE -> being $BEING (roster $NAME)"
echo "  seed $SEED"
echo "  doc  $DOC"
[ -n "$MODEL" ] || echo "  (no model found for $MACHINE in fleet.json; set SAGE_MODEL for a fuller join message)"

if [ ! -x "$MINT" ] || [ ! -x "$JOIN" ]; then
  # The two tools live in SAGE as sources and are built as web4-core EXAMPLES: the fleet's
  # documented process copies them across first. Done here when they are absent, so the only
  # thing left for a person is the build itself (cargo, never run from a governed session).
  EX="$WEB4/web4-core/examples"
  for src in mint_being_lct join_being; do
    if [ ! -f "$EX/$src.rs" ]; then
      mkdir -p "$EX" && cp "$SAGE_DIR/sage/gateway/hub/$src.rs" "$EX/$src.rs" && echo "copied $src.rs -> $EX/"
    fi
  done
  echo "build first: cd $WEB4 && cargo build --manifest-path web4-core/Cargo.toml --example mint_being_lct --example join_being" >&2
  echo "  then re-run: $0 $step" >&2
  exit 1
fi
member_id() { python3 -c "import json;print(json.load(open('$DOC'))['document']['id'])"; }
lct_id()    { python3 -c "import json;print(json.load(open('$DOC'))['lct_id'])"; }
http_code() { curl -s -m 8 -o /dev/null -w "%{http_code}" "$1"; }

if [ "$step" = all ] || [ "$step" = mint ]; then
  if [ -s "$DOC" ] && [ -s "$SEED" ]; then
    echo "--- mint: document already exists for $(lct_id); keeping it (same seed, same id)"
  elif [ -s "$DOC" ] || [ -s "$SEED" ]; then
    echo "--- mint REFUSED: exactly one of the seed and the document exists. A new mint would give"
    echo "    this being a second identity. Restore the missing half or move both aside deliberately:"
    echo "      seed: $SEED  doc: $DOC" >&2
    exit 1
  else
    mkdir -p "$(dirname "$SEED")"; chmod 700 "$(dirname "$SEED")"
    "$MINT" "$SEED" "$DOC"
    chmod 600 "$SEED"
    echo "--- minted $(lct_id); doc: $DOC (commit the doc; the seed stays here)"
  fi
fi

if [ "$step" = all ] || [ "$step" = join ]; then
  MEMBER_ID=$(member_id)
  if [ "$(http_code "$REST/hubs/$HUB_ID/members/$MEMBER_ID/pubkey")" = 200 ]; then
    echo "--- join: member $MEMBER_ID is already pinned on the hub; nothing to send"
  else
    echo "--- join, dry run (checks A-D, nothing sent):"
    "$JOIN" "$SEED" "$DOC" --name "$NAME" --message "$MESSAGE"
    NONCE=$(curl -sS -m 15 -X POST "$REST/auth/challenge" -H 'content-type: application/json' \
        -d "{\"for_lct_id\":\"$MEMBER_ID\"}" \
        | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('nonce') or d.get('challenge') or '')")
    if [ -z "$NONCE" ]; then echo "no nonce from $REST/auth/challenge" >&2; exit 1; fi
    "$JOIN" "$SEED" "$DOC" --name "$NAME" --message "$MESSAGE" --nonce "$NONCE" > "$OUT.out"
    sed -n 's/^envelope[[:space:]]*//p' "$OUT.out" | head -1 > "$OUT-envelope.json"
    python3 -c "import json;json.load(open('$OUT-envelope.json'))" || { echo "no envelope line in $OUT.out" >&2; exit 1; }
    echo "--- sending join (202 = pending_review; every join escalates under ADMISSION-REQUIRES-SOVEREIGN)"
    curl -sS -m 20 -X POST "$REST/hubs/$HUB_ID/members/join" -H 'content-type: application/json' \
        -d @"$OUT-envelope.json" | tee "$OUT-response.json"; echo
    echo "    admit (dp, on the hub box): POST /admin/api/joins/<request_id>/admit   (request_id above)"
  fi
fi

if [ "$step" = all ] || [ "$step" = relay ]; then
  LCT=$(lct_id)
  if [ "$(http_code "$REST/hubs/$HUB_ID/lcts/$LCT")" = 200 ]; then
    echo "--- relay: $LCT is already in the hub registry; nothing to send"
  else
    echo "--- relay through this seat: dry run (no vault), then send (vault, non-interactive)"
    hestia lct relay --dry-run "$DOC"
    if [ -z "${HESTIA_PASSPHRASE:-}" ] && [ -r "$HESTIA_HOME/.passphrase" ]; then
      HESTIA_PASSPHRASE="$(cat "$HESTIA_HOME/.passphrase")"; export HESTIA_PASSPHRASE
    fi
    hestia lct relay --send "$DOC" || echo "relay send refused; re-run: $0 relay"
  fi
fi

if [ "$step" = all ] || [ "$step" = check ]; then
  MEMBER_ID=$(member_id); LCT=$(lct_id)
  OWN=$(python3 -c "import json;print(json.load(open('$DOC'))['document']['public_key']['key'])")
  PIN=$(curl -s -m 8 "$REST/hubs/$HUB_ID/members/$MEMBER_ID/pubkey" | python3 -c "import sys,json;print(json.load(sys.stdin).get('pubkey_hex',''))" 2>/dev/null || true)
  REG=$(curl -s -m 8 "$REST/hubs/$HUB_ID/lcts/$LCT" | python3 -c "import sys,json;print(json.load(sys.stdin)['document']['public_key']['key'])" 2>/dev/null || true)
  echo "--- gate 0: own=${OWN:0:12} pin=${PIN:0:12} registry=${REG:0:12}"
  if [ "$OWN" = "$PIN" ] && [ "$OWN" = "$REG" ]; then
    echo "    gate 0 HOLDS: $NAME is admitted and its registry entry matches"
  else
    echo "    gate 0 open: not admitted yet, or the registry entry differs -- admit first, then re-run: $0 check"
  fi
fi

cat <<TXT
--- after admit, in this order:
    1. hestia: Discover -> the sage row -> register (hestia #1101) mints $BEING as a member of this seat's
       society, with its id derived from this machine's name. Nothing to type.
    2. the being's drain env (a secret file, not written by this script): the hub-mesh env for $BEING under
       ~/.config, named as heartbeat.py builds it from the member id, holding MY_LCT=<member uuid = document.id>,
       MY_KEYPAIR=<the seed>, HUB_MESH_STATE=~/.local/state/hub-mesh-$BEING (DESIGN_BEING_INBOX_DRAIN.md section 3).
    3. the heartbeat unit: python3 -m sage.gateway.heartbeat --member $BEING --model <model> --instance <dir>,
       with HESTIA_HOME and HESTIA_SHARED_DIR SET IN THE UNIT (measured on two seats: without them the gate client
       resolves the law from a source checkout, not the installed copy) -- and on macOS, SAGE #130 merged first.
TXT
