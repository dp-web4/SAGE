#!/usr/bin/env python3
"""verify_being_backup.sh against built snapshots (a loadable cartridge, a hashed manifest, the being's records). Never
touches the real drive. The 2026-10-31 13:07Z snapshot -- the being's only fresh copy after a week -- was kept without
hestia/witness.db (the drive was full) and recorded that in its manifest's `missing`. Rows:
  1. a complete snapshot is SOUND (exit 0)
  2. witness.db absent AND recorded missing: PARTIAL (exit 3), named, no traceback (the old script crashed printing
     its size)
  3. witness.db absent and NOT recorded: NOT SOUND (exit 2)
Run: python3 scripts/verify_being_backup_test.py [verify script]"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

import numpy as np

SCRIPT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).with_name("verify_being_backup.sh"))
bad = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}{'' if cond else ' — ' + detail}")
    if not cond:
        bad.append(name)


def snapshot(root, witness=True, recorded_missing=()):
    snap = pathlib.Path(root) / "snap"
    inst = snap / "instance"
    (inst / "conversations").mkdir(parents=True)
    for rel, text in (("entrustment.md", "entrusted\n"), ("journal.md", "journal\n"), ("todo.md", "todo\n"),
                      ("heartbeats.jsonl", "{}\n{}\n"), ("long_term_memory_recovered.jsonl", "{}\n")):
        (inst / rel).write_text(text)
    (inst / "conversations" / "dp.jsonl").write_text("{}\n{}\n{}\n")
    (snap / "membot-cartridge").mkdir()
    passages = np.array(["a memory long enough to be a memory and not a stub, one",
                         "a memory long enough to be a memory and not a stub, two"], dtype=object)
    np.savez(snap / "membot-cartridge" / "legion-being.cart.npz", passages=passages,
             embeddings=np.ones((2, 8), dtype=np.float32))
    (snap / "hestia").mkdir()
    (snap / "hestia" / "vault.enc").write_bytes(b"v" * 64)
    if witness:
        (snap / "hestia" / "witness.db").write_bytes(b"w" * (2 << 20))
    files = {}
    for p in snap.rglob("*"):
        if p.is_file():
            files[str(p.relative_to(snap))] = {"bytes": p.stat().st_size,
                                               "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    (snap / "manifest.json").write_text(json.dumps({
        "counts": {"memories": 2, "beats": 2, "turns": 3, "journal_bytes": 8},
        "suspect": None, "missing": list(recorded_missing), "files": files}))
    return snap


def verify(snap):
    return subprocess.run(["bash", str(SCRIPT), str(snap)], capture_output=True, text=True, timeout=120,
                          env={"PATH": "/usr/bin:/bin", "BEING_BACKUP_PYTHON": sys.executable})


with tempfile.TemporaryDirectory() as t:
    r = verify(snapshot(t))
    check("row 1: a complete snapshot is SOUND (exit 0)", r.returncode == 0 and "SOUND" in r.stdout,
          f"rc={r.returncode}\n{r.stdout[-500:]}{r.stderr[-300:]}")

with tempfile.TemporaryDirectory() as t:
    r = verify(snapshot(t, witness=False, recorded_missing=["hestia/witness.db"]))
    check("row 2: recorded-missing witness.db is PARTIAL (exit 3)", r.returncode == 3 and "PARTIAL" in r.stdout,
          f"rc={r.returncode}\n{r.stdout[-500:]}{r.stderr[-400:]}")
    check("row 2: and names it", "hestia/witness.db" in r.stdout, r.stdout[-300:])
    check("row 2: with no traceback", "Traceback" not in r.stderr, r.stderr[-400:])

with tempfile.TemporaryDirectory() as t:
    r = verify(snapshot(t, witness=False))
    check("row 3: unrecorded missing witness.db is NOT SOUND (exit 2)",
          r.returncode == 2 and "NOT SOUND" in r.stdout and "MISSING hestia/witness.db" in r.stdout,
          f"rc={r.returncode}\n{r.stdout[-500:]}{r.stderr[-300:]}")

print("FAIL:", bad) if bad else print("PASS - a known gap is PARTIAL, an unknown one is NOT SOUND")
sys.exit(1 if bad else 0)
