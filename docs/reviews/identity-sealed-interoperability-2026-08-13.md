# External review: Python/Rust sealed identity interoperability

Date: 2026-08-13

This note records an external-review finding independently verified against current `main`.

## Finding

The Python and Rust identity providers share the same sealed-file shape (`SAGE_SEALED_v1`, anchor line, then sealed bytes), but derive different software-sealing keys:

- Python: `hostname:uuid.getnode():instance_dir`
- Rust: `hostname:0:instance_dir`

Both then XOR the sealed bytes with the derived key. XOR provides no authentication, so unsealing with the wrong key still returns bytes rather than an error.

Both implementations also carry the same manifest fingerprint concept derived from the identity secret, but authorization currently accepts unsealed bytes without recomputing and comparing that fingerprint before constructing a signing context.

The practical consequence is a silent cross-language failure mode: a Rust provider reading an identity sealed by Python can produce a 32-byte secret that is wrong but syntactically acceptable. Relocating an instance directory creates the same failure class because the path participates in the derivation.

The Rust provider is currently effectively dormant outside tests, so this appears to be a latent interoperability defect rather than a production incident. That makes it cheap to fix before the Rust daemon begins depending on this path.

## Evidence grades

### Direct observation

- Identical sealed-file header/layout on both sides.
- Divergent machine-key derivation.
- Unconditional XOR unseal on both sides.
- No fingerprint verification before constructing the signing context.
- Matching fingerprint representation based on the secret.
- The Rust identity provider currently has no meaningful production call path beyond its local/test use.

### Inference

The Python and Rust identity providers are intended to consume the same sealed identity format.

No comment explicitly states that interoperability contract. The inference is based on the mirrored API, byte-identical magic/layout, and matching manifest/fingerprint representation. If that interpretation is disputed, the direct observations above still stand independently.

### Engineering estimate

The local hardening is small. That is an engineering judgment, not a measured patch size.

## Suggested repair

1. Define one canonical machine-key derivation and implement it identically in Python and Rust.
2. After unseal, recompute the secret fingerprint and compare it to the manifest before creating a signing context. A mismatch should fail authorization loudly.
3. Add cross-language fixtures:
   - Python seal -> Rust unseal
   - Rust seal -> Python unseal
   - wrong-machine negative control
   - relocated-instance negative control

The fingerprint check is useful even after derivation is aligned: it turns `wrong key -> plausible garbage` into `wrong key -> explicit identity failure` using identity evidence the subsystem already stores.

This is primarily an interface-integrity problem, not a criticism of the placeholder cryptography. Each implementation is internally self-consistent; the defect only appears at the boundary between them.
