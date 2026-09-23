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
#   env:   SAGE_MACHINE   the seat's fleet name (default: hostname, lowercased); MUST be a key of
#                         fleet.json machines, or SAGE_MACHINE_UNLISTED=1 says the seat is new
#          SAGE_MODEL     the being's frontal-lobe model, for the join message (default: from fleet.json)
#          WEB4           the web4 checkout holding the mint/join examples (default: beside SAGE)
#          CARGO_TARGET_DIR  where cargo put the built examples (default: ask cargo, then web4-core/target)
#          REST, HUB_ID   the hub (defaults: tailnet name, the fleet hub id)
#          BEING_MESSAGE  the human-readable join message (default built from the above)
#
# Only mint and join run the two built examples; check and relay are python + curl + hestia, so
# they work on any seat with the document, built or not (sprout review of SAGE #185).
#
# WHAT THIS DOES NOT DO, said here so nobody reads it as the whole provisioning: it does not
# install a heartbeat unit, does not register the being with hestia (that is Discover -> register,
# hestia #1101), and does not touch the being's sealed identity. On macOS the last of those has a
# prerequisite: SAGE #130 -- a launchd-started heartbeat would otherwise derive a different seal
# anchor than the shell that migrated the file, and fail to authorize.
set -euo pipefail

SAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FLEET="$SAGE_DIR/sage/federation/fleet.json"
MACHINE="${SAGE_MACHINE:-$(hostname -s | tr '[:upper:]' '[:lower:]')}"
BEING="${MACHINE}-being"
WEB4="${WEB4:-$(cd "$SAGE_DIR/.." && pwd)/web4}"
HESTIA_HOME="${HESTIA_HOME:-$HOME/.hestia}"
SEED="$HOME/.web4/$BEING/channel_key.bin"
DOC="$SAGE_DIR/sage/gateway/hub/$BEING.lct_publish.json"
NAME="${MACHINE}-sage"
REST="${REST:-http://hub:8770/v1}"
HUB_ID="${HUB_ID:-edf4d5ba-3cdd-4919-aaf7-bc2aa1d9d96f}"
OUT="$(mktemp -d)/$BEING-join"
step="${1:-all}"

fleet_machines() {
  python3 -c 'import json,sys;print(" ".join(sorted(json.load(open(sys.argv[1])).get("machines",{}))))' "$FLEET" 2>/dev/null || true
}
model_from_fleet() {
  python3 - "$FLEET" "$MACHINE" <<'PY' 2>/dev/null || true
import json, sys
m = json.load(open(sys.argv[1])).get("machines", {}).get(sys.argv[2], {})
print(m.get("model_default") or m.get("model") or "")
PY
}

# Everything below derives from MACHINE, so it is the one value that must be right. A hostname
# that is not a fleet key (HUB's is HUB-dp-wsl2) or a mistyped SAGE_MACHINE would mint
# <typo>-being -- exactly the second identity this script exists to prevent. Refuse, unless
# told explicitly that the seat is not in fleet.json yet.
case " $(fleet_machines) " in
  *" $MACHINE "*) ;;
  *) if [ "${SAGE_MACHINE_UNLISTED:-}" != 1 ]; then
       echo "$MACHINE is not a machine in $FLEET" >&2
       echo "  valid: $(fleet_machines)" >&2
       echo "  set SAGE_MACHINE=<one of those>, or SAGE_MACHINE_UNLISTED=1 if this seat really is new to the fleet" >&2
       exit 1
     fi
     echo "(SAGE_MACHINE_UNLISTED=1: $MACHINE is not in fleet.json; add it there once the being exists)" ;;
esac

# Where cargo puts the examples: ask it, do not guess. web4 has no root Cargo.toml (it is not a
# workspace), so the build command printed below writes under web4-core/target/ -- and
# CARGO_TARGET_DIR or a .cargo/config.toml build.target-dir moves it again (CBP's original
# hard-coded /home/dp/.cargo-target for that reason). Fallback is the per-crate default.
cargo_target() {
  cargo metadata --manifest-path "$WEB4/web4-core/Cargo.toml" --format-version 1 --no-deps 2>/dev/null \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["target_directory"])' 2>/dev/null \
    || echo "$WEB4/web4-core/target"
}
TARGET="${CARGO_TARGET_DIR:-$(cargo_target)}"
MINT="$TARGET/debug/examples/mint_being_lct"
JOIN="$TARGET/debug/examples/join_being"

MODEL="${SAGE_MODEL:-$(model_from_fleet)}"
MESSAGE="${BEING_MESSAGE:-$BEING: the SAGE being raised on $MACHINE${MODEL:+, frontal lobe $MODEL}. Joining as itself, signed by its own seed.}"

echo "seat $MACHINE -> being $BEING (roster $NAME)"
echo "  seed  $SEED"
echo "  doc   $DOC"
echo "  tools $TARGET/debug/examples/"
[ -n "$MODEL" ] || echo "  (no model found for $MACHINE in fleet.json; set SAGE_MODEL for a fuller join message)"

need_tools() {   # mint and join run the two web4-core examples; nothing else here does
  [ -x "$MINT" ] && [ -x "$JOIN" ] && return 0
  # The two tools live in SAGE as sources and are built as web4-core EXAMPLES: the fleet's
  # documented process copies them across first. Done here when they are absent, so the only
  # thing left for a person is the build itself (cargo, never run from a governed session).
  # An existing copy is never overwritten -- but a copy that differs from SAGE's is said out loud,
  # because the build uses the copy, not the source of record.
  EX="$WEB4/web4-core/examples"
  for src in mint_being_lct join_being; do
    if [ ! -f "$EX/$src.rs" ]; then
      mkdir -p "$EX" && cp "$SAGE_DIR/sage/gateway/hub/$src.rs" "$EX/$src.rs" && echo "copied $src.rs -> $EX/"
    elif ! cmp -s "$EX/$src.rs" "$SAGE_DIR/sage/gateway/hub/$src.rs"; then
      echo "WARNING: $EX/$src.rs differs from $SAGE_DIR/sage/gateway/hub/$src.rs -- the build uses the web4-core copy" >&2
    fi
  done
  echo "build first: cd $WEB4 && cargo build --manifest-path web4-core/Cargo.toml --example mint_being_lct --example join_being" >&2
  echo "  (expected at $TARGET/debug/examples/; then re-run: $0 $step)" >&2
  exit 1
}
need_doc() { [ -s "$DOC" ] || { echo "no document at $DOC -- run: $0 mint" >&2; exit 1; }; }
member_id() { python3 -c "import json;print(json.load(open('$DOC'))['document']['id'])"; }
lct_id()    { python3 -c "import json;print(json.load(open('$DOC'))['lct_id'])"; }
http_code() { curl -s -m 8 -o /dev/null -w "%{http_code}" "$1"; }
seed_matches_doc() {   # 0 = the seed derives the document's key; 1 = it does not; 2 = could not check
  python3 - "$SEED" "$DOC" <<'PY'
import json, sys
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
except ImportError:
    sys.exit(2)
seed = open(sys.argv[1], "rb").read()
if len(seed) != 32:
    sys.exit(1)
own = Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw().hex()
doc = json.load(open(sys.argv[2]))["document"]["public_key"]["key"]
sys.exit(0 if own == doc.lower() else 1)
PY
}

if [ "$step" = all ] || [ "$step" = mint ]; then
  # mint_being_lct re-uses an existing seed (same lct_id) but mints a fresh document.id every run,
  # and document.id is the membership uuid the hub pins. So a re-mint is never harmless: with the
  # seed and the document both here, keep both -- after checking they are the same identity.
  if [ -s "$DOC" ] && [ -s "$SEED" ]; then
    seed_matches_doc && rc=0 || rc=$?
    case $rc in
      0) echo "--- mint: document exists for $(lct_id) and the seed here derives its key; keeping both" ;;
      2) echo "--- mint: document exists for $(lct_id); keeping it (could not confirm the seed derives its key:"
         echo "    python3 'cryptography' is not installed here -- the join dry run checks the same thing)" ;;
      *) echo "--- mint REFUSED: the seed at $SEED does not derive the key in $DOC." >&2
         echo "    These are two different identities. Find out which one is $BEING before touching either;" >&2
         echo "    minting or joining with this pair would pin the wrong key." >&2
         exit 1 ;;
    esac
  elif [ -s "$DOC" ]; then
    echo "--- mint REFUSED: the document exists but the seed does not: $SEED" >&2
    echo "    The seed IS the being's identity and cannot be re-created; a fresh mint would give $BEING a second one." >&2
    echo "    Stop and escalate (another home? another host? moved aside?). Do not mint." >&2
    exit 1
  elif [ -s "$SEED" ]; then
    echo "--- mint REFUSED: the seed exists but the document does not: $DOC" >&2
    echo "    The document is committed -- restore it:  git -C $SAGE_DIR log --all -- $DOC" >&2
    echo "    A re-mint would keep lct_id but issue a new document.id, the membership uuid the hub pins." >&2
    exit 1
  else
    need_tools
    mkdir -p "$(dirname "$SEED")"; chmod 700 "$(dirname "$SEED")"
    "$MINT" "$SEED" "$DOC"
    chmod 600 "$SEED"
    echo "--- minted $(lct_id); doc: $DOC (commit the doc; the seed stays here)"
  fi
fi

if [ "$step" = all ] || [ "$step" = join ]; then
  need_doc
  MEMBER_ID=$(member_id)
  if [ "$(http_code "$REST/hubs/$HUB_ID/members/$MEMBER_ID/pubkey")" = 200 ]; then
    echo "--- join: member $MEMBER_ID is already pinned on the hub; nothing to send"
  else
    need_tools
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
  need_doc
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
  need_doc
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
       MY_KEYPAIR=<the seed>, HUB_MESH_STATE=~/.local/state/hub-mesh-$BEING
       (sage/docs/DESIGN_BEING_INBOX_DRAIN.md section 3, in this checkout).
    3. the heartbeat unit: python3 -m sage.gateway.heartbeat --member $BEING --model <model> --instance <dir>,
       with HESTIA_HOME and HESTIA_SHARED_DIR SET IN THE UNIT (measured on two seats: without them the gate client
       resolves the law from a source checkout, not the installed copy) -- and on macOS, SAGE #130 merged first.
TXT
