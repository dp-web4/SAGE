#!/usr/bin/env python3
"""backup_being.sh against a FAKE drive: a temp dir behind a `findmnt` shim, and fake instance, cartridge and
HESTIA_HOME dirs. It never touches the real drive or ~/.hestia.

The 2026-10-31 measurement this pins: the drive filled at 2026-10-25T01:07Z, ~52 runs died mid-copy, and each left a
partial snapshot (no manifest.json). Rows:
  1. 3 complete snapshots, 5 newer partials, KEEP=3: the run removes the partials, links against the newest COMPLETE
     snapshot, and prune keeps complete snapshots (the old script kept the partials and deleted the good ones).
  2. the regression gate reads the newest complete snapshot: a shrunk count past 5 partials is SUSPECT (exit 3).
  3. a run that dies mid-copy leaves no partial directory behind.
Run: python3 scripts/backup_being_test.py [script]   (default: the script beside this file)"""
import json
import os
import pathlib
import subprocess
import sys
import tempfile

SCRIPT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).with_name("backup_being.sh"))
UUID = "00000000-test-test-test-000000000000"
bad = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'} {name}{'' if cond else ' — ' + detail}")
    if not cond:
        bad.append(name)


def world(tmp, partials=5, prev_beats=3, rsync_fails_on=None):
    t = pathlib.Path(tmp)
    mount = t / "drive"
    snaps = mount / "home/dp/being-backups/legion-being/snapshots"
    snaps.mkdir(parents=True)
    for i, stamp in enumerate(["20261024T160700Z", "20261024T190700Z", "20261024T220700Z"]):
        d = snaps / stamp
        (d / "instance").mkdir(parents=True)
        (d / "instance/heartbeats.jsonl").write_text("{}\n" * prev_beats)
        (d / "manifest.json").write_text(json.dumps({"counts": {"memories": 0, "beats": prev_beats, "turns": 0,
                                                                  "journal_bytes": 0}}))
    for i in range(partials):
        (snaps / f"20261025T{i:02d}0700Z" / "instance").mkdir(parents=True)   # no manifest: died mid-copy
    inst = t / "instance"
    inst.mkdir()
    (inst / "heartbeats.jsonl").write_text("{}\n" * 3)
    (t / "cart").mkdir()
    hh = t / "hestia"
    hh.mkdir()
    (hh / "witness.db").write_text("chain\n")
    bin_ = t / "bin"
    bin_.mkdir()
    (bin_ / "findmnt").write_text(f"#!/bin/sh\necho {mount}\n")
    (bin_ / "findmnt").chmod(0o755)
    if rsync_fails_on:
        real = subprocess.check_output(["which", "rsync"], text=True).strip()
        (bin_ / "rsync").write_text(
            "#!/bin/sh\nfor a in \"$@\"; do case \"$a\" in *" + rsync_fails_on + "*) "
            "echo 'No space left on device (28)' >&2; exit 11;; esac; done\nexec " + real + " \"$@\"\n")
        (bin_ / "rsync").chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", BEING_BACKUP_UUID=UUID, BEING_BACKUP_KEEP="3",
               SAGE_INSTANCE=str(inst), MEMBOT_CARTRIDGES=str(t / "cart"), HESTIA_HOME=str(hh),
               BEING_WORKTREE=str(t / "no-worktree"))
    return snaps, env


def run(env):
    return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=120)


def listing(snaps):
    return sorted((d.name, (d / "manifest.json").is_file()) for d in snaps.iterdir() if d.is_dir())


with tempfile.TemporaryDirectory() as tmp:
    snaps, env = world(tmp)
    r = run(env)
    after = listing(snaps)
    complete = [n for n, m in after if m]
    check("row 1: the run succeeds", r.returncode == 0, f"rc={r.returncode}\n{r.stdout[-900:]}{r.stderr[-400:]}")
    check("row 1: no partial survives", all(m for _, m in after), str(after))
    check("row 1: links against the newest COMPLETE snapshot", "previous=20261024T220700Z" in r.stdout,
          r.stdout[:400])
    check("row 1: prune keeps KEEP complete snapshots, the two newest good ones among them",
          len(complete) == 3 and "20261024T190700Z" in complete and "20261024T220700Z" in complete, str(complete))

with tempfile.TemporaryDirectory() as tmp:
    snaps, env = world(tmp, prev_beats=10)          # live has 3 beats, the newest complete snapshot 10
    r = run(env)
    check("row 2: a shrink past 5 partials is SUSPECT (exit 3)", r.returncode == 3 and "SUSPECT" in r.stdout,
          f"rc={r.returncode}\n{r.stdout[-600:]}")
    check("row 2: a suspect run prunes no complete snapshot",
          sum(1 for _, m in listing(snaps) if m) == 4, str(listing(snaps)))

with tempfile.TemporaryDirectory() as tmp:
    snaps, env = world(tmp, partials=0, rsync_fails_on="witness.db")
    r = run(env)
    check("row 3: a run that dies mid-copy exits non-zero", r.returncode != 0, f"rc={r.returncode}")
    check("row 3: and leaves no partial directory", all(m for _, m in listing(snaps)), str(listing(snaps)))

print("FAIL:", bad) if bad else print("PASS - partials are never snapshots")
sys.exit(1 if bad else 0)
