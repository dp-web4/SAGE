#!/usr/bin/env python3
"""Identity provider regression tests — M-CIT-0 (a being's key is verifiable).

Two properties, both of which the provider previously violated silently:

1. The manifest records the anchor ACTUALLY ACHIEVED, never the one requested.
   No hardware sealing is implemented on either provider, so a 'tpm2' request
   seals in software. Recording the request would publish trust_ceiling 1.0 for
   a secret XORed against sha256(hostname:mac:instance_dir) — the fleet's highest
   trust ceiling, mintable by passing a string.

2. A sealed file whose machine key no longer derives is REFUSED, not silently
   unsealed into garbage. XOR is unauthenticated, so a wrong key returns
   plausible bytes; authorize() used to build a signing context asserting the
   manifest's fingerprint with a secret that cannot produce it.

The rust provider carries the mirror of both in
sage-rs/sage-lib/src/identity/provider.rs.

stdlib unittest, matching test_lct_identity.py — these guard the M-CIT-0 gate and
must run on any seat with bare python3, without pytest installed.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sage.identity.provider import IdentityProvider


class IdentityAnchorTests(unittest.TestCase):

    def setUp(self):
        self.instance_dir = Path(tempfile.mkdtemp(prefix='sage-identity-anchor-'))
        self.addCleanup(shutil.rmtree, self.instance_dir, ignore_errors=True)

    def _init(self, anchor_type, directory=None):
        provider = IdentityProvider(str(directory or self.instance_dir))
        manifest = provider.initialize(
            name='test-instance',
            lct_id='lct://sage:test:agent@test',
            machine='test-machine',
            model='test-model:latest',
            anchor_type=anchor_type,
        )
        return provider, manifest

    def test_requested_hardware_anchor_is_downgraded_not_claimed(self):
        """A hardware anchor this provider cannot deliver must not reach the manifest.

        'tpm2_no_pcr' is the sharp case: it carries a ceiling of 0.85 in
        TRUST_CEILINGS but matched no branch of the old _seal_secret, so it wrote
        NO sealed file at all and still returned a manifest — an identity that
        could never authorize again.
        """
        for requested in ('tpm2', 'fido2', 'secure_enclave', 'tpm2_no_pcr'):
            with self.subTest(requested=requested):
                directory = Path(tempfile.mkdtemp(prefix=f'sage-anchor-{requested}-'))
                self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
                provider, manifest = self._init(requested, directory)

                # The manifest prices how the secret is HELD, not what was asked for.
                self.assertEqual(manifest.anchor_type, 'software')
                self.assertEqual(manifest.trust_ceiling, 0.4)

                # A sealed file exists at all (the tpm2_no_pcr silent-skip case).
                sealed_path = directory / 'identity.sealed'
                self.assertTrue(sealed_path.exists(), 'no sealed file was written')

                # ...and its header agrees with the manifest.
                with open(sealed_path, 'rb') as f:
                    self.assertEqual(f.readline().strip(), b'SAGE_SEALED_v2')
                    self.assertEqual(f.readline().strip(), b'software')

                # The identity still round-trips: seal -> lock -> unseal -> authorize.
                provider.lock()
                self.assertFalse(provider.is_authorized)
                context = provider.authorize()
                self.assertIsNotNone(
                    context, 'identity could not re-authorize after sealing')
                self.assertEqual(context.anchor_type, 'software')

    def test_software_anchor_is_recorded_unchanged(self):
        """The honest request is untouched — the downgrade is not a blanket rewrite."""
        _, manifest = self._init('software')
        self.assertEqual(manifest.anchor_type, 'software')
        self.assertEqual(manifest.trust_ceiling, 0.4)

    def test_attestation_reports_the_achieved_anchor(self):
        """Peers read the attestation, so the claim must not survive there either."""
        provider, _ = self._init('tpm2')
        attestation = provider.get_attestation()
        self.assertIsNotNone(attestation)
        self.assertEqual(attestation['anchor_type'], 'software')
        self.assertEqual(attestation['trust_ceiling'], 0.4)

    def _copy_identity(self, dst):
        for name in ('identity.json', 'identity.sealed', 'identity.attest.json'):
            shutil.copy(self.instance_dir / name, dst / name)

    def test_identity_moved_to_another_MACHINE_is_refused(self):
        """The property the old relocation test protected, restated for v2: a sealed file
        whose key no longer derives is REFUSED, never unsealed into plausible garbage.
        v2 binds to the machine, so 'no longer derives' now means another machine."""
        provider, manifest = self._init('software')
        self.assertTrue(provider.is_authorized)
        moved = Path(tempfile.mkdtemp(prefix='sage-identity-moved-'))
        self.addCleanup(shutil.rmtree, moved, ignore_errors=True)
        self._copy_identity(moved)
        relocated = IdentityProvider(str(moved))
        relocated._machine_anchor = lambda: 'some-other-machine-id'
        self.assertIsNone(relocated.authorize(),
                          f'identity from another machine must be refused '
                          f'(fingerprint {manifest.public_key_fingerprint})')
        self.assertFalse(relocated.is_authorized)

    def test_renamed_home_on_the_same_machine_keeps_its_identity(self):
        """2026-09-19: the fleet renames being homes to <machine>-being/. v1 sealed against
        str(instance_dir), so the rename would have orphaned an identity raised since March."""
        provider, manifest = self._init('software')
        moved = Path(tempfile.mkdtemp(prefix='sage-identity-renamed-'))
        self.addCleanup(shutil.rmtree, moved, ignore_errors=True)
        self._copy_identity(moved)
        ctx = IdentityProvider(str(moved)).authorize()
        self.assertIsNotNone(ctx, 'a rename on the same machine must not orphan the identity')
        self.assertEqual(ctx.public_key_fingerprint, manifest.public_key_fingerprint)

    # -- v1 files in the field: three derivations that never agreed -------------------
    def _write_v1(self, provider, mac, path):
        """Re-seal this provider's secret the way a v1 provider would have."""
        import hashlib, socket
        secret = provider.context.identity_secret
        key = hashlib.sha256(f"{socket.gethostname()}:{mac}:{path}".encode()).digest()
        with open(provider.sealed_path, 'wb') as f:
            f.write(b'SAGE_SEALED_v1\nsoftware\n' + bytes(a ^ b for a, b in zip(secret, key)))
        return secret

    def test_v1_sealed_by_the_rust_provider_unseals_and_migrates(self):
        provider, manifest = self._init('software')
        secret = self._write_v1(provider, '0', str(self.instance_dir))
        again = IdentityProvider(str(self.instance_dir))
        ctx = again.authorize()
        self.assertIsNotNone(ctx, "python must unseal a rust-sealed v1 file ('0' for the MAC)")
        self.assertEqual(ctx.identity_secret, secret)
        with open(self.instance_dir / 'identity.sealed', 'rb') as f:
            self.assertEqual(f.readline().strip(), b'SAGE_SEALED_v2', 'verified v1 migrates to v2')
        kept = self.instance_dir / 'identity.sealed.v1'
        self.assertTrue(kept.exists(), 'the original v1 file is kept, not overwritten')
        self.assertTrue(kept.read_bytes().startswith(b'SAGE_SEALED_v1'))
        # and the migrated file authorizes on its own
        self.assertIsNotNone(IdentityProvider(str(self.instance_dir)).authorize())

    def test_v1_sealed_under_a_former_home_heals_through_instance_json(self):
        """Legion's real case: sealed 2026-03-28 at .../legion-gemma3-12b, home renamed."""
        import json
        provider, manifest = self._init('software')
        self._write_v1(provider, '0', '/old/home/legion-gemma3-12b')
        (self.instance_dir / 'instance.json').write_text(json.dumps(
            {'former_homes': [{'path': '/old/home/legion-gemma3-12b', 'moved': '2026-09-19'}]}))
        ctx = IdentityProvider(str(self.instance_dir)).authorize()
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.public_key_fingerprint, manifest.public_key_fingerprint)

    def test_v1_that_no_candidate_unseals_is_still_refused(self):
        provider, _ = self._init('software')
        self._write_v1(provider, '123456789', '/nowhere/anyone/recorded')
        again = IdentityProvider(str(self.instance_dir))
        self.assertIsNone(again.authorize(), 'no candidate matches the fingerprint -> refuse')
        with open(self.instance_dir / 'identity.sealed', 'rb') as f:
            self.assertEqual(f.readline().strip(), b'SAGE_SEALED_v1', 'an unverified file is never rewritten')

    def test_v2_key_is_the_documented_bytes(self):
        """Pins the derivation the Rust provider mirrors; change one, change both."""
        import hashlib
        provider, manifest = self._init('software')
        provider._machine_anchor = lambda: 'ANCHOR'
        self.assertEqual(provider._derive_machine_key_v2(),
                         hashlib.sha256(b'sage-seal-v2:ANCHOR:lct://sage:test:agent@test').digest())


if __name__ == '__main__':
    unittest.main()
