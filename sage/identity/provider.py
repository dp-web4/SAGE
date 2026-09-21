"""
IdentityProvider — Three-layer hardware-gated identity.

Replaces the current pattern where identity.json IS the authority.
Now identity.json is a public manifest, the root secret is hardware-sealed,
and authorization requires hardware challenge-response.

Layer A: identity.json — public manifest (name, LCT, public key, anchor type)
Layer B: identity.sealed — encrypted root secret (only unseals with hardware)
Layer C: identity.attest.json — cached attestation envelope

Backwards compatible: if no sealed secret exists, falls back to legacy
mode (identity.json as authority with software-only trust ceiling).

Patent alignment: US 11,477,027 (placing into use), US 12,278,913 (record linking)
"""

import json
import os
import time
import hashlib
import secrets
import stat
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any

# Import AttestationEnvelope if available (web4 dependency)
try:
    from web4.trust.attestation.envelope import (
        AttestationEnvelope, AnchorInfo, Proof, PlatformState, TRUST_CEILINGS
    )
    HAS_ATTESTATION = True
except ImportError:
    HAS_ATTESTATION = False
    TRUST_CEILINGS = {
        'tpm2': 1.0, 'tpm2_no_pcr': 0.85, 'fido2': 0.9,
        'secure_enclave': 0.85, 'software': 0.4,
    }


@dataclass
class IdentityManifest:
    """Layer A: public identity information. Readable by anyone."""
    name: str
    lct_id: str
    public_key_fingerprint: str = ''
    anchor_type: str = 'software'
    machine: str = ''
    model: str = ''
    model_family: str = ''
    created: str = ''
    sealed_path: str = 'identity.sealed'
    trust_ceiling: float = 0.4
    status: str = 'active'


@dataclass
class SigningContext:
    """In-memory authorized signing context. Never persisted."""
    identity_secret: bytes
    public_key_fingerprint: str
    anchor_type: str
    authorized_at: float = field(default_factory=time.time)

    def sign(self, data: bytes) -> bytes:
        """Sign data with the identity secret (HMAC-SHA256 for now).

        In production, this would use the actual key pair derived from
        the identity secret. HMAC is a placeholder until real crypto
        (ECDSA P-256 via TPM/SE) is wired.
        """
        import hmac
        return hmac.new(self.identity_secret, data, hashlib.sha256).digest()

    @property
    def age_seconds(self) -> float:
        return time.time() - self.authorized_at


SEAL_V2 = b'SAGE_SEALED_v2'


class IdentityProvider:
    """
    Three-layer identity provider with hardware authorization gating.

    Manages:
    - identity.json (Layer A: public manifest)
    - identity.sealed (Layer B: encrypted root secret)
    - identity.attest.json (Layer C: attestation cache)

    The provider is the gatekeeper: the signing context only exists
    in memory after successful hardware authorization.
    """

    def __init__(self, instance_dir: str):
        self.instance_dir = Path(instance_dir)
        self.manifest_path = self.instance_dir / 'identity.json'
        self.sealed_path = self.instance_dir / 'identity.sealed'
        self.attest_path = self.instance_dir / 'identity.attest.json'

        self._manifest: Optional[IdentityManifest] = None
        self._context: Optional[SigningContext] = None  # Only exists when authorized

    @property
    def is_initialized(self) -> bool:
        """Whether the identity has been set up."""
        return self.manifest_path.exists()

    @property
    def is_authorized(self) -> bool:
        """Whether the identity is currently unlocked."""
        return self._context is not None

    @property
    def is_hardware_sealed(self) -> bool:
        """Whether a hardware-sealed secret exists."""
        return self.sealed_path.exists()

    @property
    def manifest(self) -> Optional[IdentityManifest]:
        """Read the public manifest (always accessible)."""
        if self._manifest is None and self.manifest_path.exists():
            self._load_manifest()
        return self._manifest

    @property
    def context(self) -> Optional[SigningContext]:
        """Get the signing context (only available when authorized)."""
        return self._context

    def initialize(self, name: str, lct_id: str, machine: str = '',
                   model: str = '', model_family: str = '',
                   anchor_type: str = 'software') -> IdentityManifest:
        """First-time identity setup.

        Generates a root secret, seals it (or stores as software fallback),
        creates the public manifest, and produces initial attestation.
        """
        # Generate root secret
        identity_secret = secrets.token_bytes(32)

        # Compute fingerprint
        fingerprint = hashlib.sha256(identity_secret).hexdigest()[:16]

        # Seal the secret. Everything below records the anchor ACHIEVED, not the one
        # requested — trust_ceiling prices how the secret is actually held, and no
        # hardware path is implemented yet, so a 'tpm2' request seals in software.
        anchor_type = self._seal_secret(identity_secret, anchor_type, lct_id=lct_id)

        # Create manifest (Layer A)
        manifest = IdentityManifest(
            name=name,
            lct_id=lct_id,
            public_key_fingerprint=fingerprint,
            anchor_type=anchor_type,
            machine=machine,
            model=model,
            model_family=model_family,
            created=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            trust_ceiling=TRUST_CEILINGS.get(anchor_type, 0.4),
        )
        self._manifest = manifest
        self._save_manifest()

        # Create initial attestation (Layer C)
        self._create_attestation(anchor_type, 'enrollment')

        # Authorize immediately after init
        self._context = SigningContext(
            identity_secret=identity_secret,
            public_key_fingerprint=fingerprint,
            anchor_type=anchor_type,
        )

        return manifest

    def authorize(self) -> Optional[SigningContext]:
        """Authorize the identity by unsealing the root secret.

        For TPM/FIDO2/SE: would perform hardware challenge-response.
        For software: reads the sealed file directly (low trust ceiling).

        Returns SigningContext if authorized, None if failed.
        """
        if not self.is_initialized:
            return None

        self._load_manifest()

        # Unseal the secret
        identity_secret = self._unseal_secret()
        if identity_secret is None:
            return None

        # VERIFY the unsealed secret actually produces the identity the manifest claims.
        # XOR sealing provides no authentication: unsealing with the wrong key returns
        # plausible bytes rather than an error (wrong machine, relocated instance dir, or
        # a file sealed by the other language's provider). Without this check, the context
        # below is constructed carrying the manifest's fingerprint ALONGSIDE a secret that
        # may not produce it — it does not merely skip verification, it asserts a binding
        # nobody checked, and _create_attestation() then publishes that fingerprint as the
        # envelope's public_key. The failure mode is a signed-shaped attestation naming an
        # identity the held secret cannot generate. Fail loudly instead.
        actual = hashlib.sha256(identity_secret).hexdigest()[:16]
        expected = self._manifest.public_key_fingerprint
        if expected and actual != expected:
            print(f"[Identity] AUTHORIZATION REFUSED: unsealed secret does not match the "
                  f"manifest identity (fingerprint {actual} != {expected}). The sealed file "
                  f"was sealed on a different machine, under a different LCT id, or is a v1 file whose "
                  f"former home is not recorded in instance.json `former_homes`. (A renamed home "
                  f"and the other language's provider are NOT causes under v2.) "
                  f"Not constructing a signing context.")
            return None

        self._context = SigningContext(
            identity_secret=identity_secret,
            public_key_fingerprint=self._manifest.public_key_fingerprint,
            anchor_type=self._manifest.anchor_type,
        )

        # Update attestation cache
        self._create_attestation(self._manifest.anchor_type, 'session_start')

        return self._context

    def lock(self):
        """Clear the in-memory signing context. Identity is no longer authorized."""
        if self._context:
            # Zero out the secret in memory
            self._context.identity_secret = b'\x00' * 32
            self._context = None

    def get_attestation(self) -> Optional[Dict]:
        """Read the cached attestation (Layer C)."""
        if not self.attest_path.exists():
            return None
        try:
            with open(self.attest_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    # === Legacy compatibility ===

    def load_legacy_state(self) -> Dict[str, Any]:
        """Load identity.json as the full state (legacy mode).

        This is backwards compatible with the current identity.json format
        where the file contains the complete identity state including
        development, relationships, memory_requests, etc.

        The three-layer split only affects the root secret and attestation.
        The mutable state (session count, phase, relationships) stays in
        identity.json as before.
        """
        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                return json.load(f)
        return {}

    def save_legacy_state(self, state: Dict[str, Any]):
        """Save full state back to identity.json (legacy mode)."""
        with open(self.manifest_path, 'w') as f:
            json.dump(state, f, indent=2)

    # === Internal methods ===

    def _load_manifest(self):
        """Load the public manifest from identity.json."""
        try:
            with open(self.manifest_path) as f:
                data = json.load(f)

            # Handle both new manifest format and legacy identity.json
            if 'identity' in data:
                # Legacy format — extract manifest fields from nested structure
                identity = data['identity']
                self._manifest = IdentityManifest(
                    name=identity.get('name', ''),
                    lct_id=identity.get('lct', ''),
                    public_key_fingerprint=identity.get('public_key_fingerprint', ''),
                    anchor_type=data.get('anchor_type', 'software'),
                    machine=identity.get('machine', ''),
                    model=identity.get('model', ''),
                    model_family=identity.get('model_family', ''),
                    created=identity.get('created', ''),
                    trust_ceiling=TRUST_CEILINGS.get(
                        data.get('anchor_type', 'software'), 0.4),
                )
            else:
                # New manifest format
                self._manifest = IdentityManifest(**{
                    k: v for k, v in data.items()
                    if k in IdentityManifest.__dataclass_fields__
                })
        except (json.JSONDecodeError, IOError, KeyError):
            self._manifest = None

    def _save_manifest(self):
        """Save the public manifest.

        If legacy identity.json exists (with development, relationships, etc.),
        merge manifest fields into it. Otherwise create a clean manifest.
        """
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path) as f:
                    existing = json.load(f)
                # Merge manifest fields into existing legacy structure
                if 'identity' in existing:
                    existing['identity']['public_key_fingerprint'] = self._manifest.public_key_fingerprint
                existing['anchor_type'] = self._manifest.anchor_type
                existing['trust_ceiling'] = self._manifest.trust_ceiling
                existing['sealed_path'] = self._manifest.sealed_path
                with open(self.manifest_path, 'w') as f:
                    json.dump(existing, f, indent=2)
                return
            except (json.JSONDecodeError, IOError):
                pass

        # New file — write clean manifest
        with open(self.manifest_path, 'w') as f:
            json.dump(asdict(self._manifest), f, indent=2)

    def _seal_secret(self, secret: bytes, anchor_type: str, lct_id: Optional[str] = None) -> str:
        """Seal the identity root secret. Returns the anchor ACTUALLY ACHIEVED.

        For software: XOR with machine-derived key (weak but functional).
        For TPM/FIDO2/SE: not yet implemented — falls back to software sealing,
        and says so in the return value rather than only on stdout.

        The return value is load-bearing: the caller records it as the manifest's
        anchor_type, which sets trust_ceiling. Returning the REQUESTED anchor here
        would let a caller mint a ceiling of 1.0 by passing the string 'tpm2' for a
        secret that is in fact XORed against sha256(hostname:mac:instance_dir).
        """
        # TODO: real hardware sealing, at which point each branch returns its OWN
        # anchor instead of falling through to software:
        #   tpm2           — TPM2 sealing via tpm2-tools or python-tpm2-pytss
        #   tpm2_no_pcr    — as above, without PCR binding
        #   fido2          — FIDO2 credential-based unwrap
        #   secure_enclave — Apple SE integration
        if anchor_type != 'software':
            # No hardware path is implemented on this provider yet. Downgrade the
            # anchor rather than the honesty: seal in software and REPORT software.
            print(f"[Identity] {anchor_type} sealing not yet implemented — "
                  f"using software fallback; anchor recorded as 'software'")
            anchor_type = 'software'

        # Software fallback: derive a machine key and XOR
        # This is NOT secure — it's a placeholder that makes the file
        # non-trivially copyable while the real TPM path is implemented
        machine_key = self._derive_machine_key_v2(lct_id)
        sealed = bytes(a ^ b for a, b in zip(secret, machine_key))
        tmp = self.sealed_path.with_suffix('.sealed.tmp')
        with open(tmp, 'wb') as f:
            f.write(SEAL_V2 + b'\n')
            f.write(anchor_type.encode() + b'\n')
            f.write(sealed)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.sealed_path)
        return anchor_type

    def _unseal_secret(self) -> Optional[bytes]:
        """Unseal the identity root secret.

        v2 files unseal with the one stable key. v1 files were sealed by one of THREE
        derivations that never agreed (see `_legacy_keys`), so every candidate is tried and
        the manifest's fingerprint picks the right one — XOR has no authentication of its
        own, the fingerprint is the only thing that can tell a right key from a wrong one.
        A v1 file that unseals is rewritten as v2 (the original kept as `identity.sealed.v1`).
        """
        if not self.sealed_path.exists():
            return None
        try:
            with open(self.sealed_path, 'rb') as f:
                header = f.readline().strip()
                anchor_line = f.readline().strip()
                sealed = f.read()
        except IOError:
            return None

        self._unsealed_with = None
        if header == SEAL_V2:
            self._unsealed_with = 'v2'
            return bytes(a ^ b for a, b in zip(sealed, self._derive_machine_key_v2()))
        if not header.startswith(b'SAGE_SEALED_v1'):
            return None

        expected = self._manifest.public_key_fingerprint if self._manifest else ''
        first = None
        for label, key in self._legacy_keys():
            secret = bytes(a ^ b for a, b in zip(sealed, key))
            if first is None:
                first = secret
            if expected and hashlib.sha256(secret).hexdigest()[:16] == expected:
                self._unsealed_with = label
                self._migrate_to_v2(secret, anchor_line.decode(errors='replace') or 'software', label)
                return secret
        # Nothing matched (or no fingerprint to match against): hand back the historical
        # first candidate so authorize()'s fingerprint check refuses it exactly as before.
        return first

    def _migrate_to_v2(self, secret: bytes, anchor_type: str, label: str):
        """Rewrite a verified v1 seal as v2, keeping the original beside it. Best effort:
        anything that stops the original being preserved leaves the v1 file in place, and it
        unseals again next time.

        INVARIANT (same in the Rust provider): the live v1 is replaced only after
        `identity.sealed.v1` exists as a regular file whose bytes EQUAL the live v1. "The copy
        did not raise" is not enough, and neither is "something is already there": a stale or
        unrelated file at that name — an interrupted earlier migration, a copied-in home —
        would otherwise be blessed as "the original" while the only real v1 specimen is
        overwritten. Authorization is unaffected either way; the caller already holds the
        verified secret."""
        try:
            keep = self.sealed_path.with_name('identity.sealed.v1')
            live = self.sealed_path.read_bytes()

            # Never follow a pre-existing final-component symlink while creating the backup.
            # Path.exists() follows symlinks, so a dangling link looks absent; opening with
            # mode 'xb' gives us O_CREAT|O_EXCL semantics instead. If another filesystem
            # object appears between lstat and create, exclusive creation fails rather than
            # following/reusing it.
            try:
                keep.lstat()
            except FileNotFoundError:
                try:
                    with open(keep, 'xb') as out:
                        out.write(live)
                        out.flush()
                        os.fsync(out.fileno())
                except FileExistsError:
                    pass

            try:
                keep_stat = keep.lstat()
            except FileNotFoundError:
                keep_stat = None
            preserved = (
                keep_stat is not None
                and stat.S_ISREG(keep_stat.st_mode)
                and keep.read_bytes() == live
            )
            if not preserved:
                print(f"[Identity] v1 seal verified with '{label}' but NOT migrated: "
                      f"{keep.name} is not a byte-identical regular-file copy of the live v1 file. "
                      f"The v1 file is left in place. Move {keep.name} aside to allow migration.")
                return
            self._seal_secret(secret, anchor_type)
            print(f"[Identity] sealed file migrated v1 -> v2 (it unsealed with the legacy "
                  f"'{label}' key; original kept as {keep.name}). Same secret, same fingerprint.")
        except OSError as e:
            print(f"[Identity] v1 seal verified with '{label}' but could not be rewritten as v2: {e}")

    @staticmethod
    def _system_tool(name: str) -> Optional[str]:
        """Absolute path of a system tool, WITHOUT consulting PATH. None when not found.

        NONE, NOT THE BARE NAME. The first cut returned `name`, and the very next
        `subprocess.run([name])` consults PATH again -- so on any machine where the fixed
        directories miss, the original defect came straight back and the test that pinned the
        bare-name fallback was pinning the escape hatch rather than the property (GPT seat,
        SAGE #130). A miss now skips the probe and falls through to the next anchor source,
        identically in every process on the machine, which is the only property that matters:
        the anchor is an input to the sealing key, so two processes must never disagree.

        Measured on McNugget (macOS, 2026-09-20): `ioreg` is /usr/sbin/ioreg and `ifconfig` is
        /sbin/ifconfig, and a launchd agent with no PATH key runs with `/usr/bin:/bin`. Looked
        up by bare name, both were found from a shell and NOT from the daemon's unit -- so one
        machine produced two anchors (IOPlatformUUID vs `host:<name>`), i.e. two v2 keys, and a
        seal written by either process was unreadable to the other. The failure was silent in
        both directions: the fallback is a valid anchor, just a different one."""
        for d in ('/usr/sbin', '/sbin', '/usr/bin', '/bin'):
            cand = os.path.join(d, name)
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
        return None

    @staticmethod
    def _machine_anchor() -> str:
        """A per-install identifier that does not move: /etc/machine-id (Linux, WSL),
        IOPlatformUUID (macOS), else the hostname. NOT a MAC: `uuid.getnode()` returns
        whichever interface it enumerates first, and that changed on Legion between
        2026-03-28 and 2026-09-19 (wifi -> a bridge), silently orphaning the seal."""
        for p in ('/etc/machine-id', '/var/lib/dbus/machine-id'):
            try:
                v = open(p).read().strip()
                if v:
                    return v
            except OSError:
                pass
        ioreg = IdentityProvider._system_tool('ioreg')
        if ioreg:
            try:
                import subprocess
                out = subprocess.run([ioreg, '-rd1', '-c', 'IOPlatformExpertDevice'],
                                     capture_output=True, text=True, timeout=5).stdout
                for line in out.splitlines():
                    if 'IOPlatformUUID' in line:
                        return line.split('"')[-2]
            except Exception:
                pass
        import socket
        return 'host:' + socket.gethostname()

    def _derive_machine_key_v2(self, lct_id: Optional[str] = None) -> bytes:
        """The v2 sealing key: sha256("sage-seal-v2:<machine anchor>:<lct id>").

        Bound to the MACHINE and the IDENTITY — not to the instance directory's path and
        not to a network interface. v1 bound the seal to `str(instance_dir)`, so renaming a
        being's home (the fleet's 2026-09-19 move to `<machine>-being/`) would have made a
        being raised since March unable to prove it was itself. Copying the files to another
        MACHINE is still refused; moving them on the same machine no longer is. This is still
        a placeholder, not security — the secret sits XORed beside a derivable key — and the
        Rust provider derives the identical bytes (sage-rs identity/provider.rs)."""
        # initialize() seals BEFORE the manifest exists, so it passes the lct explicitly
        lct = lct_id if lct_id is not None else (self._manifest.lct_id if self._manifest else '')
        return hashlib.sha256(f"sage-seal-v2:{self._machine_anchor()}:{lct}".encode()).digest()

    @staticmethod
    def _parse_ether_lines(text: str) -> list:
        """MACs (as the decimal integers `uuid.getnode()` would return) from `ifconfig -a` /
        `ip link` output: every `ether aa:bb:cc:dd:ee:ff` / `link/ether …` token."""
        import re
        out = []
        for a in re.findall(r"ether\s+((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})", text or ""):
            v = int(a.replace(":", ""), 16)
            if v and str(v) not in out:
                out.append(str(v))
        return out

    def _interface_macs(self) -> list:
        """Every interface MAC this machine has, as decimal strings. Linux: sysfs. macOS and
        anything else: parse `ifconfig -a` (no sysfs there — without this a Mac whose
        `uuid.getnode()` drifted could not recover its own v1 seal). Best effort, never raises."""
        import glob
        out = []
        for f in sorted(glob.glob('/sys/class/net/*/address')):
            try:
                a = open(f).read().strip()
                if a and a != '00:00:00:00:00:00':
                    m = str(int(a.replace(':', ''), 16))
                    if m not in out:
                        out.append(m)
            except (OSError, ValueError):
                pass
        ifconfig = self._system_tool('ifconfig') if not out else None
        if ifconfig:
            try:
                import subprocess
                txt = subprocess.run([ifconfig, '-a'], capture_output=True, text=True, timeout=5).stdout
                out = self._parse_ether_lines(txt)
            except Exception:
                pass
        return out

    def _legacy_keys(self):
        """Every key a v1 file on this machine could have been sealed with, most likely first.

        Three derivations existed and never agreed:
          python : sha256("<hostname>:<uuid.getnode()>:<instance_dir as passed>")
          rust   : sha256("<hostname>:0:<instance_dir as passed>")
          …and `uuid.getnode()` is not stable across boots when several interfaces exist.
        Path spellings tried: as passed, resolved absolute, and any `former_homes[].path`
        recorded in instance.json — so a renamed home heals itself on first authorize."""
        import socket
        import uuid
        import json as _json
        host = socket.gethostname()
        macs = [str(uuid.getnode())]
        for m in self._interface_macs():
            if m not in macs:
                macs.append(m)
        macs.append('0')   # the Rust provider's literal
        paths = [str(self.instance_dir)]
        try:
            r = str(self.instance_dir.resolve())
            if r not in paths:
                paths.append(r)
        except OSError:
            pass
        try:
            cfg = _json.loads((self.instance_dir / 'instance.json').read_text())
            for fh in cfg.get('former_homes') or []:
                if fh.get('path') and fh['path'] not in paths:
                    paths.append(str(fh['path']))
        except (OSError, ValueError):
            pass
        for p in paths:
            for m in macs:
                yield (f"v1 mac={m} path={p}", hashlib.sha256(f"{host}:{m}:{p}".encode()).digest())

    def _derive_machine_key(self) -> bytes:
        """The ORIGINAL v1 python derivation, kept only so old tests and tools can name it.
        New seals use `_derive_machine_key_v2`."""
        import socket
        import uuid
        machine_id = f"{socket.gethostname()}:{uuid.getnode()}:{self.instance_dir}"
        return hashlib.sha256(machine_id.encode()).digest()

    def _create_attestation(self, anchor_type: str, purpose: str):
        """Create and cache an attestation envelope (Layer C)."""
        if HAS_ATTESTATION and self._manifest:
            envelope = AttestationEnvelope(
                entity_id=self._manifest.lct_id,
                public_key=self._manifest.public_key_fingerprint,
                anchor=AnchorInfo(type=anchor_type),
                proof=Proof(
                    format='ecdsa_software',
                    signature='',  # Would be real signature with hardware
                    challenge=secrets.token_hex(16),
                ),
                purpose=purpose,
                issuer=self._manifest.machine,
            )
            with open(self.attest_path, 'w') as f:
                f.write(envelope.to_json())
        else:
            # Minimal attestation without web4 dependency
            attest = {
                'entity_id': self._manifest.lct_id if self._manifest else '',
                'anchor_type': anchor_type,
                'purpose': purpose,
                'timestamp': time.time(),
                'trust_ceiling': TRUST_CEILINGS.get(anchor_type, 0.4),
                'version': '0.1',
            }
            with open(self.attest_path, 'w') as f:
                json.dump(attest, f, indent=2)


# === Self-test ===

if __name__ == '__main__':
    import tempfile
    import shutil

    # Create a temp instance directory
    tmpdir = tempfile.mkdtemp(prefix='sage-identity-test-')
    try:
        provider = IdentityProvider(tmpdir)

        # Initialize
        assert not provider.is_initialized
        manifest = provider.initialize(
            name='test-instance',
            lct_id='lct://sage:test:agent@test',
            machine='test-machine',
            model='test-model:latest',
            anchor_type='software',
        )
        assert provider.is_initialized
        assert provider.is_authorized
        assert manifest.trust_ceiling == 0.4  # Software ceiling
        print(f'Initialized: {manifest.name} ({manifest.anchor_type})')
        print(f'Trust ceiling: {manifest.trust_ceiling}')
        print(f'Fingerprint: {manifest.public_key_fingerprint}')

        # Sign something
        sig = provider.context.sign(b'hello world')
        print(f'Signature: {sig.hex()[:32]}...')

        # Lock and re-authorize
        provider.lock()
        assert not provider.is_authorized

        context = provider.authorize()
        assert context is not None
        assert provider.is_authorized
        print('Re-authorization: OK')

        # Verify same signature
        sig2 = context.sign(b'hello world')
        assert sig == sig2
        print('Signature consistency: OK')

        # Check attestation
        attest = provider.get_attestation()
        assert attest is not None
        print(f'Attestation purpose: {attest.get("purpose", "?")}')

        # Check files exist
        assert (Path(tmpdir) / 'identity.json').exists()
        assert (Path(tmpdir) / 'identity.sealed').exists()
        assert (Path(tmpdir) / 'identity.attest.json').exists()
        print('Three-layer files: OK')

        # Legacy compatibility
        state = provider.load_legacy_state()
        assert state.get('anchor_type') == 'software'
        print('Legacy compatibility: OK')

        print('\n=== All self-tests passed ===')

    finally:
        shutil.rmtree(tmpdir)
