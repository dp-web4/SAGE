#!/usr/bin/env bash
# Verify a being's backup can actually be read back. A backup nobody has restored is a hope.
#
# Checks the newest snapshot (or one named on the command line):
#   1. every file matches the sha256 the manifest recorded for it
#   2. the memory cartridge LOADS and holds the number of memories the manifest claims —
#      the specific failure of 2026-09-09 was a cartridge that existed, was the right
#      shape, and contained nothing, so "the file is present" proves nothing here
#   3. the instance carries the records that make a being itself: entrustment, journal,
#      conversations, and the beat log the memory texts were recovered from
#   4. hestia's vault and witness chain are present and non-trivial in size
#
# Usage: verify_being_backup.sh [snapshot-dir]
set -uo pipefail

BEING="${SAGE_BEING:-legion-being}"
DRIVE_UUID="${BEING_BACKUP_UUID:-180ae0df-e653-4806-bf5d-2b737074fb2d}"

say() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

# The cartridge check needs numpy, and a systemd user service runs with a minimal PATH
# where python3 is /usr/bin/python3 without it. Interactively this passed and under the
# timer it reported the cartridge unreadable — a false alarm about the very thing being
# guarded. Pick an interpreter that can actually open the file.
PY=""
for cand in "${BEING_BACKUP_PYTHON:-}" /home/dp/miniforge3/bin/python3 \
            /home/dp/ai-workspace/membot/.venv/bin/python "$(command -v python3)"; do
    [ -n "$cand" ] && [ -x "$cand" ] && "$cand" -c "import numpy" 2>/dev/null && { PY="$cand"; break; }
done
if [ -z "$PY" ]; then
    say "FAILED: no python3 with numpy found; cannot verify the memory cartridge."
    say "        Set BEING_BACKUP_PYTHON to an interpreter that has it."
    exit 1
fi

SNAP="${1:-}"
if [ -z "$SNAP" ]; then
    MOUNT="$(findmnt -no TARGET "UUID=$DRIVE_UUID" 2>/dev/null | head -1)"
    [ -n "$MOUNT" ] || { say "FAILED: backup drive $DRIVE_UUID is not mounted"; exit 1; }
    SNAP="$MOUNT/home/dp/being-backups/$BEING/latest"
fi
[ -d "$SNAP" ] || { say "FAILED: no snapshot at $SNAP"; exit 1; }
say "verifying $(readlink -f "$SNAP")"

"$PY" - "$SNAP" <<'PY'
import hashlib, json, os, sys

snap = sys.argv[1]
mpath = os.path.join(snap, "manifest.json")
if not os.path.exists(mpath):
    print("FAILED: no manifest.json in this snapshot"); sys.exit(1)
man = json.load(open(mpath))
counts = man.get("counts", {})
problems, checked, skipped = [], 0, 0

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

# 1. content matches what was recorded
for rel, meta in man.get("files", {}).items():
    p = os.path.join(snap, rel)
    if not os.path.exists(p):
        problems.append(f"MISSING {rel}"); continue
    if meta.get("sha256") is None:
        skipped += 1
        if os.path.getsize(p) != meta["bytes"]:
            problems.append(f"SIZE {rel}: {meta['bytes']} -> {os.path.getsize(p)}")
        continue
    checked += 1
    if sha(p) != meta["sha256"]:
        problems.append(f"CORRUPT {rel}")
print(f"  files: {checked} hash-verified, {skipped} size-verified, {len(man.get('files', {}))} total")

# 2. the cartridge is not merely present — it must LOAD and hold what was claimed
cart = os.path.join(snap, "membot-cartridge", "legion-being.cart.npz")
claimed = int(counts.get("memories", 0))
if not os.path.exists(cart):
    problems.append("MISSING the memory cartridge")
else:
    try:
        import numpy as np
        z = np.load(cart, allow_pickle=True)
        passages = list(z["passages"])
        emb = z["embeddings"]
        dim = emb.shape[1] if getattr(emb, "ndim", 0) == 2 else 0
        print(f"  cartridge: {len(passages)} memories, {dim}-dim embeddings "
              f"(manifest claims {claimed})")
        if len(passages) != claimed:
            problems.append(f"CARTRIDGE COUNT {claimed} claimed, {len(passages)} in the file")
        if claimed and (len(passages) == 0 or dim == 0):
            problems.append("CARTRIDGE IS EMPTY — this is the 2026-09-09 failure exactly")
        if passages:
            longest = max(passages, key=lambda t: len(str(t)))
            print(f"  a memory reads: {str(passages[0])[:110]}...")
            if len(str(longest)) < 40:
                problems.append("cartridge holds only stubs, not memories")
    except Exception as e:
        problems.append(f"CARTRIDGE WILL NOT LOAD: {type(e).__name__}: {e}")

# 3. the records that make the being itself
for rel, what in (("instance/entrustment.md", "what it was entrusted with"),
                  ("instance/journal.md", "its journal"),
                  ("instance/todo.md", "its todo"),
                  ("instance/heartbeats.jsonl", "the beat record"),
                  ("instance/long_term_memory_recovered.jsonl", "the recovered memory texts")):
    p = os.path.join(snap, rel)
    if not os.path.exists(p) or os.path.getsize(p) == 0:
        problems.append(f"MISSING/EMPTY {rel} ({what})")
convs = os.path.join(snap, "instance", "conversations")
n_turns = 0
if os.path.isdir(convs):
    for f in os.listdir(convs):
        if f.endswith(".jsonl"):
            n_turns += sum(1 for _ in open(os.path.join(convs, f), errors="replace"))
print(f"  instance: journal {os.path.getsize(os.path.join(snap,'instance/journal.md'))} bytes, "
      f"{n_turns} conversation turns, "
      f"{sum(1 for _ in open(os.path.join(snap,'instance/heartbeats.jsonl'), errors='replace'))} beats")
if n_turns != int(counts.get("turns", -1)):
    problems.append(f"TURNS {counts.get('turns')} claimed, {n_turns} present")

# 4. hestia identity
for rel, floor in (("hestia/vault.enc", 1), ("hestia/witness.db", 1 << 20)):
    p = os.path.join(snap, rel)
    if not os.path.exists(p):
        problems.append(f"MISSING {rel}")
    elif os.path.getsize(p) < floor:
        problems.append(f"SUSPICIOUSLY SMALL {rel}: {os.path.getsize(p)} bytes")
print(f"  hestia: vault {os.path.getsize(os.path.join(snap,'hestia/vault.enc'))} bytes, "
      f"witness chain {os.path.getsize(os.path.join(snap,'hestia/witness.db'))//(1<<20)} MB")

if man.get("suspect"):
    problems.append(f"snapshot was marked SUSPECT when taken: {man['suspect']}")

print()
if problems:
    print(f"NOT SOUND — {len(problems)} problem(s):")
    for p in problems:
        print("  -", p)
    sys.exit(2)
print("SOUND: this snapshot restores the being's identity, history and memory.")
PY
