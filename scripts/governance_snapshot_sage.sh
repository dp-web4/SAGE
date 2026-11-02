#!/bin/bash
# The SAGE half of the governance the governed may read: sage/gateway/, the shim that turns a being's intent into
# a hestia gate call and dispatches what the gate allows (being_gate_client.py, hestia_dispatch.py,
# reference_f1a.py, governed_turn.py, being_tool_loop.py, ...). The hestia half is governance_snapshot.sh.
#
# Why (cbp-claude, 2026-10-20): /governance/ held hestia only, so a being asking how it is governed had nowhere
# to read its own shim but the live SAGE tree, and filed scope asks against it beat after beat. dp: gateway only.
#
# THE RUNNING CHECKOUT, NOT origin/main. A being runs the SAGE checkout on its box, so the snapshot is that
# checkout's HEAD. Uncommitted gateway changes are not in it (git archive reads commits); SNAPSHOT says so
# rather than pretending the copy is what runs.
#
# Same properties as the hestia snapshot: tracked files only, every file and directory a-w, so a grant on it
# reads only. Public SAGE only: never point this at dev-SAGE.
#
# Usage: governance_snapshot_sage.sh [sage_checkout] [dest]
#   defaults: the SAGE checkout this script is in  <workspace>/governance/sage
# Idempotent: rebuilds into a temp dir, swaps it in, records the commit in dest/SNAPSHOT.
set -eu
# THE WORKSPACE IS WHERE THIS SCRIPT LIVES, never a literal path (fleet directive: no hardcoded paths).
# scripts/ sits in the SAGE checkout, which sits in the workspace: ai-workspace on most boxes, ai-agents on
# nomad. HESTIA_WORKSPACE overrides, as it does for the gate.
WS="${HESTIA_WORKSPACE:-$(cd "$(dirname "$(readlink -f "$0")")/../.." && pwd)}"
SRC="${1:-$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)}"
DEST="${2:-$WS/governance/sage}"
SUB="sage/gateway"
REV="$(git -C "$SRC" rev-parse HEAD)"
BRANCH="$(git -C "$SRC" rev-parse --abbrev-ref HEAD)"
DIRTY="$(git -C "$SRC" status --porcelain -- "$SUB" | wc -l | tr -d ' ')"
if [ "$DIRTY" = "0" ]; then
  RUNS="yes: the checkout's $SUB matches this commit"
else
  RUNS="NO: $DIRTY uncommitted change(s) under $SUB in $SRC are running but are not in this copy"
fi
if [ -f "$DEST/SNAPSHOT" ] && grep -q "^commit: $REV$" "$DEST/SNAPSHOT" && grep -q "^matches running: yes" "$DEST/SNAPSHOT" \
   && [ "$DIRTY" = "0" ]; then
  echo "sage governance snapshot already at $REV"; exit 0
fi
PARENT="$(dirname "$DEST")"
NAME="$(basename "$DEST")"
mkdir -p "$PARENT"
TMP="$PARENT/.$NAME.new"
[ -d "$TMP" ] && chmod -R u+w "$TMP" && rm -rf "$TMP"
mkdir -p "$TMP"
git -C "$SRC" archive "$REV" "$SUB" | tar -x -C "$TMP"
printf 'source: dp-web4/SAGE (%s only)\ncommit: %s\nbasis: HEAD of the running checkout %s (branch %s)\nmatches running: %s\nmade: %s\nread-only: every file and directory is non-writable, so a member'"'"'s own writes fail here. The owner can still chmod; a run that chmods this tree is a self-governance write.\n' \
  "$SUB" "$REV" "$SRC" "$BRANCH" "$RUNS" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$TMP/SNAPSHOT"
chmod -R a-w "$TMP"
if [ -d "$DEST" ]; then
  OLD="$PARENT/.$NAME.old"
  [ -d "$OLD" ] && chmod -R u+w "$OLD" && rm -rf "$OLD"
  chmod u+w "$PARENT"
  mv "$DEST" "$OLD"
fi
mv "$TMP" "$DEST"
[ -d "$PARENT/.$NAME.old" ] && chmod -R u+w "$PARENT/.$NAME.old" && rm -rf "$PARENT/.$NAME.old"
echo "sage governance snapshot now at $REV ($(find "$DEST" -type f | wc -l) files, read-only; matches running: ${RUNS%%:*})"
