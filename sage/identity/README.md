# SAGE Identity Module

Hardware-gated identity for SAGE instances. Three layers separate public manifest, hardware-sealed secrets, and attestation state.

## Three-Layer Architecture

| Layer | File | Contents | Access |
|-------|------|----------|--------|
| **A: Manifest** | `identity.json` | Name, LCT ID, public key fingerprint, anchor type, machine, model | Public. Readable by anyone, peers, dashboards. |
| **B: Sealed Secret** | `identity.sealed` | Encrypted root secret (identity private key material) | Hardware-gated. Only accessible via challenge-response from the bound anchor (TPM2, FIDO2, Secure Enclave). |
| **C: Attestation Cache** | `identity.attest.json` | Last successful `AttestationEnvelope` from Web4 | Cached proof of hardware verification. Expires based on freshness rules. |

## How It Works

```
IdentityProvider(instance_dir)
    │
    ├── load_manifest()          # Reads identity.json (Layer A)
    ├── authorize(challenge)     # Unseals identity.sealed via hardware (Layer B)
    │   └── returns SigningContext (in-memory, never persisted)
    └── attest(nonce)            # Produces AttestationEnvelope (Layer C)
        └── cached in identity.attest.json
```

**Authorization flow**:
1. Daemon starts or raising session begins
2. `IdentityProvider.authorize()` is called with a challenge
3. The provider attempts to unseal `identity.sealed` using the hardware anchor
4. On success, an in-memory `SigningContext` is returned (used for signing, never written to disk)
5. On failure (wrong hardware, missing sealed file), falls back to software mode (trust ceiling 0.4)

## Trust Ceilings by Anchor Type

| Anchor | Trust Ceiling | Notes |
|--------|--------------|-------|
| `tpm2` | 1.0 | Full hardware attestation with PCR platform state |
| `tpm2_no_pcr` | 0.85 | TPM without platform state verification |
| `fido2` | 0.9 | YubiKey or platform authenticator |
| `secure_enclave` | 0.85 | Apple Secure Enclave |
| `software` | 0.4 | Development fallback. No hardware binding. |

## Integration Points

- **Daemon startup** (`sage_daemon.py`): Calls `authorize()` to establish signing context before entering consciousness loop
- **Raising sessions**: Identity provider gates session initialization
- **Web4 AttestationEnvelope**: The attestation cache (Layer C) uses the canonical envelope format from `web4-core/python/web4/trust/attestation/`

## Migration Path

### Existing instances (no sealed file)
Backwards compatible. If `identity.sealed` does not exist, `IdentityProvider` operates in legacy mode:
- Reads `identity.json` as before
- Trust ceiling locked to `software` (0.4)
- All signing uses software-only HMAC
- No attestation cache generated

### Adding hardware binding to an existing instance
1. Generate a key pair and seal the private key to hardware: `python3 -m sage.identity.seal --anchor tpm2 --instance-dir <path>`
2. Update `identity.json` to set `anchor_type` and `public_key_fingerprint`
3. On next daemon start, `authorize()` will use hardware unsealing

### Future: FIDO2/YubiKey binding
The anchor verification modules exist in web4 (`web4-core/python/web4/trust/attestation/anchors/fido2.py`) but require the `fido2` Python package and a connected authenticator. The `IdentityProvider` is already anchor-agnostic — adding a new anchor type requires only a new verification module, no changes to `provider.py`.

## Key Files

| File | Purpose |
|------|---------|
| `provider.py` | `IdentityProvider`, `IdentityManifest`, `SigningContext` |
| `IDENTITY.md` | Developmental identity document (evolves with raising sessions) |
| `TRUST.md` | Trust principles and relationships |
| `PERMISSIONS.md` | Permission model documentation |
| `HISTORY.md` | Identity evolution history |

## Dependency

The attestation envelope format comes from Web4:
```
web4/web4-core/python/web4/trust/attestation/
├── envelope.py          # AttestationEnvelope dataclass
├── verify.py            # Unified verify_envelope()
└── anchors/
    ├── tpm2.py          # TPM 2.0 verification
    ├── fido2.py         # FIDO2/WebAuthn verification
    ├── secure_enclave.py # Apple SE verification
    └── software.py      # Software fallback verification
```

Import is optional — `provider.py` gracefully degrades if `web4` is not installed (uses built-in trust ceiling constants).

## Patent Alignment

The three-layer split maps to MetaLINXX 305 patent family:
- **US 11,477,027**: "Placing into use" = hardware authorization gate (Layer B)
- **US 12,278,913**: "Cryptographic association" = sealed secret binding anchor to identity record (Layer A + B linkage)
