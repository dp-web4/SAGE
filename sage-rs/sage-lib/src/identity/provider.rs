use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::identity::signing::SigningContext;

const TRUST_CEILINGS: &[(&str, f64)] = &[
    ("tpm2", 1.0),
    ("tpm2_no_pcr", 0.85),
    ("fido2", 0.9),
    ("secure_enclave", 0.85),
    ("software", 0.4),
];

fn trust_ceiling_for(anchor_type: &str) -> f64 {
    TRUST_CEILINGS
        .iter()
        .find(|(k, _)| *k == anchor_type)
        .map(|(_, v)| *v)
        .unwrap_or(0.4)
}

fn now_epoch() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IdentityManifest {
    pub name: String,
    pub lct_id: String,
    #[serde(default)]
    pub public_key_fingerprint: String,
    #[serde(default = "default_anchor")]
    pub anchor_type: String,
    #[serde(default)]
    pub machine: String,
    #[serde(default)]
    pub model: String,
    #[serde(default)]
    pub model_family: String,
    #[serde(default)]
    pub created: String,
    #[serde(default = "default_sealed_path")]
    pub sealed_path: String,
    #[serde(default = "default_trust_ceiling")]
    pub trust_ceiling: f64,
    #[serde(default = "default_status")]
    pub status: String,
}

fn default_anchor() -> String { "software".to_string() }
fn default_sealed_path() -> String { "identity.sealed".to_string() }
fn default_trust_ceiling() -> f64 { 0.4 }
fn default_status() -> String { "active".to_string() }

/// Three-layer identity provider.
/// Layer A: identity.json (public manifest)
/// Layer B: identity.sealed (encrypted root secret)
/// Layer C: identity.attest.json (attestation cache)
pub struct IdentityProvider {
    instance_dir: PathBuf,
    manifest_path: PathBuf,
    sealed_path: PathBuf,
    attest_path: PathBuf,
    manifest: Option<IdentityManifest>,
    context: Option<SigningContext>,
    /// tests only: stand in for another machine's anchor
    anchor_override: Option<String>,
}

impl IdentityProvider {
    pub fn new(instance_dir: &Path) -> Self {
        let dir = instance_dir.to_path_buf();
        Self {
            manifest_path: dir.join("identity.json"),
            sealed_path: dir.join("identity.sealed"),
            attest_path: dir.join("identity.attest.json"),
            instance_dir: dir,
            manifest: None,
            context: None,
            anchor_override: None,
        }
    }

    pub fn is_initialized(&self) -> bool {
        self.manifest_path.exists()
    }

    pub fn is_authorized(&self) -> bool {
        self.context.is_some()
    }

    pub fn is_hardware_sealed(&self) -> bool {
        self.sealed_path.exists()
    }

    pub fn manifest(&mut self) -> Option<&IdentityManifest> {
        if self.manifest.is_none() && self.manifest_path.exists() {
            self.load_manifest();
        }
        self.manifest.as_ref()
    }

    pub fn context(&self) -> Option<&SigningContext> {
        self.context.as_ref()
    }

    /// First-time identity setup. Generates root secret, seals it, creates manifest.
    pub fn initialize(
        &mut self,
        name: &str,
        lct_id: &str,
        machine: &str,
        model: &str,
        anchor_type: &str,
    ) -> IdentityManifest {
        let secret = SigningContext::generate_secret();
        let fingerprint = SigningContext::fingerprint(&secret);

        // Everything below records the anchor ACHIEVED, not the one requested —
        // trust_ceiling prices how the secret is actually held, and this provider
        // seals only in software today.
        let achieved_anchor = self.seal_secret(&secret, anchor_type, lct_id);
        let anchor_type: &str = achieved_anchor.as_str();

        let manifest = IdentityManifest {
            name: name.to_string(),
            lct_id: lct_id.to_string(),
            public_key_fingerprint: fingerprint.clone(),
            anchor_type: anchor_type.to_string(),
            machine: machine.to_string(),
            model: model.to_string(),
            model_family: String::new(),
            created: chrono_now_utc(),
            sealed_path: "identity.sealed".to_string(),
            trust_ceiling: trust_ceiling_for(anchor_type),
            status: "active".to_string(),
        };

        self.manifest = Some(manifest.clone());
        self.save_manifest();
        self.create_attestation(anchor_type, "enrollment");

        self.context = Some(SigningContext::new(secret, &fingerprint, anchor_type));

        manifest
    }

    /// Unseal the root secret and authorize the identity.
    pub fn authorize(&mut self) -> Option<&SigningContext> {
        if !self.is_initialized() {
            return None;
        }
        self.load_manifest();

        let secret = self.unseal_secret()?;
        let manifest = self.manifest.as_ref()?;

        // VERIFY the unsealed secret produces the identity the manifest claims. XOR sealing
        // is unauthenticated: a wrong key (a different machine, a different LCT id, or a v1
        // file whose former home was never recorded) yields plausible bytes, not an error. Without this, the context below asserts the
        // manifest's fingerprint alongside a secret that may not produce it, and the
        // attestation publishes that unverified claim. Fail closed.
        let actual = SigningContext::fingerprint(&secret);
        if !manifest.public_key_fingerprint.is_empty() && actual != manifest.public_key_fingerprint {
            eprintln!(
                "[identity] AUTHORIZATION REFUSED: unsealed secret does not match the manifest \
                 identity (fingerprint {} != {}). Sealed on a different machine, under a different \
                 LCT id, or a v1 file whose former home is not in instance.json `former_homes`. \
                 (A renamed home and the other language's provider are NOT causes under v2.)",
                actual, manifest.public_key_fingerprint
            );
            return None;
        }

        self.context = Some(SigningContext::new(
            secret,
            &manifest.public_key_fingerprint,
            &manifest.anchor_type,
        ));

        self.create_attestation(&manifest.anchor_type.clone(), "session_start");
        self.context.as_ref()
    }

    /// Clear the in-memory signing context.
    pub fn lock(&mut self) {
        self.context = None;
    }

    /// Read the cached attestation (Layer C).
    pub fn get_attestation(&self) -> Option<serde_json::Value> {
        let data = std::fs::read_to_string(&self.attest_path).ok()?;
        serde_json::from_str(&data).ok()
    }

    /// Load identity.json as raw JSON (legacy compatibility).
    pub fn load_legacy_state(&self) -> serde_json::Value {
        std::fs::read_to_string(&self.manifest_path)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or(serde_json::Value::Object(serde_json::Map::new()))
    }

    // --- Internal ---

    fn load_manifest(&mut self) {
        let data = match std::fs::read_to_string(&self.manifest_path) {
            Ok(s) => s,
            Err(_) => return,
        };

        let json: serde_json::Value = match serde_json::from_str(&data) {
            Ok(v) => v,
            Err(_) => return,
        };

        // Handle legacy format with nested "identity" key
        if let Some(identity) = json.get("identity") {
            let anchor = json.get("anchor_type")
                .and_then(|v| v.as_str())
                .unwrap_or("software");

            self.manifest = Some(IdentityManifest {
                name: identity.get("name").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                lct_id: identity.get("lct").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                public_key_fingerprint: identity.get("public_key_fingerprint")
                    .and_then(|v| v.as_str()).unwrap_or("").to_string(),
                anchor_type: anchor.to_string(),
                machine: identity.get("machine").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                model: identity.get("model").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                model_family: identity.get("model_family").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                created: identity.get("created").and_then(|v| v.as_str()).unwrap_or("").to_string(),
                sealed_path: "identity.sealed".to_string(),
                trust_ceiling: trust_ceiling_for(anchor),
                status: "active".to_string(),
            });
        } else {
            self.manifest = serde_json::from_value(json).ok();
        }
    }

    fn save_manifest(&self) {
        let manifest = match &self.manifest {
            Some(m) => m,
            None => return,
        };
        let json = serde_json::to_string_pretty(manifest).unwrap_or_default();
        let _ = std::fs::write(&self.manifest_path, json);
    }

    /// Seal the root secret. Returns the anchor ACTUALLY ACHIEVED.
    ///
    /// This provider has no hardware path: the secret is always XORed against the v2
    /// machine key (`derive_machine_key_v2`: machine anchor + LCT id — not the hostname, not
    /// a MAC, not the instance path). So the achieved anchor is always "software",
    /// and a request for tpm2/fido2/secure_enclave is a downgrade, reported as one.
    ///
    /// The return value is load-bearing — the caller records it as the manifest's
    /// anchor_type, which drives trust_ceiling_for(). Recording the REQUESTED anchor
    /// instead would let a caller mint a ceiling of 1.0 for a software-sealed secret.
    fn seal_secret(&self, secret: &[u8], anchor_type: &str, lct_id: &str) -> String {
        let machine_key = self.derive_machine_key_v2(lct_id);
        let sealed: Vec<u8> = secret.iter().zip(machine_key.iter()).map(|(a, b)| a ^ b).collect();

        // TODO: real hardware sealing (tpm2, tpm2_no_pcr, fido2, secure_enclave), at
        // which point `achieved` becomes whichever anchor actually took effect.
        let achieved = "software";
        if !anchor_type.is_empty() && anchor_type != achieved {
            eprintln!(
                "[identity] {} sealing not yet implemented — using software fallback; \
                 anchor recorded as '{}'",
                anchor_type, achieved
            );
        }

        let mut content = format!("SAGE_SEALED_v2\n{}\n", achieved).into_bytes();
        content.extend_from_slice(&sealed);
        // write-then-rename: a torn identity.sealed is an identity lost
        let tmp = self.sealed_path.with_extension("sealed.tmp");
        if std::fs::write(&tmp, content).is_ok() {
            let _ = std::fs::rename(&tmp, &self.sealed_path);
        }
        achieved.to_string()
    }

    /// Unseal the root secret.
    ///
    /// v2 files unseal with the one stable key. v1 files were sealed by one of three
    /// derivations that never agreed (`legacy_keys`), so every candidate is tried and the
    /// manifest's fingerprint picks the right one — XOR authenticates nothing, the
    /// fingerprint is the only thing that tells a right key from a wrong one. A v1 file that
    /// verifies is rewritten as v2, the original kept as `identity.sealed.v1`.
    fn unseal_secret(&self) -> Option<Vec<u8>> {
        let data = std::fs::read(&self.sealed_path).ok()?;
        let first_nl = data.iter().position(|&b| b == b'\n')?;
        let header = &data[..first_nl];
        let second_nl = data[first_nl + 1..].iter().position(|&b| b == b'\n')? + first_nl + 1;
        let anchor = String::from_utf8_lossy(&data[first_nl + 1..second_nl]).trim().to_string();
        let sealed = &data[second_nl + 1..];
        let xor = |key: &[u8]| -> Vec<u8> { sealed.iter().zip(key.iter()).map(|(a, b)| a ^ b).collect() };
        let lct = self.manifest.as_ref().map(|m| m.lct_id.clone()).unwrap_or_default();

        if header == b"SAGE_SEALED_v2" {
            return Some(xor(&self.derive_machine_key_v2(&lct)));
        }
        if header != b"SAGE_SEALED_v1" {
            return None;
        }
        let expected = self.manifest.as_ref().map(|m| m.public_key_fingerprint.clone()).unwrap_or_default();
        let mut first: Option<Vec<u8>> = None;
        for (label, key) in self.legacy_keys() {
            let secret = xor(&key);
            if first.is_none() {
                first = Some(secret.clone());
            }
            if !expected.is_empty() && SigningContext::fingerprint(&secret) == expected {
                // INVARIANT (same in the python provider): the live v1 is replaced only after
                // `identity.sealed.v1` exists as a regular file whose bytes EQUAL the live v1.
                // A copy whose result is discarded is not that, and neither is "something is
                // already there" — a stale or unrelated file at that name would be blessed as
                // "the original" while the only real v1 specimen is overwritten. Authorization
                // is unaffected either way: the verified secret is returned below regardless.
                let keep = self.sealed_path.with_file_name("identity.sealed.v1");

                // Do not use Path::exists() here: it follows symlinks, so a dangling final
                // component looks absent. create_new is O_CREAT|O_EXCL semantics; a symlink,
                // directory, stale file, or a racing creator makes it fail rather than being
                // followed/reused as the backup destination.
                let absent = match std::fs::symlink_metadata(&keep) {
                    Err(e) if e.kind() == std::io::ErrorKind::NotFound => true,
                    _ => false,
                };
                if absent {
                    use std::io::Write;
                    if let Ok(mut out) = std::fs::OpenOptions::new()
                        .write(true)
                        .create_new(true)
                        .open(&keep)
                    {
                        let _ = out.write_all(&data);
                        let _ = out.sync_all();
                    }
                }
                let preserved = std::fs::symlink_metadata(&keep).map(|m| m.is_file()).unwrap_or(false)
                    && std::fs::read(&keep).map(|b| b == data).unwrap_or(false);
                if preserved {
                    self.seal_secret(&secret, if anchor.is_empty() { "software" } else { &anchor }, &lct);
                    eprintln!(
                        "[identity] sealed file migrated v1 -> v2 (unsealed with legacy '{}'; original \
                         kept as identity.sealed.v1). Same secret, same fingerprint.", label);
                } else {
                    eprintln!(
                        "[identity] v1 seal verified with '{}' but NOT migrated: identity.sealed.v1 is \
                         not a byte-identical regular-file copy of the live v1. The v1 file is left in \
                         place. Move identity.sealed.v1 aside to allow migration.", label);
                }
                return Some(secret);
            }
        }
        // nothing verified: hand back the historical first candidate so authorize()'s
        // fingerprint check refuses it exactly as before. An unverified file is never rewritten.
        first
    }

    /// A per-install identifier that does not move: /etc/machine-id (Linux, WSL),
    /// IOPlatformUUID (macOS), else the hostname. NOT a MAC — python's `uuid.getnode()`
    /// changed interface on Legion between 2026-03-28 and 2026-09-19 and orphaned the seal.
    /// Must return the same string as python `IdentityProvider._machine_anchor`.
    fn machine_anchor() -> String {
        for p in ["/etc/machine-id", "/var/lib/dbus/machine-id"] {
            if let Ok(v) = std::fs::read_to_string(p) {
                let v = v.trim();
                if !v.is_empty() {
                    return v.to_string();
                }
            }
        }
        if let Ok(out) = std::process::Command::new("ioreg")
            .args(["-rd1", "-c", "IOPlatformExpertDevice"]).output()
        {
            for line in String::from_utf8_lossy(&out.stdout).lines() {
                if line.contains("IOPlatformUUID") {
                    let parts: Vec<&str> = line.split('"').collect();
                    if parts.len() >= 2 {
                        return parts[parts.len() - 2].to_string();
                    }
                }
            }
        }
        let h = hostname::get().map(|h| h.to_string_lossy().to_string())
            .unwrap_or_else(|_| "unknown".to_string());
        format!("host:{}", h)
    }

    /// v2 sealing key: sha256("sage-seal-v2:<machine anchor>:<lct id>") — byte-identical to
    /// the python provider. Bound to the machine and the identity, NOT to the instance
    /// directory's path: v1 bound to the path, so renaming a being's home (the fleet's
    /// 2026-09-19 move to `<machine>-being/`) would have orphaned an identity raised since
    /// March. Another MACHINE is still refused. Still a placeholder, not security.
    fn derive_machine_key_v2(&self, lct_id: &str) -> Vec<u8> {
        Self::key_v2_from(&self.anchor_override.clone().unwrap_or_else(Self::machine_anchor), lct_id)
    }

    fn key_v2_from(anchor: &str, lct_id: &str) -> Vec<u8> {
        use sha2::{Sha256, Digest};
        Sha256::digest(format!("sage-seal-v2:{}:{}", anchor, lct_id).as_bytes()).to_vec()
    }

    /// MACs, as the decimal integers python's `uuid.getnode()` returns, from `ifconfig -a` /
    /// `ip link` text: every `ether aa:bb:cc:dd:ee:ff` token.
    fn parse_ether_lines(text: &str) -> Vec<String> {
        let mut out: Vec<String> = Vec::new();
        let toks: Vec<&str> = text.split_whitespace().collect();
        for w in toks.windows(2) {
            if w[0].ends_with("ether") {
                let hexs = w[1].replace(':', "");
                if hexs.len() == 12 && w[1].matches(':').count() == 5 {
                    if let Ok(v) = u64::from_str_radix(&hexs, 16) {
                        if v != 0 && !out.contains(&v.to_string()) {
                            out.push(v.to_string());
                        }
                    }
                }
            }
        }
        out
    }

    /// Every interface MAC on this machine. Linux: sysfs. macOS and anything else: parse
    /// `ifconfig -a` — there is no sysfs there, and without this a Mac whose python
    /// `uuid.getnode()` drifted could not recover its own v1 seal. Best effort.
    fn interface_macs() -> Vec<String> {
        let mut out: Vec<String> = Vec::new();
        if let Ok(rd) = std::fs::read_dir("/sys/class/net") {
            let mut names: Vec<_> = rd.flatten().map(|e| e.path()).collect();
            names.sort();
            for n in names {
                if let Ok(a) = std::fs::read_to_string(n.join("address")) {
                    if let Ok(v) = u64::from_str_radix(&a.trim().replace(':', ""), 16) {
                        if v != 0 && !out.contains(&v.to_string()) {
                            out.push(v.to_string());
                        }
                    }
                }
            }
        }
        if out.is_empty() {
            if let Ok(o) = std::process::Command::new("ifconfig").arg("-a").output() {
                out = Self::parse_ether_lines(&String::from_utf8_lossy(&o.stdout));
            }
        }
        out
    }

    /// Every key a v1 file on this machine could have been sealed with:
    ///   rust   : sha256("<hostname>:0:<instance_dir as passed>")
    ///   python : sha256("<hostname>:<uuid.getnode()>:<instance_dir>") — getnode is some
    ///            interface's MAC as a decimal integer, so every interface is tried.
    /// Paths: as passed, canonical, and `former_homes[].path` from instance.json, so a
    /// renamed home heals itself on first authorize.
    fn legacy_keys(&self) -> Vec<(String, Vec<u8>)> {
        use sha2::{Sha256, Digest};
        let host = hostname::get().map(|h| h.to_string_lossy().to_string())
            .unwrap_or_else(|_| "unknown".to_string());
        let mut macs: Vec<String> = vec!["0".to_string()];
        for m in Self::interface_macs() {
            if !macs.contains(&m) {
                macs.push(m);
            }
        }
        let mut paths: Vec<String> = vec![self.instance_dir.display().to_string()];
        if let Ok(c) = self.instance_dir.canonicalize() {
            let c = c.display().to_string();
            if !paths.contains(&c) {
                paths.push(c);
            }
        }
        if let Ok(txt) = std::fs::read_to_string(self.instance_dir.join("instance.json")) {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(&txt) {
                if let Some(arr) = v.get("former_homes").and_then(|f| f.as_array()) {
                    for fh in arr {
                        if let Some(p) = fh.get("path").and_then(|p| p.as_str()) {
                            if !paths.contains(&p.to_string()) {
                                paths.push(p.to_string());
                            }
                        }
                    }
                }
            }
        }
        let mut out = Vec::new();
        for p in &paths {
            for m in &macs {
                out.push((format!("v1 mac={} path={}", m, p),
                          Sha256::digest(format!("{}:{}:{}", host, m, p).as_bytes()).to_vec()));
            }
        }
        out
    }

    /// The ORIGINAL v1 rust derivation. New seals use `derive_machine_key_v2`.
    #[allow(dead_code)]
    fn derive_machine_key(&self) -> Vec<u8> {
        use sha2::{Sha256, Digest};
        let hostname = hostname::get()
            .map(|h| h.to_string_lossy().to_string())
            .unwrap_or_else(|_| "unknown".to_string());
        let machine_id = format!("{}:0:{}", hostname, self.instance_dir.display());
        let hash = Sha256::digest(machine_id.as_bytes());
        hash.to_vec()
    }

    fn create_attestation(&self, anchor_type: &str, purpose: &str) {
        let entity_id = self.manifest.as_ref()
            .map(|m| m.lct_id.as_str())
            .unwrap_or("");

        let attest = serde_json::json!({
            "entity_id": entity_id,
            "anchor_type": anchor_type,
            "purpose": purpose,
            "timestamp": now_epoch(),
            "trust_ceiling": trust_ceiling_for(anchor_type),
            "version": "0.1",
        });

        let _ = std::fs::write(
            &self.attest_path,
            serde_json::to_string_pretty(&attest).unwrap_or_default(),
        );
    }
}

fn chrono_now_utc() -> String {
    let secs = now_epoch() as u64;
    let days = secs / 86400;
    let rem = secs % 86400;
    let h = rem / 3600;
    let m = (rem % 3600) / 60;
    let s = rem % 60;
    // Approximate date — good enough for a timestamp string
    format!("{days}d-{h:02}:{m:02}:{s:02}Z")
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    /// Per-test directory. Keyed on the test NAME as well as the pid: cargo runs
    /// tests as threads of one process, so a pid-only key gave every test the same
    /// directory and let one test's cleanup() delete another's identity mid-run.
    fn temp_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir()
            .join(format!("sage-id-test-{}-{}", std::process::id(), name));
        let _ = fs::remove_dir_all(&dir);
        let _ = fs::create_dir_all(&dir);
        dir
    }

    fn cleanup(dir: &Path) {
        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn full_lifecycle() {
        let dir = temp_dir("full_lifecycle");
        let mut provider = IdentityProvider::new(&dir);

        assert!(!provider.is_initialized());
        assert!(!provider.is_authorized());

        let manifest = provider.initialize("test", "lct://test", "testmachine", "model:1b", "software");
        assert!(provider.is_initialized());
        assert!(provider.is_authorized());
        assert_eq!(manifest.trust_ceiling, 0.4);
        assert!(!manifest.public_key_fingerprint.is_empty());

        // Sign something
        let sig = provider.context().unwrap().sign(b"hello");
        assert_eq!(sig.len(), 32);

        // Lock and re-authorize
        provider.lock();
        assert!(!provider.is_authorized());

        let ctx = provider.authorize().unwrap();
        let sig2 = ctx.sign(b"hello");
        assert_eq!(sig, sig2);

        // Attestation exists
        let attest = provider.get_attestation().unwrap();
        assert_eq!(attest["anchor_type"], "software");

        // Files exist
        assert!(dir.join("identity.json").exists());
        assert!(dir.join("identity.sealed").exists());
        assert!(dir.join("identity.attest.json").exists());

        cleanup(&dir);
    }

    /// A requested anchor this provider cannot actually deliver must NOT be recorded.
    ///
    /// There is no hardware sealing here — every secret is XORed against the v2 machine key
    /// (machine anchor + LCT id). Recording the REQUESTED anchor would publish
    /// trust_ceiling 1.0 (tpm2) for a software-sealed secret, i.e. let a caller mint
    /// the fleet's highest trust ceiling by passing a string.
    #[test]
    fn requested_hardware_anchor_is_downgraded_not_claimed() {
        let dir = temp_dir("anchor_downgrade");
        let mut provider = IdentityProvider::new(&dir);

        let manifest = provider.initialize("test", "lct://test", "m", "model:1b", "tpm2");

        // The manifest prices how the secret is HELD, not what was asked for.
        assert_eq!(manifest.anchor_type, "software");
        assert_eq!(manifest.trust_ceiling, 0.4);

        // The sealed header agrees.
        let sealed = fs::read(dir.join("identity.sealed")).unwrap();
        let text = String::from_utf8_lossy(&sealed[..sealed.len().min(64)]).to_string();
        let mut lines = text.lines();
        assert_eq!(lines.next().unwrap(), "SAGE_SEALED_v2");
        assert_eq!(lines.next().unwrap(), "software");

        // So does the attestation, which is what peers actually read.
        let attest = provider.get_attestation().unwrap();
        assert_eq!(attest["anchor_type"], "software");
        assert_eq!(attest["trust_ceiling"], 0.4);

        // And it survives a re-authorize, which reloads from disk.
        provider.lock();
        assert!(provider.authorize().is_some());
        assert_eq!(provider.manifest().unwrap().anchor_type, "software");

        cleanup(&dir);
    }

    fn copy_identity(from: &Path, to: &Path) {
        for f in ["identity.json", "identity.sealed", "identity.attest.json"] {
            fs::copy(from.join(f), to.join(f)).unwrap();
        }
    }

    /// The property the old relocation test protected, restated for v2: a sealed file whose
    /// key no longer derives is REFUSED, never unsealed into plausible garbage. v2 binds to
    /// the machine, so "no longer derives" now means another machine.
    #[test]
    fn identity_moved_to_another_machine_is_refused() {
        let origin = temp_dir("othermachine_origin");
        let mut provider = IdentityProvider::new(&origin);
        let manifest = provider.initialize("test", "lct://test", "m", "model:1b", "software");
        assert!(provider.is_authorized());
        let moved = temp_dir("othermachine_moved");
        copy_identity(&origin, &moved);
        let mut relocated = IdentityProvider::new(&moved);
        relocated.anchor_override = Some("some-other-machine-id".into());
        assert!(relocated.authorize().is_none(),
            "identity from another machine must be REFUSED (fingerprint {})", manifest.public_key_fingerprint);
        assert!(!relocated.is_authorized());
        cleanup(&origin);
        cleanup(&moved);
    }

    /// 2026-09-19: being homes are renamed to <machine>-being/. v1 sealed against the
    /// instance path, so the rename would have orphaned an identity raised since March.
    #[test]
    fn renamed_home_on_the_same_machine_keeps_its_identity() {
        let origin = temp_dir("rename_origin");
        let mut provider = IdentityProvider::new(&origin);
        let manifest = provider.initialize("test", "lct://test", "m", "model:1b", "software");
        let moved = temp_dir("rename_moved");
        copy_identity(&origin, &moved);
        let mut renamed = IdentityProvider::new(&moved);
        let ctx = renamed.authorize().expect("a rename on the same machine must not orphan the identity");
        assert_eq!(ctx.fingerprint, manifest.public_key_fingerprint);
        cleanup(&origin);
        cleanup(&moved);
    }

    fn write_v1(dir: &Path, secret: &[u8], mac: &str, path: &str) {
        use sha2::{Sha256, Digest};
        let host = hostname::get().unwrap().to_string_lossy().to_string();
        let key = Sha256::digest(format!("{}:{}:{}", host, mac, path).as_bytes());
        let mut content = b"SAGE_SEALED_v1\nsoftware\n".to_vec();
        content.extend(secret.iter().zip(key.iter()).map(|(a, b)| a ^ b));
        fs::write(dir.join("identity.sealed"), content).unwrap();
    }

    /// Legion's real case: sealed by the PYTHON provider (a MAC, not "0") under a former
    /// home. The secret below has a known fingerprint; the MAC is one no interface here has,
    /// so only the `former_homes` + rust-"0" path can be exercised portably — the python-MAC
    /// leg is pinned in sage/tests/test_identity_provider_anchor.py and on the real file.
    #[test]
    fn v1_under_a_former_home_heals_and_migrates_keeping_the_original() {
        let dir = temp_dir("v1_former");
        let mut provider = IdentityProvider::new(&dir);
        let manifest = provider.initialize("test", "lct://test", "m", "model:1b", "software");
        let secret = provider.unseal_secret().unwrap();
        write_v1(&dir, &secret, "0", "/old/home/legion-gemma3-12b");
        fs::write(dir.join("instance.json"),
            r#"{"former_homes":[{"path":"/old/home/legion-gemma3-12b","moved":"2026-09-19"}]}"#).unwrap();
        let mut again = IdentityProvider::new(&dir);
        let ctx = again.authorize().expect("former_homes must heal a renamed v1 seal");
        assert_eq!(ctx.fingerprint, manifest.public_key_fingerprint);
        let now = fs::read(dir.join("identity.sealed")).unwrap();
        assert!(now.starts_with(b"SAGE_SEALED_v2"), "verified v1 migrates to v2");
        let kept = fs::read(dir.join("identity.sealed.v1")).expect("original v1 kept");
        assert!(kept.starts_with(b"SAGE_SEALED_v1"));
        assert!(IdentityProvider::new(&dir).authorize().is_some(), "migrated file authorizes alone");
        cleanup(&dir);
    }

    // --- the backup-before-rewrite invariant, four arms (same four in the python suite) ---

    fn v1_fixture(tag: &str) -> (std::path::PathBuf, String, Vec<u8>) {
        let dir = temp_dir(tag);
        let mut provider = IdentityProvider::new(&dir);
        let manifest = provider.initialize("test", "lct://test", "m", "model:1b", "software");
        let secret = provider.unseal_secret().unwrap();
        write_v1(&dir, &secret, "0", dir.to_str().unwrap());
        let original = fs::read(dir.join("identity.sealed")).unwrap();
        (dir, manifest.public_key_fingerprint, original)
    }

    #[test]
    fn migration_arm1_no_backup_creates_a_byte_identical_one_then_rewrites() {
        let (dir, fp, original) = v1_fixture("mig_arm1");
        let mut again = IdentityProvider::new(&dir);
        let ctx = again.authorize().expect("verified v1 authorizes");
        assert_eq!(ctx.fingerprint, fp);
        assert_eq!(fs::read(dir.join("identity.sealed.v1")).unwrap(), original);
        assert!(fs::read(dir.join("identity.sealed")).unwrap().starts_with(b"SAGE_SEALED_v2"));
        cleanup(&dir);
    }

    #[test]
    fn migration_arm2_backup_impossible_authorizes_but_does_not_rewrite() {
        let (dir, fp, original) = v1_fixture("mig_arm2");
        fs::create_dir(dir.join("identity.sealed.v1")).unwrap(); // a directory: cannot be the backup
        let mut again = IdentityProvider::new(&dir);
        let ctx = again.authorize().expect("a verified v1 still authorizes");
        assert_eq!(ctx.fingerprint, fp);
        assert_eq!(fs::read(dir.join("identity.sealed")).unwrap(), original,
            "the live v1 was replaced with no backup of it");
        cleanup(&dir);
    }

    /// HUB induced this on a real seal 2026-09-20 (python provider, same guard): unrelated
    /// bytes already at identity.sealed.v1, the live v1 replaced anyway, the v1 bytes
    /// surviving nowhere.
    #[test]
    fn migration_arm3_stale_backup_is_not_blessed_as_the_original() {
        let (dir, fp, original) = v1_fixture("mig_arm3");
        fs::write(dir.join("identity.sealed.v1"), b"NOT THE ORIGINAL").unwrap();
        let mut again = IdentityProvider::new(&dir);
        let ctx = again.authorize().expect("a verified v1 still authorizes");
        assert_eq!(ctx.fingerprint, fp);
        assert_eq!(fs::read(dir.join("identity.sealed")).unwrap(), original,
            "the live v1 was replaced beside a stale backup");
        assert_eq!(fs::read(dir.join("identity.sealed.v1")).unwrap(), b"NOT THE ORIGINAL");
        cleanup(&dir);
    }

    #[cfg(unix)]
    #[test]
    fn migration_arm4_dangling_symlink_is_never_followed() {
        use std::os::unix::fs::symlink;

        let (dir, fp, original) = v1_fixture("mig_arm4");
        let target = dir.parent().unwrap().join(format!(
            "{}-must-not-be-created",
            dir.file_name().unwrap().to_string_lossy()
        ));
        let _ = fs::remove_file(&target);
        let keep = dir.join("identity.sealed.v1");
        symlink(&target, &keep).unwrap();

        let mut again = IdentityProvider::new(&dir);
        let ctx = again.authorize().expect("a verified v1 still authorizes");
        assert_eq!(ctx.fingerprint, fp);
        assert_eq!(fs::read(dir.join("identity.sealed")).unwrap(), original,
            "the live v1 changed beside a dangling symlink");
        assert!(std::fs::symlink_metadata(&keep).unwrap().file_type().is_symlink(),
            "the backup symlink itself was replaced");
        assert!(!target.exists(),
            "migration followed the dangling symlink outside the being home");

        let _ = fs::remove_file(&target);
        cleanup(&dir);
    }

    #[test]
    fn v1_that_no_candidate_unseals_is_refused_and_never_rewritten() {
        let dir = temp_dir("v1_nomatch");
        let mut provider = IdentityProvider::new(&dir);
        provider.initialize("test", "lct://test", "m", "model:1b", "software");
        let secret = provider.unseal_secret().unwrap();
        write_v1(&dir, &secret, "123456789", "/nowhere/anyone/recorded");
        let mut again = IdentityProvider::new(&dir);
        assert!(again.authorize().is_none());
        assert!(fs::read(dir.join("identity.sealed")).unwrap().starts_with(b"SAGE_SEALED_v1"));
        cleanup(&dir);
    }

    /// No sysfs on macOS: MACs come from `ifconfig -a`. Same sample, same expected values as
    /// python's test_macos_ifconfig_macs_are_candidates_for_v1_recovery.
    #[test]
    fn macos_ifconfig_macs_parse_to_getnode_decimals() {
        let sample = "lo0: flags=8049<UP> mtu 16384\n\tinet 127.0.0.1 netmask 0xff000000\n\
                      en0: flags=8863<UP> mtu 1500\n\tether f0:18:98:aa:bb:cc\n\
                      en1: flags=8963<UP> mtu 1500\n\tether 36:6f:24:00:11:22\n\
                      bridge0: flags=8863 mtu 1500\n\tether 36:6f:24:00:11:22\n";
        assert_eq!(IdentityProvider::parse_ether_lines(sample),
                   vec![0xf01898aabbccu64.to_string(), 0x366f24001122u64.to_string()]);
    }

    /// Pins the bytes the python provider mirrors (test_v2_key_is_the_documented_bytes).
    #[test]
    fn v2_key_is_the_documented_bytes() {
        use sha2::{Sha256, Digest};
        assert_eq!(IdentityProvider::key_v2_from("ANCHOR", "lct://sage:test:agent@test"),
                   Sha256::digest(b"sage-seal-v2:ANCHOR:lct://sage:test:agent@test").to_vec());
    }

    #[test]
    fn loads_real_sprout_identity() {
        let sprout_dir = Path::new("/home/sprout/ai-workspace/SAGE/sage/instances/sprout-qwen3.5-0.8b");
        if !sprout_dir.join("identity.json").exists() {
            return; // Skip if not on Sprout
        }

        let mut provider = IdentityProvider::new(sprout_dir);
        assert!(provider.is_initialized());

        let manifest = provider.manifest().unwrap();
        assert!(!manifest.name.is_empty());
        assert!(!manifest.lct_id.is_empty());
    }
}
