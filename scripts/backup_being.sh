#!/usr/bin/env bash
# Back up a being's identity, history and memory to an external drive.
#
# WHY THIS EXISTS, precisely. On 2026-09-09 legion-being's long-term memory cartridge was
# found holding ZERO memories. It had held 223 at 2026-09-08T21:36:20Z. A soft failure in
# membot ("No cartridge mounted", returned as ordinary text) made every `remember` look
# like a success, and the save that followed wrote the empty session over the populated
# file. Thirteen hours of beats reported "memory #N stored" while the file on disk was
# 1,170 bytes. The texts were recoverable ONLY because every intent's arguments are kept
# in heartbeats.jsonl. There was no backup of any of it.
#
# So this script is built around one rule: A BACKUP THAT CAN BE SILENTLY EMPTIED IS NOT A
# BACKUP. Every run counts what it is about to copy, compares those counts with the last
# run, and refuses to retire the previous snapshot when anything shrank.
#
# What it copies:
#   * the instance directory — entrustment, journal, todo, notes, scratch, conversations,
#     heartbeats.jsonl (the record that made recovery possible), account, identity files
#   * the membot cartridge — the being's long-term memory, plus its manifest
#   * hestia's identity core — the vault the being's LCT and standing grants live in, the
#     witness chain, the inbox, trust and seats
#   * the being's uncommitted work as a patch (its worktree is a git checkout; what is
#     committed lives in the repo, what is not lives only here)
#
# Snapshots are hardlinked against the previous one (rsync --link-dest), so an unchanged
# file costs an inode, not its bytes.
#
# Usage: backup_being.sh [--dry-run]
set -uo pipefail

BEING="${SAGE_BEING:-legion-being}"
INSTANCE="${SAGE_INSTANCE:-/home/dp/ai-workspace/SAGE/sage/instances/legion-gemma3-12b}"
CART_DIR="${MEMBOT_CARTRIDGES:-/home/dp/ai-workspace/membot/cartridges}"
CART_NAME="${MEMBOT_CART:-legion-being}"
HESTIA_HOME="${HESTIA_HOME:-/home/dp/.hestia}"
WORKTREE="${BEING_WORKTREE:-/home/dp/ai-workspace/being-worktrees/legion-being}"

# The drive is named by FILESYSTEM UUID, never by mount path: /media/dp/<uuid> is created
# by the desktop automounter and a different disk could take the same path.
DRIVE_UUID="${BEING_BACKUP_UUID:-180ae0df-e653-4806-bf5d-2b737074fb2d}"
# 24 snapshots at the 3-hourly cadence = three days of history. Sizing, measured
# 2026-09-09: a snapshot is ~141 MB, of which 109 MB is the hestia witness chain and ~17 MB
# the being's own append-only logs — all of which change every beat, so hardlinking saves
# the static remainder only. 24 x 141 MB is about 3.4 GB against the 17 GB this drive has.
KEEP="${BEING_BACKUP_KEEP:-24}"
# NOTE ON THE VAULT PASSPHRASE. This script does not copy it, or the operator key, and
# that is a governance decision rather than an oversight. hestia's gate refuses this seat
# any act that touches a credential path (egress.secret), and putting those files on a
# drive that can leave the machine is what that rule exists to prevent. The consequence is
# stated in the README written below: vault.enc is encrypted with that passphrase, so this
# backup restores the being's records, memory and history in full, while a complete
# identity restore needs the operator to supply the passphrase from wherever they keep it.
# If that trade should change, it changes as an operator act and by amending this comment.

DRY=""
[ "${1:-}" = "--dry-run" ] && DRY="--dry-run"   # checked before the copy: a dry run returns early

say() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
die() { say "FAILED: $*"; exit 1; }

# ---------------------------------------------------------------- the drive
MOUNT="$(findmnt -no TARGET "UUID=$DRIVE_UUID" 2>/dev/null | head -1)"
[ -n "$MOUNT" ] || die "backup drive $DRIVE_UUID is not mounted. Nothing was backed up.
   Plug it in (or mount it) and run: systemctl --user start being-backup.service
   This exits non-zero on purpose: a backup that is not happening must be visible."
DEST_ROOT="$MOUNT/home/dp/being-backups/$BEING"
[ -w "$(dirname "$(dirname "$DEST_ROOT")")" ] || die "$MOUNT/home/dp is not writable by $(id -un)"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SNAP="$DEST_ROOT/snapshots/$STAMP"
PREV="$(ls -1d "$DEST_ROOT"/snapshots/*/ 2>/dev/null | sort | tail -1)"
PREV="${PREV%/}"
say "being=$BEING drive=$MOUNT snapshot=$STAMP"
[ -n "$PREV" ] && say "previous=$(basename "$PREV")" || say "previous=(none: first run)"

# ------------------------------------------------- what we are about to copy
# Counted BEFORE the copy, from the live files, so the manifest describes what was on the
# machine at snapshot time rather than what happened to land on the drive.
cart_npz="$CART_DIR/$CART_NAME.cart.npz"
cart_manifest="$CART_DIR/$CART_NAME.cart_manifest.json"
memories=0
[ -f "$cart_manifest" ] && memories="$(python3 -c "
import json,sys
try: print(int(json.load(open(sys.argv[1])).get('count', 0)))
except Exception: print(0)" "$cart_manifest")"
beats=0;   [ -f "$INSTANCE/heartbeats.jsonl" ] && beats="$(wc -l < "$INSTANCE/heartbeats.jsonl")"
journal=0; [ -f "$INSTANCE/journal.md" ] && journal="$(wc -c < "$INSTANCE/journal.md")"
recovered=0; [ -f "$INSTANCE/long_term_memory_recovered.jsonl" ] && \
    recovered="$(wc -l < "$INSTANCE/long_term_memory_recovered.jsonl")"
turns=0
for f in "$INSTANCE"/conversations/*.jsonl; do
    [ -f "$f" ] && turns=$((turns + $(wc -l < "$f")))
done
say "counts: memories=$memories beats=$beats turns=$turns journal_bytes=$journal recovered=$recovered"

# ------------------------------------------ the regression gate (the whole point)
# A shrinking count is how the loss of 2026-09-08 would have looked from here. It is not
# proof of damage — a log can be rotated, a conversation pruned — so the run continues and
# the snapshot is taken. What it must NOT do is let the last good snapshot be pruned.
SUSPECT=""
if [ -n "$PREV" ] && [ -f "$PREV/manifest.json" ]; then
    SUSPECT="$(python3 - "$PREV/manifest.json" "$memories" "$beats" "$turns" "$journal" <<'PY'
import json, sys
prev = json.load(open(sys.argv[1])).get("counts", {})
now = dict(zip(("memories", "beats", "turns", "journal_bytes"), map(int, sys.argv[2:6])))
shrank = [f"{k}: {prev[k]} -> {now[k]}" for k in now
          if isinstance(prev.get(k), int) and now[k] < prev[k]]
print("; ".join(shrank))
PY
)"
fi
if [ -n "$SUSPECT" ]; then
    say "SUSPECT: something shrank since the last snapshot — $SUSPECT"
    say "SUSPECT: taking the snapshot anyway and KEEPING every older one (no pruning this run)."
    say "SUSPECT: if this is the cartridge, read sage/instances/*/long_term_memory_recovered.jsonl"
fi

# ---------------------------------------------------------------- the copy
# A DRY RUN MUST NOT TOUCH THE SERIES. It used to mkdir the snapshot directory before
# rsync's own --dry-run did nothing, so probing the script left empty directories in the
# snapshot series — and if the source is missing it then died at the first rsync, leaving
# the stub behind (measured 2026-09-09 while testing the address-change case). The counts
# and the regression gate above are the whole value of a dry run; they have already run.
if [ -n "$DRY" ]; then
    say "dry run: counts and the regression gate ran; nothing was written to $DEST_ROOT"
    [ -n "$SUSPECT" ] && exit 3
    exit 0
fi
mkdir -p "$SNAP" || die "cannot create $SNAP"

# rsync resolves --link-dest against the DESTINATION directory, so it has to name the
# matching subdirectory of the previous snapshot — not the snapshot root. Pointed at the
# root, every lookup misses and every file is copied in full: four snapshots measured
# 563 MB where they should have shared nearly all of it (2026-09-09).
rs() {  # rs <relative-subpath> <rsync args...>
    local sub="$1"; shift
    local link=()
    [ -n "$PREV" ] && [ -d "$PREV/$sub" ] && link=(--link-dest="$PREV/$sub")
    rsync -a --delete --numeric-ids --info=stats1 $DRY "${link[@]}" "$@"
}

say "instance ->"
rs instance --exclude '__pycache__/' "$INSTANCE/" "$SNAP/instance/" || die "rsync instance"

say "cartridge ->"
mkdir -p "$SNAP/membot-cartridge"
if [ -f "$cart_npz" ]; then
    rs membot-cartridge "$cart_npz" "$cart_manifest" "$SNAP/membot-cartridge/" || die "rsync cartridge"
else
    say "WARNING: no cartridge at $cart_npz — the being's long-term memory is NOT in this snapshot"
fi

say "hestia identity ->"
mkdir -p "$SNAP/hestia"
# The vault holds the being's LCT and its standing grants; witness.db is the chain every
# witnessed act is anchored in. The multi-GB build caches and rolled binaries are not
# identity and are excluded by listing what IS.
# An `&&` chain here skipped every one of these files on a FIRST run, silently, because
# the link-dest test is false when there is no previous snapshot. Plain `if`.
hlink=()
if [ -n "$PREV" ] && [ -d "$PREV/hestia" ]; then hlink=(--link-dest="$PREV/hestia"); fi
for f in vault.enc witness.db inbox.db public-identity.json current-build.json \
         reputation-deltas.jsonl deploy-status.tsv endpoint; do
    if [ -e "$HESTIA_HOME/$f" ]; then
        # no --delete here: these are named files, not a mirrored tree
        rsync -a --info=stats1 $DRY "${hlink[@]}" "$HESTIA_HOME/$f" "$SNAP/hestia/" \
            || die "rsync hestia/$f"
    fi
done
for d in trust seats telemetry archive; do
    [ -d "$HESTIA_HOME/$d" ] && rs "hestia/$d" "$HESTIA_HOME/$d/" "$SNAP/hestia/$d/"
done
say "vault unlock material is NOT copied by design — see the note at the top of this script"

say "uncommitted work ->"
mkdir -p "$SNAP/worktree"
if [ -d "$WORKTREE/.git" ] || [ -f "$WORKTREE/.git" ]; then
    ( cd "$WORKTREE" || exit 0
      git rev-parse HEAD                       > "$SNAP/worktree/HEAD" 2>/dev/null
      git status --porcelain                   > "$SNAP/worktree/status.txt" 2>/dev/null
      git diff HEAD                            > "$SNAP/worktree/uncommitted.patch" 2>/dev/null
      git log --oneline -50                    > "$SNAP/worktree/recent-commits.txt" 2>/dev/null
      # untracked files are in no commit and in no diff: they exist only here
      git ls-files --others --exclude-standard > "$SNAP/worktree/untracked.txt" 2>/dev/null
      if [ -s "$SNAP/worktree/untracked.txt" ]; then
          tar -czf "$SNAP/worktree/untracked.tar.gz" -T "$SNAP/worktree/untracked.txt" 2>/dev/null
      fi )
fi

# ---------------------------------------------------------------- the manifest
python3 - "$SNAP" "$BEING" "$STAMP" "$memories" "$beats" "$turns" "$journal" "$recovered" \
         "${SUSPECT:-}" <<'PY'
import hashlib, json, os, subprocess, sys
snap, being, stamp = sys.argv[1], sys.argv[2], sys.argv[3]
memories, beats, turns, journal, recovered = map(int, sys.argv[4:9])
suspect = sys.argv[9]

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

files, total = {}, 0
for root, _, names in os.walk(snap):
    for n in names:
        p = os.path.join(root, n)
        if os.path.islink(p) or n == "manifest.json":
            continue
        try:
            st = os.stat(p); total += st.st_size
            rel = os.path.relpath(p, snap)
            # hash the small, load-bearing things; size alone for bulk history
            files[rel] = {"bytes": st.st_size,
                          "sha256": sha(p) if st.st_size <= 8 << 20 else None}
        except OSError:
            pass
json.dump({
    "being": being, "snapshot": stamp,
    "host": os.uname().nodename,
    "counts": {"memories": memories, "beats": beats, "turns": turns,
               "journal_bytes": journal, "recovered_memory_lines": recovered},
    "suspect": suspect or None,
    "total_bytes": total, "file_count": len(files),
    "files": files,
}, open(os.path.join(snap, "manifest.json"), "w"), indent=1, sort_keys=True)
print(f"manifest: {len(files)} files, {total/1e6:.1f} MB")
PY

ln -sfn "$SNAP" "$DEST_ROOT/latest"

# ---------------------------------------------------------------- README + prune
cat > "$DEST_ROOT/README.md" <<EOF
# $BEING — identity, history, memory

Written by \`SAGE/scripts/backup_being.sh\` on $(hostname). Newest: \`latest/\` -> \`snapshots/$STAMP\`.

Each snapshot holds:

| path | what it is |
|---|---|
| \`instance/\` | the being's own directory: entrustment, journal, todo, notes, scratch, conversations, \`heartbeats.jsonl\` |
| \`membot-cartridge/\` | its long-term memory (\`.cart.npz\`) and the manifest naming how many memories are in it |
| \`hestia/\` | the vault its LCT and standing grants live in, the witness chain, inbox, trust, seats |
| \`worktree/\` | its uncommitted work as a patch, plus untracked files (what is committed is in the git repo) |
| \`manifest.json\` | counts, sizes and sha256 of every file, for verifying a restore |

Snapshots are hardlinked to the one before, so an unchanged file costs an inode, not its bytes.

## What is deliberately not here

The hestia vault unlock material. \`vault.enc\` above is encrypted with it, so this backup
restores the being's records, memory and history in full, while a complete identity restore
needs the operator to supply that unlock material from wherever they keep it.

That is a decision, not an oversight: hestia's own gate refuses the seat any act touching
those files, and putting them on a drive that can leave the machine is what the rule exists
to prevent. Changing the trade is an operator act.

## Why the counts matter

On 2026-09-09 this being's memory cartridge was found holding 0 memories; it had held 223
the night before. A soft failure made every \`remember\` report success while the save wrote
an empty cartridge over the real one. Each run here counts memories, beats, conversation
turns and journal bytes, compares them with the previous snapshot, and if anything shrank
it marks the snapshot \`suspect\` and prunes nothing — so the last good copy stays.

Check the newest snapshot at any time:

    jq '{snapshot, counts, suspect}' latest/manifest.json

## Restoring

    rsync -a latest/instance/           <SAGE>/sage/instances/<instance>/
    rsync -a latest/membot-cartridge/   <membot>/cartridges/
    rsync -a latest/hestia/vault.enc latest/hestia/witness.db latest/hestia/secrets/ ~/.hestia/

Then restart \`membot-*\`, \`hestia\`, and the being's heartbeat, and confirm the cartridge
mounts with the count this manifest names.
EOF

if [ -n "$SUSPECT" ]; then
    say "not pruning (suspect run); $(ls -1d "$DEST_ROOT"/snapshots/*/ 2>/dev/null | wc -l) snapshots kept"
else
    mapfile -t all < <(ls -1d "$DEST_ROOT"/snapshots/*/ 2>/dev/null | sort)
    if [ "${#all[@]}" -gt "$KEEP" ]; then
        for old in "${all[@]:0:$(( ${#all[@]} - KEEP ))}"; do
            say "prune $(basename "${old%/}")"
            [ -z "$DRY" ] && rm -rf "$old"
        done
    fi
fi

# Room to keep going. The drive is a 477 GB disk that is 97% full with other things; if it
# fills, rsync fails mid-copy and the newest snapshot is the broken one.
# `df -P --output=` is rejected (the two are mutually exclusive) and the empty result read
# as 0 free, so the first run cried "0 MB free" on a drive with 17 GB. A guard that fires
# on its own bug teaches the operator to ignore it.
free_kb="$(df -k --output=avail "$MOUNT" | tail -1 | tr -d " ")"
if [ "${free_kb:-0}" -lt 3145728 ]; then
    say "WARNING: only $((free_kb / 1024)) MB free on the backup drive. At ~150 MB per"
    say "WARNING: snapshot this has room for about $((free_kb / 1024 / 150)) more. Lower"
    say "WARNING: BEING_BACKUP_KEEP (now $KEEP) or free space on the drive."
fi

sync
say "OK: $SNAP"
df -h --output=avail "$MOUNT" | tail -1 | xargs -I{} echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) drive free: {}"
[ -n "$SUSPECT" ] && exit 3
exit 0
