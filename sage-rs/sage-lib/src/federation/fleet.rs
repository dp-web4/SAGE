use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MachineInfo {
    // Every string field defaults, and null deserializes to empty rather than refusing.
    // WHY: serde rejects the WHOLE manifest on one bad field, so a single incomplete
    // machine entry silently removes every peer from every daemon in the fleet. Measured
    // on Legion 2026-09-07: `pub` (a society-host added 2026-08-28 with "Network coords
    // TBD") carries `"gateway_host": null`, and that one null cost all EIGHT machines
    // their federation — /peers returned [] while the startup line still said
    // "federation=active". A member we cannot reach yet should be unreachable, not fatal.
    #[serde(default)]
    pub pool: String,
    #[serde(default)]
    pub lct_id: String,
    #[serde(default, deserialize_with = "null_to_empty")]
    pub mdns_name: String,
    #[serde(default, deserialize_with = "null_to_empty")]
    pub gateway_host: String,
    #[serde(default, deserialize_with = "null_to_empty")]
    pub last_seen_ip: String,
    #[serde(default)]
    pub gateway_port: u16,
    #[serde(default)]
    pub federation_port: u16,
    #[serde(default)]
    pub model_default: String,
    #[serde(default)]
    pub device: String,
    #[serde(default)]
    pub hardware: String,
}

#[derive(Debug, Deserialize)]
struct FleetManifest {
    #[serde(default)]
    fleet_version: u32,
    machines: HashMap<String, MachineInfo>,
}

/// A JSON null in a string field becomes "", not a parse failure. See MachineInfo.
fn null_to_empty<'de, D>(d: D) -> Result<String, D::Error>
where
    D: serde::Deserializer<'de>,
{
    Ok(Option::<String>::deserialize(d)?.unwrap_or_default())
}

impl MachineInfo {
    /// A member with no host is a member we cannot reach YET — present in the registry,
    /// absent from peer traffic. Recorded rather than dropped, so the fleet size stays
    /// honest and the reason is visible.
    pub fn is_reachable(&self) -> bool {
        !self.gateway_host.is_empty() && self.gateway_port != 0
    }
}

/// Immutable registry of SAGE fleet members loaded from fleet.json.
#[derive(Clone)]
pub struct FleetRegistry {
    self_machine: String,
    machines: HashMap<String, MachineInfo>,
    version: u32,
}

impl FleetRegistry {
    pub fn load(self_machine: &str, manifest_path: &Path) -> Result<Self, String> {
        let data = std::fs::read_to_string(manifest_path)
            .map_err(|e| format!("failed to read fleet.json: {e}"))?;
        let manifest: FleetManifest = serde_json::from_str(&data)
            .map_err(|e| format!("failed to parse fleet.json: {e}"))?;

        Ok(Self {
            self_machine: self_machine.to_string(),
            machines: manifest.machines,
            version: manifest.fleet_version,
        })
    }

    pub fn version(&self) -> u32 {
        self.version
    }

    pub fn fleet_size(&self) -> usize {
        self.machines.len()
    }

    pub fn get_all(&self) -> &HashMap<String, MachineInfo> {
        &self.machines
    }

    pub fn get_peers(&self) -> HashMap<&str, &MachineInfo> {
        self.machines
            .iter()
            .filter(|(name, _)| name.as_str() != self.self_machine)
            .map(|(name, info)| (name.as_str(), info))
            .collect()
    }

    pub fn get_peer(&self, name: &str) -> Option<&MachineInfo> {
        self.machines.get(name)
    }

    pub fn get_self_info(&self) -> Option<&MachineInfo> {
        self.machines.get(&self.self_machine)
    }

    pub fn peer_names(&self) -> Vec<&str> {
        self.machines
            .keys()
            .filter(|n| n.as_str() != self.self_machine)
            .map(|n| n.as_str())
            .collect()
    }

    pub fn gateway_url(&self, machine_name: &str) -> Option<String> {
        // A member with no host is unreachable, and saying so is the point. Before this,
        // `pub` (host null) was advertised as "http://:8750" — a URL that resolves to
        // nothing and fails at connect time, one layer away from where the cause is
        // legible. None here means "in the registry, not yet reachable", which is the
        // truth about that member.
        let m = self.machines.get(machine_name)?;
        if !m.is_reachable() {
            return None;
        }
        Some(format!("http://{}:{}", m.gateway_host, m.gateway_port))
    }
}

#[cfg(test)]
mod tests {
    // Guard for the defect that cost the whole fleet its peers (Legion, 2026-09-07):
    // `pub` carries "gateway_host": null and serde refused the ENTIRE manifest on it, so
    // /peers returned [] on every daemon while the startup line still read
    // "federation=active". One incomplete member must not delete the other seven.
    use super::*;
    use std::path::PathBuf;

    fn fleet_path() -> PathBuf {
        // Repo-relative, not /home/sprout/... — the hardcoded pilot-seat path made every
        // test in this module return early (a silent skip, not a pass) on all seven other
        // machines, which is how a manifest that refuses to deserialize survived.
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../sage/federation/fleet.json")
    }

    #[test]
    fn load_real_fleet() {
        let path = fleet_path();
        if !path.exists() {
            return;
        }

        // The real manifest must LOAD — that is the assertion that matters, and the one
        // that was not being made: this test read /home/sprout/... , did not exist on any
        // other machine, and returned early as a silent skip. Meanwhile the manifest had
        // stopped deserializing entirely.
        let registry = FleetRegistry::load("sprout", &path)
            .expect("the real fleet.json must deserialize");

        // The fleet GROWS. Pinning a literal count made this fail the moment the test
        // started running for real (it said 6; the fleet is 8 since 2026-08-28). Assert
        // the invariants instead: self is present, peers are everyone else, known members
        // are there.
        assert!(registry.fleet_size() >= 6, "fleet shrank unexpectedly: {}", registry.fleet_size());
        assert_eq!(registry.get_peers().len(), registry.fleet_size() - 1,
                   "peers must be every machine except self");
        assert!(registry.get_peer("thor").is_some());
        assert!(registry.get_peer("legion").is_some());
        assert!(registry.get_self_info().is_some());
        // The port is whatever the manifest says, not a literal: the fleet moved from 8750
        // (Python gateway) to 8760 (sage-rs) after this test was written, and a pinned 8750
        // failed the moment the test stopped silently skipping.
        assert_ne!(registry.get_self_info().unwrap().gateway_port, 0);
    }

    #[test]
    fn gateway_url() {
        let path = fleet_path();
        if !path.exists() {
            return;
        }

        let registry = FleetRegistry::load("sprout", &path).unwrap();
        let url = registry.gateway_url("thor").unwrap();
        assert!(url.starts_with("http://"));
        let port = registry.get_peer("thor").unwrap().gateway_port;
        assert!(url.ends_with(&format!(":{port}")), "url {url} must carry the manifest port {port}");
    }

    #[test]
    fn peer_names_exclude_self() {
        let path = fleet_path();
        if !path.exists() {
            return;
        }

        let registry = FleetRegistry::load("sprout", &path).unwrap();
        let names = registry.peer_names();
        assert!(!names.contains(&"sprout"));
        assert!(names.contains(&"thor"));
    }
}

#[cfg(test)]
mod null_tolerance_tests {
    use super::*;

    const WITH_A_NULL_HOST: &str = r#"{
      "fleet_version": 3,
      "machines": {
        "legion": {"pool":"synthesis","lct_id":"legion_sage_lct","gateway_host":"10.0.0.1","gateway_port":8750},
        "pub":    {"pool":"infra","lct_id":"pub_sage_lct","gateway_host":null,"last_seen_ip":null,"gateway_port":8750}
      }
    }"#;

    #[test]
    fn one_incomplete_member_does_not_delete_the_others() {
        let dir = std::env::temp_dir().join(format!("fleet-null-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("fleet.json");
        std::fs::write(&path, WITH_A_NULL_HOST).unwrap();

        let reg = FleetRegistry::load("legion", &path)
            .expect("a null host must not refuse the whole manifest");
        assert_eq!(reg.fleet_size(), 2, "both members stay in the registry");

        // and the unreachable one reports as unreachable rather than as http://:8750
        assert_eq!(reg.gateway_url("pub"), None, "no host means not reachable, not a broken URL");
        assert_eq!(reg.gateway_url("legion").as_deref(), Some("http://10.0.0.1:8750"));

        let _ = std::fs::remove_dir_all(&dir);
    }
}
