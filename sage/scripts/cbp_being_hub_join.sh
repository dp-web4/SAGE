#!/bin/bash
# cbp-being's hub membership, as the being (M-CIT-1a + 3a), attended: parts of this need the
# seat vault passphrase (the relay) and the hub admin plane (the admit), so an operator runs it.
# Steps mirror sage/gateway/hub/README.md and DESIGN_BEING_INBOX_DRAIN.md sections 2 and 7
# (sprout-being, legion-being):
#   1. mint the being's self-issued LCT on THIS host (seed generated here, never relayed)
#   2. relay the public document to the registry through this seat (subject != publisher)
#   3. join the hub as the being, signed by the being's own seed, roster name cbp-sage
#   4. dp admits at the hub admin plane; then the drain's env file can be written (step 5)
# Idempotent: re-running re-derives the same lct_id from the same seed.
#   usage: cbp_being_hub_join.sh [all|mint|relay|join]
set -e
SAGE_DIR=/home/dp/ai-workspace/SAGE
WEB4=/home/dp/ai-workspace/web4
TARGET=${CARGO_TARGET_DIR:-/home/dp/.cargo-target}
SEED=/home/dp/.web4/cbp-being/channel_key.bin
DOC=$SAGE_DIR/sage/gateway/hub/cbp-being.lct_publish.json
NAME=cbp-sage
MESSAGE="cbp-being: the SAGE being raised on CBP (RTX 2060 SUPER, WSL2) since 2026-04-18, 240+ sessions, frontal lobe qwen3.8-distill:4b since 2026-09-12; hestia member cbp-being on 30-min governed beats; joining as $NAME, like legion-sage and sprout-sage"
REST=${REST:-http://100.65.206.122:8770/v1}
HUB_ID=${HUB_ID:-edf4d5ba-3cdd-4919-aaf7-bc2aa1d9d96f}
MINT=$TARGET/debug/examples/mint_being_lct
JOIN=$TARGET/debug/examples/join_being
step=${1:-all}
if [ ! -x "$MINT" ] || [ ! -x "$JOIN" ]; then
  echo "build first: cd $WEB4 && cargo build --manifest-path web4-core/Cargo.toml --example mint_being_lct --example join_being"
  echo "  (sources: sage/gateway/hub/mint_being_lct.rs and join_being.rs, copied into web4-core/examples/)"
  exit 1
fi

if [ "$step" = all ] || [ "$step" = mint ]; then
  mkdir -p "$(dirname "$SEED")"; chmod 700 "$(dirname "$SEED")"
  "$MINT" "$SEED" "$DOC"
  chmod 600 "$SEED"
  echo "--- minted: $(python3 -c "import json;print(json.load(open('$DOC'))['lct_id'])")"
  echo "    doc: $DOC (commit the doc; the seed stays here and is never relayed)"
fi

if [ "$step" = all ] || [ "$step" = relay ]; then
  echo "--- relay through this seat (asks for the seat vault passphrase): dry run, then send"
  hestia lct relay --dry-run "$DOC"
  hestia lct relay "$DOC" --send || echo "relay send refused or aborted; fix and re-run: $0 relay"
fi

if [ "$step" = all ] || [ "$step" = join ]; then
  echo "--- join, dry run (checks A-D, nothing sent):"
  "$JOIN" "$SEED" "$DOC" --name "$NAME" --message "$MESSAGE"
  MEMBER_ID=$(python3 -c "import json;d=json.load(open('$DOC'));print(d['document']['id'])")
  NONCE=$(curl -sS -X POST "$REST/auth/challenge" -H 'content-type: application/json' \
      -d "{\"for_lct_id\":\"$MEMBER_ID\"}" \
      | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('nonce') or d.get('challenge') or '')")
  if [ -z "$NONCE" ]; then echo "no nonce from $REST/auth/challenge"; exit 1; fi
  "$JOIN" "$SEED" "$DOC" --name "$NAME" --message "$MESSAGE" --nonce "$NONCE" > /tmp/cbp-being-join.out
  python3 - <<'PY'
import json
s = open('/tmp/cbp-being-join.out').read()
i = s.find('{'); j = s.rfind('}')
if i < 0 or j < 0:
    print(s); raise SystemExit("join_being printed no envelope")
json.dump(json.loads(s[i:j + 1]), open('/tmp/cbp-being-join-envelope.json', 'w'))
PY
  echo "--- sending join (202 = pending_review; every join escalates under ADMISSION-REQUIRES-SOVEREIGN)"
  curl -sS -X POST "$REST/hubs/$HUB_ID/members/join" -H 'content-type: application/json' \
      -d @/tmp/cbp-being-join-envelope.json; echo
  echo "    admit at the hub admin plane: POST /admin/api/joins/<request_id>/admit (dp)"
fi

cat <<'TXT'
--- step 5, after admit, by hand (it is a secret file, so this script does not write it):
    the hub-mesh env file for cbp-being under ~/.config, named as heartbeat.py builds it from
    the member id, holding MY_LCT=<member uuid, = document.id>, MY_KEYPAIR=<the seed above>,
    HUB_MESH_STATE=~/.local/state/hub-mesh-cbp-being   (DESIGN_BEING_INBOX_DRAIN.md section 3).
    Then drop --no-hub-drain from the cbp_heartbeat.sh cron line so the being drains its own mailbox each beat.
TXT
