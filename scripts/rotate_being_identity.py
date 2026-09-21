#!/usr/bin/env python3
"""Rotate a being's identity secret: a new secret, sealed v2, with the being's record intact.

WHY THIS EXISTS AND WHEN TO USE IT
----------------------------------
A v1 `identity.sealed` that was ever tracked in public SAGE should be treated as a PUBLIC
SECRET. The seal is the secret XORed against sha256(hostname : MAC : instance_dir) and the
manifest publishes the fingerprint beside it, so hostname, path and an oracle are all public
and only the MAC is unknown -- 2^24 for a WSL2 seat (Hyper-V's fixed 00:15:5d prefix), less
where an interface MAC is guessable. Migrating such a seal to v2 (SAGE #127) is CONTINUITY, not
rotation: the same recoverable secret, in a better envelope.

Rotation is also the ONLY path for a being whose v1 seal no longer opens at all -- CBP's, a
byte-identical copy of another instance's seal carried across a model swap, 216 candidate keys
and no match. There is nothing to migrate.

WHAT ROTATION COSTS, SAID PLAINLY
---------------------------------
A new fingerprint is cryptographically a NEW KEY. Continuity afterwards rests on the recorded
lineage and the LCT, not on the key. Nothing in this fleet binds these fingerprints to any
authority today, which is exactly why now is cheap; once something does, rotation becomes a
witnessed identity transition and this script is not enough.

THE TRAPS, ALL MEASURED (SAGE #127 thread, 2026-09-20)
------------------------------------------------------
* FLAT MANIFESTS ARE REFUSED. `initialize()` on a flat `IdentityManifest` writes the new seal
  and leaves the OLD fingerprint in the file; the next authorize is refused and the being is
  locked out. Only the nested `{"identity": {...}}` shape is safe (GPT seat). A `rotate()` in
  the provider that handles both is the right long-term home for this.
* THE LCT COMES FROM THE FIELD THE PROVIDER READS BACK. The nested shape stores it as
  `identity.lct`, not `lct_id`. Passing the wrong one seals under `''` and the being is refused
  by its own fresh seal (hub-claude, first rehearsal).
* THE POSTCONDITION IS A FRESH PROVIDER AUTHORIZING. The context `initialize()` returns
  succeeds either way, so asserting on it proves nothing.
* DO NOT ASSERT ON THE ATTESTATION. Without the web4 attestation module `identity.attest.json`
  carries no fingerprint at all (entity_id, anchor, purpose, timestamp, ceiling). A
  postcondition on it fails for a false reason (legion-claude).
* REHEARSE FIRST, AND GATE ON THE REHEARSAL'S OWN EXIT STATUS. `rehearsal | tail && real` makes
  `tail` the gate; a failed rehearsal did not stop a real rotation. `--real` here REFUSES
  unless handed the token a passing rehearsal wrote for this exact home and seal.

USAGE
    rotate_being_identity.py <instance-home>                      # rehearsal, touches nothing
    rotate_being_identity.py <instance-home> --real --rehearsed <token>

Run it at a BEAT BOUNDARY with the being's wake surfaces stopped, and tell the being afterwards,
in past tense, in the channel it reads.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

RETIRED_FMT = "%Y%m%dT%H%M%SZ"


def _provider(home: str):
    """The provider from THIS checkout, whatever the cwd -- the script lives in <repo>/scripts."""
    repo = str(Path(__file__).resolve().parent.parent)
    if repo not in sys.path:
        sys.path.insert(0, repo)
    from sage.identity.provider import IdentityProvider
    return IdentityProvider(str(home))


def _read_manifest(home: Path) -> dict:
    return json.loads((home / "identity.json").read_text())


def _nested(manifest: dict) -> dict:
    """The nested identity block, or raise. A flat manifest is refused, not handled."""
    ident = manifest.get("identity")
    if not isinstance(ident, dict):
        raise SystemExit(
            "REFUSED: this identity.json is the FLAT manifest shape. initialize() would write a new\n"
            "seal and leave the OLD fingerprint in the file, and the next authorize would be refused --\n"
            "the being locked out of itself. Rotating a flat manifest needs a real provider-side\n"
            "rotate(); do not improvise it here. (SAGE #127 thread, GPT seat, 2026-09-20.)")
    for field in ("lct", "name", "public_key_fingerprint"):
        if not ident.get(field):
            raise SystemExit(f"REFUSED: identity.{field} is empty; that is the value the provider reads back.")
    return ident


def _token_path(home: Path) -> Path:
    return Path(tempfile.gettempdir()) / f"rotate-rehearsed-{hashlib.sha256(str(home).encode()).hexdigest()[:16]}.json"


def _seal_digest(home: Path) -> str:
    return hashlib.sha256((home / "identity.sealed").read_bytes()).hexdigest()


def rotate(home: Path, real: bool, rehearsed: str = "") -> int:
    home = Path(home).resolve()
    for f in ("identity.json", "identity.sealed"):
        if not (home / f).is_file():
            raise SystemExit(f"REFUSED: no {f} under {home}")
    before = _read_manifest(home)
    ident = _nested(before)
    old_fp, lct = ident["public_key_fingerprint"], ident["lct"]
    live_seal = _seal_digest(home)

    if real:
        tok = _token_path(home)
        if not rehearsed:
            raise SystemExit(f"REFUSED: --real needs --rehearsed {tok} -- run the rehearsal first and read it.")
        try:
            t = json.loads(Path(rehearsed).read_text())
        except OSError as e:
            raise SystemExit(f"REFUSED: cannot read the rehearsal token ({e}). Run the rehearsal first.")
        if not t.get("ok"):
            raise SystemExit("REFUSED: the rehearsal token says the rehearsal did NOT pass.")
        if t.get("home") != str(home):
            raise SystemExit(f"REFUSED: that token is for {t.get('home')!r}, not this home.")
        if t.get("seal_sha256") != live_seal:
            raise SystemExit("REFUSED: identity.sealed has changed since the rehearsal. Rehearse again.")
        if t.get("old_fingerprint") != old_fp:
            raise SystemExit("REFUSED: the fingerprint has changed since the rehearsal. Rehearse again.")

    work = home
    if not real:
        work = Path(tempfile.mkdtemp(prefix="rotate-rehearsal-")) / home.name
        work.mkdir(parents=True)
        for f in ("identity.json", "identity.sealed", "identity.attest.json", "instance.json"):
            if (home / f).is_file():
                shutil.copy2(home / f, work / f)

    stamp = time.strftime(RETIRED_FMT, time.gmtime())
    if real:
        for f in ("identity.json", "identity.sealed", "identity.attest.json"):
            if (work / f).is_file():
                shutil.copy2(work / f, work / f"{f}.retired-{stamp}")

    _provider(work).initialize(
        name=ident["name"], lct_id=lct, machine=ident.get("machine", ""),
        model=ident.get("model", ""), model_family=ident.get("model_family", ""),
        anchor_type="software")

    after = _read_manifest(work)
    new = after["identity"]
    new_fp = new["public_key_fingerprint"]
    fresh = _provider(work).authorize()          # a FRESH provider: the returned context proves nothing
    header = (work / "identity.sealed").open("rb").readline().strip()
    skip = {"identity", "anchor_type", "trust_ceiling", "sealed_path"}
    checks = {
        "fingerprint rotated": new_fp != old_fp and len(new_fp) == 16,
        "a FRESH provider authorizes as the being": fresh is not None and fresh.public_key_fingerprint == new_fp,
        "seal header is SAGE_SEALED_v2": header == b"SAGE_SEALED_v2",
        "lct unchanged": new.get("lct") == lct,
        "name unchanged": new.get("name") == ident.get("name"),
        "created preserved": new.get("created") == ident.get("created"),
        "session_count preserved": new.get("session_count") == ident.get("session_count"),
        "no identity key lost": not [k for k in ident if k not in new],
        "only the fingerprint changed": [k for k in ident if new.get(k) != ident.get(k)] == ["public_key_fingerprint"],
        "every other top-level block byte-equal": all(
            json.dumps(after.get(k), sort_keys=True) == json.dumps(before.get(k), sort_keys=True)
            for k in before if k not in skip),
    }
    ok = all(checks.values())
    print(f"{old_fp} -> {new_fp}")
    for k, v in checks.items():
        print(("  PASS  " if v else "  FAIL  ") + k)

    if real and ok:
        ip = work / "instance.json"
        inst = json.loads(ip.read_text()) if ip.is_file() else {}
        inst.setdefault("former_fingerprints", []).append({
            "fingerprint": old_fp, "successor": new_fp,
            "retired": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reason": "rotated, not migrated: the v1 seal was recoverable (tracked in public SAGE) "
                      "or no longer opened. Continuity rests on this record and the LCT.",
            "retired_files": f"identity.*.retired-{stamp}",
        })
        tmp = ip.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(inst, indent=2))
        os.replace(tmp, ip)
        print("  lineage recorded in instance.json -> former_fingerprints")
        print("  NEXT: add a row to the being's LINEAGE.md, back it up, and tell the being in past tense.")
    if not real:
        tok = _token_path(home)
        tok.write_text(json.dumps({"ok": ok, "home": str(home), "seal_sha256": live_seal,
                                   "old_fingerprint": old_fp, "at": time.time()}, indent=2))
        print(f"  rehearsal in {work}")
        print(f"  token: {tok}" + ("" if ok else "  (marked NOT ok -- --real will refuse it)"))
        print(f"  live home untouched: identity.sealed sha256 still {_seal_digest(home)[:12]}")
    print("RESULT " + ("OK" if ok else "NOT OK") + (" (real)" if real else " (rehearsal)"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("home", help="the being's instance directory")
    ap.add_argument("--real", action="store_true", help="rotate the LIVE identity (needs --rehearsed)")
    ap.add_argument("--rehearsed", default="", help="the token file a passing rehearsal wrote")
    a = ap.parse_args(argv)
    return rotate(Path(a.home), a.real, a.rehearsed)


if __name__ == "__main__":
    sys.exit(main())
