#!/bin/bash
# Mirror a being's home into private-context (dp ruling 2026-09-19: being state is gitignored in
# public SAGE and "mirrored to private-context going forward").
#
# What does NOT go: identity.sealed* (key material stays on this machine; the USB backup holds it),
# heartbeat.log (stdout noise, 55 MB), caches. heartbeats.jsonl is the record that once made a
# recovery possible, so it goes — split by DAY (so a 3-hourly commit rewrites only today, ~3 MB, not the whole log), because GitHub refuses files over 100 MB and the
# whole log crosses that within weeks.
#
# Exit 0 = mirrored AND pushed AND counts agree. Anything else says why on stderr.
#
# Written by legion-claude on legion/mission-artifact (2026-09-19/20). Landed on main for the fleet
# with ONE change: the four settings below are REQUIRED, with no defaults. The original defaulted to
# Legion's being and an absolute path; on any other machine that either fails late or, worse,
# mirrors under the wrong being's name. A fleet script names nothing it was not told
# (dp directive: no hardcoded paths, not even as a fallback). Set them in the unit that runs this:
#   SAGE_INSTANCE    the being's home, e.g. <workspace>/SAGE/sage/instances/<machine>-being
#   PRIVATE_CONTEXT  the private-context checkout
#   SAGE_BEING       <machine>-being   (the directory name under private-context/beings/)
#   SEAT_ID          <machine>-claude  (recorded in the mirror commit)
set -uo pipefail
say(){ echo "[mirror $(date -u +%FT%TZ)] $*"; }
die(){ say "FAILED: $*" >&2; exit 1; }
for v in SAGE_INSTANCE PRIVATE_CONTEXT SAGE_BEING SEAT_ID; do
  [ -n "${!v:-}" ] || die "$v is not set (required; this script has no defaults — see its header)"
done
INSTANCE="$SAGE_INSTANCE"; PC="$PRIVATE_CONTEXT"; BEING="$SAGE_BEING"; SEAT="$SEAT_ID"
# The mirror directory is named by SAGE_BEING, the source by SAGE_INSTANCE. If they disagree, one
# being's record lands under another's name — refuse rather than guess which was meant.
# TRANSITION: a machine that has not yet moved its being still has a model-named home, and "private
# going forward" should not wait for the move. Such a machine declares the legacy name explicitly
# (and in shared-context/fleet/<machine>.md); the mismatch is then logged, not guessed at.
if [ "$(basename "$INSTANCE")" != "$BEING" ]; then
  [ "${SAGE_INSTANCE_LEGACY_NAME:-}" = "$(basename "$INSTANCE")" ] || die \
    "SAGE_INSTANCE ends in '$(basename "$INSTANCE")' but SAGE_BEING is '$BEING'. If this being has not moved yet, set SAGE_INSTANCE_LEGACY_NAME='$(basename "$INSTANCE")' to say so."
  say "legacy home '$(basename "$INSTANCE")' mirrored as '$BEING' (declared; not yet moved)"
fi
DEST="$PC/beings/$BEING"

[ -d "$INSTANCE" ] || die "no instance at $INSTANCE"
[ -d "$PC/.git" ] || die "no private-context checkout at $PC"
mkdir -p "$DEST/heartbeats"

rsync -a --delete \
  --exclude 'identity.sealed*' --exclude 'heartbeat.log' --exclude 'heartbeats.jsonl' \
  --exclude 'heartbeats/' --exclude '__pycache__/' --exclude '*.tmp' --exclude '.git' \
  "$INSTANCE/" "$DEST/" || die "rsync"
mkdir -p "$DEST/heartbeats"   # excluded above, so --delete leaves it alone

# heartbeats.jsonl -> heartbeats/YYYY-MM-DD.jsonl.gz ; only days whose content changed are rewritten
python3 - "$INSTANCE/heartbeats.jsonl" "$DEST/heartbeats" <<'PY' || die "heartbeat split"
import sys, os, json, collections, gzip, io
src, out = sys.argv[1], sys.argv[2]
if not os.path.exists(src): sys.exit(0)
months = collections.OrderedDict(); n = 0
for line in open(src, encoding="utf-8", errors="replace"):
    if not line.strip(): continue
    n += 1
    try: m = str(json.loads(line).get("ts") or "")[:10] or "undated"
    except ValueError: m = "unparsed"
    months.setdefault(m, []).append(line if line.endswith("\n") else line + "\n")
total = 0
for m, lines in months.items():
    # gzip with mtime=0: identical beats -> identical bytes, so an unchanged day is no diff.
    # Compressed because private-context's pre-commit guard refuses files over 10 MB and a
    # busy day of beats is 13 MB raw (~1 MB gzipped). The guard is right; the mirror adapts.
    p = os.path.join(out, f"{m}.jsonl.gz"); total += len(lines)
    raw = "".join(lines).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=6) as g: g.write(raw)
    blob = buf.getvalue()
    if not os.path.exists(p) or open(p, "rb").read() != blob:
        open(p + ".tmp", "wb").write(blob); os.replace(p + ".tmp", p)
assert total == n, (total, n)
print(f"heartbeats: {n} beats in {len(months)} day file(s)")
PY

# counts: what the being has vs what the mirror holds (the two known exclusions aside)
src_n=$(cd "$INSTANCE" && find . -type f ! -name 'identity.sealed*' ! -name heartbeat.log ! -name heartbeats.jsonl ! -path '*/__pycache__/*' ! -name '*.tmp' | wc -l)
dst_n=$(cd "$DEST" && find . -type f ! -path './heartbeats/*' | wc -l)
[ "$src_n" = "$dst_n" ] || die "count mismatch: instance $src_n vs mirror $dst_n"
src_b=$(wc -l < "$INSTANCE/heartbeats.jsonl" 2>/dev/null || echo 0)
dst_b=$(zcat "$DEST"/heartbeats/*.jsonl.gz 2>/dev/null | wc -l)
[ "$src_b" = "$dst_b" ] || die "beat count mismatch: $src_b vs $dst_b"
big=$(find "$DEST" -type f -size +9M | head -1); [ -z "$big" ] || die "file over 9MB would be refused by private-context's pre-commit size guard: $big"

cd "$PC" || die "cd"
git add -A "beings/$BEING" || die "git add"
if git diff --cached --quiet; then say "no change ($src_n files, $src_b beats)"; exit 0; fi
git commit -q -m "mirror($BEING): $src_n files, $src_b beats

Seat: $SEAT" || die "commit"
git pull -q --rebase --autostash || die "pull --rebase"
git push -q || die "push"
say "mirrored + pushed: $src_n files, $src_b beats -> beings/$BEING @ $(git rev-parse --short HEAD)"
