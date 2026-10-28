#!/usr/bin/env bash
# test_mirror_partial_gz.sh: heartbeat.partial.jsonl is published gzipped, and a failed compressor
# never publishes a cut file (NOVA HOLD at 012ae47c on SAGE #509).
#
# Runs scripts/mirror_being_private.sh end to end against a throwaway instance and a throwaway
# private-context checkout with a bare remote. Failures are injected with a `gzip` shim on PATH,
# which fails only the compress call (-9) and passes -t and -dc through to the real gzip.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIRROR="$(cd "$SCRIPT_DIR/.." && pwd)/mirror_being_private.sh"
REAL_GZIP="$(command -v gzip)"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL: $1 — $2"; FAIL=$((FAIL + 1)); }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
INST="$T/sage/instances/test-being"
PC="$T/private-context"
mkdir -p "$INST" "$T/remote.git" "$T/shim"
git init -q --bare "$T/remote.git"
git init -q "$PC"
git -C "$PC" config user.name test; git -C "$PC" config user.email test@example.invalid
git -C "$PC" remote add origin "$T/remote.git"
echo seed > "$PC/README"; git -C "$PC" add -A; git -C "$PC" commit -q -m seed
git -C "$PC" push -q -u origin HEAD 2>/dev/null

echo '{"ts": "2026-10-22T00:00:00Z", "n": 1}' > "$INST/heartbeats.jsonl"
echo '{"note": "x"}' > "$INST/journal.md"
for i in $(seq 1 2000); do echo "{\"generate\": $i, \"text\": \"some words from a beat\"}"; done > "$INST/heartbeat.partial.jsonl"

GZ="$PC/beings/test-being/heartbeat.partial.jsonl.gz"
run() {  # <PATH prefix or empty>
  env ${1:+PATH="$1:$PATH"} SAGE_INSTANCE="$INST" PRIVATE_CONTEXT="$PC" SAGE_BEING=test-being SEAT_ID=test-seat \
    bash "$MIRROR" > "$T/out" 2>&1
}
sha() { sha256sum "$1" 2>/dev/null | cut -c1-64; }

echo "mirror: heartbeat.partial.jsonl.gz"

# 1. a normal run publishes a .gz that decompresses to the source exactly
if run "" && [ -f "$GZ" ] && "$REAL_GZIP" -dc "$GZ" | cmp -s - "$INST/heartbeat.partial.jsonl"; then
  pass "published, and decompresses to the source"
else fail "published" "$(tail -3 "$T/out")"; fi
good="$(sha "$GZ")"

# 2. an unchanged source gives identical bytes (-n), so the run reports no change
if run "" && [ "$(sha "$GZ")" = "$good" ] && grep -q "no change" "$T/out"; then
  pass "unchanged input -> identical bytes, no change"
else fail "deterministic" "$(tail -3 "$T/out")"; fi

# 3. the compressor is killed partway (writes a truncated stream, exits non-zero)
echo '{"generate": 2001}' >> "$INST/heartbeat.partial.jsonl"
cat > "$T/shim/gzip" <<SH
#!/bin/bash
if [ "\$1" = "-9" ]; then "$REAL_GZIP" -9 -n -c "\${@: -1}" | head -c 100; exit 1; fi
exec "$REAL_GZIP" "\$@"
SH
chmod +x "$T/shim/gzip"
if run "$T/shim"; then fail "killed gzip" "the run succeeded"; else
  if [ "$(sha "$GZ")" = "$good" ]; then pass "killed gzip: run fails, previous copy unchanged"
  else fail "killed gzip" "published copy changed"; fi
fi
if ls -A "$PC/beings/test-being" | grep -q '\.tmp$'; then fail "killed gzip" "temp left behind"
else pass "killed gzip: no temp left behind"; fi

# 4. ENOSPC-like: the stream is cut but gzip reports success; `gzip -t` must catch it
cat > "$T/shim/gzip" <<SH
#!/bin/bash
if [ "\$1" = "-9" ]; then "$REAL_GZIP" -9 -n -c "\${@: -1}" | head -c 100; exit 0; fi
exec "$REAL_GZIP" "\$@"
SH
if run "$T/shim"; then fail "cut stream, exit 0" "the run succeeded"; else
  if [ "$(sha "$GZ")" = "$good" ]; then pass "cut stream reported as success: caught by gzip -t, copy unchanged"
  else fail "cut stream, exit 0" "published copy changed"; fi
fi

# 5. nothing from a failed run was committed: the remote still holds the good copy
git -C "$T/remote.git" show HEAD:beings/test-being/heartbeat.partial.jsonl.gz > "$T/remote.gz" 2>/dev/null
if [ "$(sha "$T/remote.gz")" = "$good" ]; then pass "remote holds the last good copy"
else fail "remote" "remote copy differs from the last good one"; fi

# 6. the next healthy run publishes the grown file
if run "" && "$REAL_GZIP" -dc "$GZ" | cmp -s - "$INST/heartbeat.partial.jsonl" && [ "$(sha "$GZ")" != "$good" ]; then
  pass "a healthy run after failures publishes the grown file"
else fail "recovery" "$(tail -3 "$T/out")"; fi

# 7. the source gone -> the copy goes, and the file counts still agree
rm -f "$INST/heartbeat.partial.jsonl"
if run "" && [ ! -e "$GZ" ]; then pass "source removed -> copy removed, counts agree"
else fail "source removed" "$(tail -3 "$T/out")"; fi

echo "mirror partial gz: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
