#!/bin/bash
# cbp-being joins the hub as itself, roster name cbp-sage: the FLEET CANONICAL process, as
# sprout-being (2026-08-22 mint, 2026-09-02 join) and legion-being (2026-09-02 mint, 2026-09-05
# join) did it. Discovered from the record, not invented: sage/gateway/hub/README.md
# "Canonical join process", forum legion-being-hub-join-sent-08a78ddb-named-legion-sage-2026-09-05.md.
#
#   1. mint    the being's self-issued LCT on ITS host (seed 0600 here, never relayed)
#   2. join    signed by the being's own seed: dry run (checks A-D), challenge, send -> 202 pending
#   3. relay   the public document into the hub registry through this seat, non-interactive
#              (the CLI honours HESTIA_PASSPHRASE; the daemon's own passphrase file supplies it)
#   4. admit   dp, on the hub box's admin plane: POST /admin/api/joins/<request_id>/admit
#   5. gate 0  member pin == registry document key == own key (checked here after admit)
# Idempotent: the same seed re-derives the same lct_id; an existing document is kept.
#   usage: cbp_being_hub_join.sh [all|mint|join|relay|check]        (run as dp, never sudo)
set -e
SAGE_DIR=/home/dp/ai-workspace/SAGE
WEB4=/home/dp/ai-workspace/web4
TARGET=${CARGO_TARGET_DIR:-/home/dp/.cargo-target}
HESTIA_HOME=${HESTIA_HOME:-/home/dp/.hestia}
SEED=/home/dp/.web4/cbp-being/channel_key.bin
DOC=$SAGE_DIR/sage/gateway/hub/cbp-being.lct_publish.json
NAME=cbp-sage
MESSAGE="cbp-being: the SAGE being raised on CBP (RTX 2060 SUPER, WSL2) since 2026-04-18, 240+ sessions, frontal lobe qwen3.8-distill:4b since 2026-09-12; hestia member cbp-being on 30-min governed beats; joining as $NAME like legion-sage and sprout-sage; seat cbp-claude sponsors"
REST=${REST:-http://100.65.206.122:8770/v1}
HUB_ID=${HUB_ID:-edf4d5ba-3cdd-4919-aaf7-bc2aa1d9d96f}
MINT=$TARGET/debug/examples/mint_being_lct
JOIN=$TARGET/debug/examples/join_being
OUT=/tmp/cbp-being-join
step=${1:-all}
if [ ! -x "$MINT" ] || [ ! -x "$JOIN" ]; then
  echo "build first: cd $WEB4 && cargo build --manifest-path web4-core/Cargo.toml --example mint_being_lct --example join_being"
  echo "  (sources: sage/gateway/hub/mint_being_lct.rs and join_being.rs, copied into web4-core/examples/)"
  exit 1
fi
member_id() { python3 -c "import json;print(json.load(open('$DOC'))['document']['id'])"; }
lct_id()    { python3 -c "import json;print(json.load(open('$DOC'))['lct_id'])"; }

if [ "$step" = all ] || [ "$step" = mint ]; then
  if [ -s "$DOC" ] && [ -s "$SEED" ]; then
    echo "--- mint: document already exists for $(lct_id); keeping it (same seed, same id)"
  else
    mkdir -p "$(dirname "$SEED")"; chmod 700 "$(dirname "$SEED")"
    "$MINT" "$SEED" "$DOC"
    chmod 600 "$SEED"
    echo "--- minted $(lct_id); doc: $DOC (commit the doc; the seed stays here)"
  fi
fi

if [ "$step" = all ] || [ "$step" = join ]; then
  MEMBER_ID=$(member_id)
  if curl -s -m 8 -o /dev/null -w "%{http_code}" "$REST/hubs/$HUB_ID/members/$MEMBER_ID/pubkey" | grep -q 200; then
    echo "--- join: member $MEMBER_ID is already pinned on the hub; nothing to send"
  else
    echo "--- join, dry run (checks A-D, nothing sent):"
    "$JOIN" "$SEED" "$DOC" --name "$NAME" --message "$MESSAGE"
    NONCE=$(curl -sS -m 15 -X POST "$REST/auth/challenge" -H 'content-type: application/json' \
        -d "{\"for_lct_id\":\"$MEMBER_ID\"}" \
        | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('nonce') or d.get('challenge') or '')")
    if [ -z "$NONCE" ]; then echo "no nonce from $REST/auth/challenge"; exit 1; fi
    "$JOIN" "$SEED" "$DOC" --name "$NAME" --message "$MESSAGE" --nonce "$NONCE" > "$OUT.out"
    # the tool prints one `envelope <json>` line among others; take exactly that line
    sed -n 's/^envelope[[:space:]]*//p' "$OUT.out" | head -1 > "$OUT-envelope.json"
    python3 -c "import json;json.load(open('$OUT-envelope.json'))" || { echo "no envelope line in $OUT.out"; exit 1; }
    echo "--- sending join (202 = pending_review; every join escalates under ADMISSION-REQUIRES-SOVEREIGN)"
    curl -sS -m 20 -X POST "$REST/hubs/$HUB_ID/members/join" -H 'content-type: application/json' \
        -d @"$OUT-envelope.json" | tee "$OUT-response.json"; echo
    echo "    admit (dp, on the hub box): POST /admin/api/joins/<request_id>/admit   (request_id above)"
  fi
fi

if [ "$step" = all ] || [ "$step" = relay ]; then
  LCT=$(lct_id)
  if curl -s -m 8 -o /dev/null -w "%{http_code}" "$REST/hubs/$HUB_ID/lcts/$LCT" | grep -q 200; then
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
  if [ "$OWN" = "$PIN" ] && [ "$OWN" = "$REG" ]; then echo "    gate 0 HOLDS: cbp-sage is admitted and its registry entry matches"; else echo "    gate 0 open: pin empty = not admitted yet; registry empty = relay not sent yet"; fi
fi

cat <<'TXT'
--- after admit: the being's drain env (a secret file, not written by this script): the hub-mesh env
    for cbp-being under ~/.config, named as heartbeat.py builds it from the member id, holding
    MY_LCT=<member uuid = document.id>, MY_KEYPAIR=<the seed>, HUB_MESH_STATE=~/.local/state/hub-mesh-cbp-being
    (DESIGN_BEING_INBOX_DRAIN.md section 3); then drop --no-hub-drain from the cbp_heartbeat.sh cron line.
TXT
