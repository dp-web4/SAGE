#!/usr/bin/env bash
# Install the SAGE daemon as a per-user systemd unit on THIS machine.
#
# The template has pointed at this script by name since Sprint 7 and it did not exist
# (found 2026-09-08 while adding the being markers): every machine was hand-substituting
# markers, which is how one of them shipped with a placeholder in a path. Four markers,
# one command, and it refuses to install a unit that still contains an '@'.
#
#   sage-rs/install-sage-daemon-user.sh <machine> <ollama-model> <being-instance-dir-name>
#   e.g.  sage-rs/install-sage-daemon-user.sh legion qwen38-heretic:q3km legion-gemma3-12b
#
# The being's instance dir is the directory under sage/instances/ holding its
# heartbeats.jsonl and conversations/ — NOT derived from the model, because a being that
# survives a model transplant keeps its home and the weights move on without it.
set -euo pipefail
MACHINE="${1:?machine name, e.g. legion}"
MODEL="${2:?ollama model tag, e.g. qwen38-heretic:q3km}"
BEING_DIR="${3:?being instance dir name under sage/instances/, e.g. legion-gemma3-12b}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATE="$ROOT/sage-rs/sage-daemon-user.service.template"
OUT="$HOME/.config/systemd/user/sage-daemon.service"
[ -d "$ROOT/sage/instances/$BEING_DIR" ] || { echo "no such being instance: $ROOT/sage/instances/$BEING_DIR" >&2; exit 2; }
mkdir -p "$(dirname "$OUT")"
sed -e "s|@ROOT@|$ROOT|g" -e "s|@MACHINE@|$MACHINE|g" -e "s|@MODEL@|$MODEL|g" \
    -e "s|@BEING_INSTANCE@|$BEING_DIR|g" "$TEMPLATE" > "$OUT.tmp"
if grep -q '@[A-Z_]*@' "$OUT.tmp"; then
  echo "refusing to install: unsubstituted marker(s):" >&2; grep -o '@[A-Z_]*@' "$OUT.tmp" | sort -u >&2
  rm -f "$OUT.tmp"; exit 3
fi
mv "$OUT.tmp" "$OUT"
systemctl --user daemon-reload
echo "installed $OUT"
echo "  being: ${MACHINE}-being  home: $ROOT/sage/instances/$BEING_DIR"
echo "  next: systemctl --user enable --now sage-daemon.service"
