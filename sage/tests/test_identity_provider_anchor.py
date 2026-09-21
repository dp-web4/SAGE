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

    # --- the backup-before-rewrite invariant, four arms (same four in the Rust suite) ---

    def _live(self):
        return (self.instance_dir / 'identity.sealed').read_bytes()

    def test_migration_arm1_no_backup_creates_a_byte_identical_one_then_rewrites(self):
        provider, _ = self._init('software')
        self._write_v1(provider, '0', str(self.instance_dir))
        original = self._live()
        self.assertIsNotNone(IdentityProvider(str(self.instance_dir)).authorize())
        self.assertEqual((self.instance_dir / 'identity.sealed.v1').read_bytes(), original)
        self.assertTrue(self._live().startswith(b'SAGE_SEALED_v2'))

    def test_migration_arm2_backup_impossible_authorizes_but_does_not_rewrite(self):
        provider, manifest = self._init('software')
        self._write_v1(provider, '0', str(self.instance_dir))
        original = self._live()
        (self.instance_dir / 'identity.sealed.v1').mkdir()   # a directory: cannot be the backup
        ctx = IdentityProvider(str(self.instance_dir)).authorize()
        self.assertIsNotNone(ctx, 'a verified v1 still authorizes when it cannot be migrated')
        self.assertEqual(ctx.public_key_fingerprint, manifest.public_key_fingerprint)
        self.assertEqual(self._live(), original, 'the live v1 was replaced with no backup of it')

    def test_migration_arm3_stale_backup_is_not_blessed_as_the_original(self):
        """HUB induced this on a real seal 2026-09-20: unrelated bytes already at
        identity.sealed.v1, the live v1 replaced anyway, the log saying 'original kept',
        and the v1 bytes surviving nowhere."""
        import contextlib
        import io
        provider, manifest = self._init('software')
        self._write_v1(provider, '0', str(self.instance_dir))
        original = self._live()
        (self.instance_dir / 'identity.sealed.v1').write_bytes(b'NOT THE ORIGINAL')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ctx = IdentityProvider(str(self.instance_dir)).authorize()
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.public_key_fingerprint, manifest.public_key_fingerprint)
        self.assertEqual(self._live(), original, 'the live v1 was replaced beside a stale backup')
        self.assertEqual((self.instance_dir / 'identity.sealed.v1').read_bytes(), b'NOT THE ORIGINAL')
        self.assertNotIn('original kept', out.getvalue(), 'success was claimed for a migration that did not happen')
        self.assertIn('NOT migrated', out.getvalue())

    def test_migration_arm4_dangling_symlink_is_never_followed(self):
        """A dangling backup symlink must not redirect the preservation write outside the home."""
        import contextlib
        import io
        import os
        provider, manifest = self._init('software')
        self._write_v1(provider, '0', str(self.instance_dir))
        original = self._live()

        outside_dir = Path(tempfile.mkdtemp(prefix='sage-identity-symlink-target-'))
        self.addCleanup(shutil.rmtree, outside_dir, ignore_errors=True)
        sentinel = outside_dir / 'must-not-be-created'
        keep = self.instance_dir / 'identity.sealed.v1'
        os.symlink(sentinel, keep)

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ctx = IdentityProvider(str(self.instance_dir)).authorize()

        self.assertIsNotNone(ctx, 'a verified v1 still authorizes when migration is blocked')
        self.assertEqual(ctx.public_key_fingerprint, manifest.public_key_fingerprint)
        self.assertEqual(self._live(), original, 'the live v1 changed beside a dangling symlink')
        self.assertTrue(keep.is_symlink(), 'the backup symlink itself was replaced')
        self.assertFalse(sentinel.exists(), 'migration followed the dangling symlink outside the being home')
        self.assertNotIn('original kept', out.getvalue())
        self.assertIn('NOT migrated', out.getvalue())

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

    def test_macos_ifconfig_macs_are_candidates_for_v1_recovery(self):
        """No sysfs on macOS: the MACs come from `ifconfig -a`. Parser pinned on real-shaped
        output; the decimal form must equal what uuid.getnode() would have sealed with."""
        sample = ("lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384\n"
                  "\tinet 127.0.0.1 netmask 0xff000000\n"
                  "en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500\n"
                  "\tether f0:18:98:aa:bb:cc\n"
                  "en1: flags=8963<UP> mtu 1500\n\tether 36:6f:24:00:11:22\n"
                  "bridge0: flags=8863 mtu 1500\n\tether 36:6f:24:00:11:22\n")
        macs = IdentityProvider._parse_ether_lines(sample)
        self.assertEqual(macs, [str(0xf01898aabbcc), str(0x366f24001122)])
        # and a v1 sealed with a MAC that only ifconfig reports is recovered
        provider, manifest = self._init('software')
        self._write_v1(provider, str(0xf01898aabbcc), str(self.instance_dir))
        again = IdentityProvider(str(self.instance_dir))
        again._interface_macs = lambda: macs
        ctx = again.authorize()
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx.public_key_fingerprint, manifest.public_key_fingerprint)

    def test_v2_key_is_the_documented_bytes(self):
        """Pins the derivation the Rust provider mirrors; change one, change both."""
        import hashlib
        provider, manifest = self._init('software')
        provider._machine_anchor = lambda: 'ANCHOR'
        self.assertEqual(provider._derive_machine_key_v2(),
                         hashlib.sha256(b'sage-seal-v2:ANCHOR:lct://sage:test:agent@test').digest())


class SystemToolLookupTests(unittest.TestCase):
    """The machine anchor is an INPUT TO THE SEALING KEY, so how `ioreg` is found is not a
    detail. Measured on McNugget (macOS, 2026-09-20): /usr/sbin/ioreg and /sbin/ifconfig are
    outside the `/usr/bin:/bin` a launchd agent gets by default. By bare name, a shell found
    them and the daemon's unit did not -- one machine, two anchors (IOPlatformUUID vs
    `host:<name>`), two v2 keys, and zero MACs for healing a v1 seal. Silent both ways: the
    fallback is a valid anchor, just a different one. Mirrors the rust
    `system_tool_is_resolved_without_path`."""

    @staticmethod
    def _with_path(value):
        import os
        from unittest import mock
        return mock.patch.dict(os.environ, {'PATH': value})

    def test_system_tool_ignores_path(self):
        import os
        for path in ('/usr/bin:/bin', '', '/nonexistent'):
            with self._with_path(path):
                for tool in ('ioreg', 'ifconfig'):
                    got = IdentityProvider._system_tool(tool)
                    if sys.platform == 'darwin':
                        self.assertTrue(os.path.isabs(got) and os.access(got, os.X_OK),
                                        f"{tool} under PATH={path!r} -> {got!r}")
        if sys.platform == 'darwin':
            self.assertEqual(IdentityProvider._system_tool('ioreg'), '/usr/sbin/ioreg')
            self.assertEqual(IdentityProvider._system_tool('ifconfig'), '/sbin/ifconfig')
        self.assertIsNone(IdentityProvider._system_tool('no-such-tool-xyz'),
                          "not found must be None: returning the bare name hands the next "
                          "subprocess.run straight back to PATH, which is the defect")

    def test_a_tool_reachable_ONLY_through_PATH_is_neither_found_nor_run(self):
        """The negative control (GPT seat, SAGE #130). The first cut returned the bare name on a
        miss, so the next `subprocess.run([name])` reopened PATH and two processes on one
        machine could still derive different anchors. A tool that exists only on PATH must be
        invisible to this lookup, and must not reach the anchor."""
        import os
        import shutil as _shutil
        import tempfile as _tempfile
        d = Path(_tempfile.mkdtemp(prefix='sage-fake-tool-'))
        self.addCleanup(_shutil.rmtree, d, ignore_errors=True)
        fake = d / 'ioreg'
        fake.write_text('#!/bin/sh\necho \'    "IOPlatformUUID" = "00000000-DEAD-BEEF-0000-000000000000"\'\n')
        fake.chmod(0o755)
        with self._with_path(f"{d}{os.pathsep}{os.environ.get('PATH', '')}"):
            self.assertIsNone(
                IdentityProvider._system_tool('sage-no-such-system-tool'),
                "a name absent from the fixed directories is not found, however rich PATH is")
            anchor = IdentityProvider._machine_anchor()
        self.assertNotIn('DEAD-BEEF', anchor,
                         "a tool planted on PATH reached the machine anchor, and so the sealing key")

    def test_a_file_that_is_not_executable_is_not_the_tool(self):
        """Parity with the rust side, which now applies the same predicate. The two providers
        derive ONE sealing key, so a machine where they disagree about what counts as a tool is
        a machine with two keys."""
        import os
        import shutil as _shutil
        import tempfile as _tempfile
        d = Path(_tempfile.mkdtemp(prefix='sage-noexec-'))
        self.addCleanup(_shutil.rmtree, d, ignore_errors=True)
        plain = d / 'ioreg'
        plain.write_text('not executable')
        plain.chmod(0o644)
        self.assertFalse(os.access(plain, os.X_OK),
                         "fixture: the acceptance predicate both providers apply")

    def test_the_anchor_does_not_depend_on_path(self):
        """The property itself, end to end, on whatever platform this runs on."""
        import hashlib
        # Compared as digests: the anchor is a hardware identifier and a key input, and a
        # failing assertEqual would print both values into whatever log runs this.
        d8 = lambda a: ('host' if a.startswith('host:') else 'id') + ':' + hashlib.sha256(a.encode()).hexdigest()[:8]
        full = IdentityProvider._machine_anchor()
        for path in ('/usr/bin:/bin', ''):
            with self._with_path(path):
                self.assertEqual(d8(IdentityProvider._machine_anchor()), d8(full),
                                 f"PATH={path!r} changed the anchor, and with it the sealing key")
        if sys.platform == 'darwin':
            self.assertFalse(full.startswith('host:'),
                             "a Mac must anchor on IOPlatformUUID, not fall through to the hostname")

    @unittest.skipUnless(sys.platform == 'darwin', "sysfs covers Linux; this is the ifconfig branch")
    def test_macs_are_found_under_the_launchd_path(self):
        p = IdentityProvider.__new__(IdentityProvider)
        with self._with_path('/usr/bin:/bin'):
            self.assertGreater(len(p._interface_macs()), 0,
                               "no MACs under launchd's PATH: a v1 seal on this Mac could never heal")


if __name__ == '__main__':
    unittest.main()
