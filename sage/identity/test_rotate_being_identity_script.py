"""Regression pin for scripts/rotate_being_identity.py's real-attempt transaction."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def _load_script():
    root = Path(__file__).resolve().parents[2]
    p = root / "scripts" / "rotate_being_identity.py"
    spec = importlib.util.spec_from_file_location("rotate_being_identity_script", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_failure_after_new_seal_restores_every_live_byte_and_consumes_token(tmp_path):
    """Inject the dangerous failure: new seal written, manifest commit then throws."""
    R = _load_script()
    home = tmp_path / "being"
    home.mkdir()

    old_fp = "aaaaaaaaaaaaaaaa"
    manifest = {
        "identity": {
            "name": "being",
            "lct": "lct:web4:test",
            "public_key_fingerprint": old_fp,
            "machine": "m",
            "model": "model",
            "model_family": "family",
            "created": "2026-01-01T00:00:00Z",
            "session_count": 7,
        },
        "anchor_type": "software",
        "trust_ceiling": 0.4,
        "sealed_path": "identity.sealed",
        "development": {"kept": True},
    }
    (home / "identity.json").write_text(json.dumps(manifest, indent=2))
    (home / "identity.sealed").write_bytes(b"OLD-SEAL-BYTES")
    (home / "identity.attest.json").write_bytes(b"OLD-ATTEST")
    (home / "instance.json").write_text('{"former_fingerprints": []}')

    names = ("identity.json", "identity.sealed", "identity.attest.json", "instance.json")
    before = {n: (home / n).read_bytes() for n in names}

    token = tmp_path / "rehearsed.json"
    token.write_text(json.dumps({
        "ok": True,
        "home": str(home.resolve()),
        "seal_sha256": hashlib.sha256(before["identity.sealed"]).hexdigest(),
        "old_fingerprint": old_fp,
    }))

    class FailingProvider:
        def __init__(self, h):
            self.home = Path(h)

        def authorize(self):
            # Baseline and rollback verification both see the original identity.
            m = json.loads((self.home / "identity.json").read_text())
            if ((self.home / "identity.sealed").read_bytes() == b"OLD-SEAL-BYTES"
                    and m["identity"]["public_key_fingerprint"] == old_fp):
                return SimpleNamespace(public_key_fingerprint=old_fp)
            return None

        def initialize(self, **kwargs):
            # The exact partial transition GPT's review required us to survive.
            (self.home / "identity.sealed").write_bytes(b"NEW-SEAL-PARTIAL")
            (self.home / "identity.json").write_bytes(b'{"half-written":')
            raise OSError("injected manifest failure after seal replacement")

    old_provider = R._provider
    R._provider = lambda h: FailingProvider(h)
    try:
        rc = R.rotate(home, real=True, rehearsed=str(token))
    finally:
        R._provider = old_provider

    assert rc == 1
    assert not token.exists(), "a real attempt must consume its rehearsal token"
    for n, data in before.items():
        assert (home / n).read_bytes() == data, f"{n} was not restored byte-for-byte"
