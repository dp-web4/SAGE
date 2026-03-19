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

        # Seal the secret based on anchor type
        self._seal_secret(identity_secret, anchor_type)

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

    def _seal_secret(self, secret: bytes, anchor_type: str):
        """Seal the identity root secret.

        For software: XOR with machine-derived key (weak but functional).
        For TPM/FIDO2/SE: placeholder for real hardware sealing.
        """
        if anchor_type == 'software':
            # Software fallback: derive a machine key and XOR
            # This is NOT secure — it's a placeholder that makes the file
            # non-trivially copyable while the real TPM path is implemented
            machine_key = self._derive_machine_key()
            sealed = bytes(a ^ b for a, b in zip(secret, machine_key))
            with open(self.sealed_path, 'wb') as f:
                f.write(b'SAGE_SEALED_v1\n')
                f.write(anchor_type.encode() + b'\n')
                f.write(sealed)
        elif anchor_type == 'tpm2':
            # TODO: TPM2 sealing via tpm2-tools or python-tpm2-pytss
            # For now, fall back to software sealing with a note
            self._seal_secret(secret, 'software')
            print("[Identity] TPM2 sealing not yet implemented — using software fallback")
        elif anchor_type == 'fido2':
            # TODO: FIDO2 credential-based unwrap
            self._seal_secret(secret, 'software')
            print("[Identity] FIDO2 sealing not yet implemented — using software fallback")
        elif anchor_type == 'secure_enclave':
            # TODO: Apple SE integration
            self._seal_secret(secret, 'software')
            print("[Identity] Secure Enclave sealing not yet implemented — using software fallback")

    def _unseal_secret(self) -> Optional[bytes]:
        """Unseal the identity root secret."""
        if not self.sealed_path.exists():
            return None

        try:
            with open(self.sealed_path, 'rb') as f:
                header = f.readline()  # SAGE_SEALED_v1
                anchor_line = f.readline().strip()
                sealed = f.read()

            if not header.startswith(b'SAGE_SEALED_v1'):
                return None

            # Software unsealing
            machine_key = self._derive_machine_key()
            secret = bytes(a ^ b for a, b in zip(sealed, machine_key))
            return secret

        except IOError:
            return None

    def _derive_machine_key(self) -> bytes:
        """Derive a machine-specific key for software sealing.

        Uses hostname + MAC + instance dir as entropy sources.
        This is NOT cryptographically strong — it's a placeholder
        that makes naive file copying fail while real hardware
        sealing is implemented.
        """
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
