use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;

use reqwest::Client;
use serde::Deserialize;
use tokio::sync::{watch, Mutex};
use tracing::{info, warn};

use sage_lib::federation::fleet::FleetRegistry;
use sage_lib::federation::peer_trust::PeerTrustTracker;

#[derive(Debug, Clone)]
pub struct PeerState {
    pub online: bool,
    pub last_seen: f64,
    pub last_checked: f64,
    pub metabolic_state: Option<String>,
    pub atp_level: Option<f64>,
    /// A peer's loop ticks, from daemons older than SAGE #295. Newer daemons leave it empty.
    pub cycle_count: Option<u64>,
    /// Beats the peer completed since its daemon started (SAGE #295).
    pub beats_completed: Option<u64>,
    pub latency_ms: Option<f64>,
    pub hardware: String,
    pub error: Option<String>,
}

#[derive(Deserialize)]
struct HealthResponse {
    #[serde(default)]
    status: String,
    #[serde(default)]
    metabolic_state: Option<String>,
    #[serde(default)]
    atp_level: Option<f64>,
    #[serde(default)]
    atp_remaining: Option<f64>,
    #[serde(default)]
    cycle_count: Option<u64>,
    #[serde(default)]
    beats_completed: Option<u64>,
}

pub struct PeerMonitor {
    fleet: FleetRegistry,
    trust: Arc<Mutex<PeerTrustTracker>>,
    states: Arc<Mutex<HashMap<String, PeerState>>>,
    client: Client,
    poll_interval_secs: u64,
}

impl PeerMonitor {
    pub fn new(
        fleet: FleetRegistry,
        trust: Arc<Mutex<PeerTrustTracker>>,
        poll_interval_secs: u64,
    ) -> Self {
        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(2))
            .build()
            .unwrap();

        let mut initial_states = HashMap::new();
        for (name, info) in fleet.get_peers() {
            initial_states.insert(name.to_string(), PeerState {
                online: false,
                last_seen: 0.0,
                last_checked: 0.0,
                metabolic_state: None,
                atp_level: None,
                cycle_count: None,
                beats_completed: None,
                latency_ms: None,
                hardware: info.hardware.clone(),
                error: None,
            });
        }

        Self {
            fleet,
            trust,
            states: Arc::new(Mutex::new(initial_states)),
            client,
            poll_interval_secs,
        }
    }

    pub fn states(&self) -> Arc<Mutex<HashMap<String, PeerState>>> {
        self.states.clone()
    }

    pub async fn run(self, mut shutdown: watch::Receiver<bool>) {
        info!("peer monitor starting (interval={}s, peers={})", self.poll_interval_secs, self.fleet.peer_names().len());

        loop {
            self.poll_all().await;

            tokio::select! {
                _ = shutdown.changed() => {
                    if *shutdown.borrow() {
                        info!("peer monitor: shutdown signal received");
                        break;
                    }
                }
                _ = tokio::time::sleep(std::time::Duration::from_secs(self.poll_interval_secs)) => {}
            }
        }
    }

    async fn poll_all(&self) {
        let peers: Vec<(String, String)> = self.fleet.get_peers()
            .into_iter()
            .map(|(name, info)| {
                let url = format!("http://{}:{}/health", info.gateway_host, info.gateway_port);
                (name.to_string(), url)
            })
            .collect();

        let now = sage_lib::snarc::temporal::now_secs();
        let mut online_count = 0;

        for (name, url) in &peers {
            let start = Instant::now();
            let result = self.client.get(url).send().await;
            let latency = start.elapsed().as_secs_f64() * 1000.0;

            let mut states = self.states.lock().await;
            let state = states.entry(name.clone()).or_insert_with(|| PeerState {
                online: false,
                last_seen: 0.0,
                last_checked: 0.0,
                metabolic_state: None,
                atp_level: None,
                cycle_count: None,
                beats_completed: None,
                latency_ms: None,
                hardware: String::new(),
                error: None,
            });

            state.last_checked = now;

            match result {
                Ok(resp) if resp.status().is_success() => {
                    if let Ok(health) = resp.json::<HealthResponse>().await {
                        state.online = true;
                        state.last_seen = now;
                        state.metabolic_state = health.metabolic_state;
                        state.atp_level = health.atp_level.or(health.atp_remaining);
                        state.cycle_count = health.cycle_count;
                        state.beats_completed = health.beats_completed;
                        state.latency_ms = Some(latency);
                        state.error = None;
                        online_count += 1;
                    }
                    let mut trust = self.trust.lock().await;
                    trust.record_interaction(name, "success");
                }
                Ok(resp) => {
                    state.online = false;
                    let err = format!("HTTP {}", resp.status());
                    state.error = Some(err);
                    let mut trust = self.trust.lock().await;
                    trust.record_interaction(name, "error");
                }
                Err(e) => {
                    state.online = false;
                    let err = format!("{}", e);
                    state.error = Some(if err.len() > 200 { err[..200].to_string() } else { err });
                    let mut trust = self.trust.lock().await;
                    trust.record_interaction(name, "timeout");
                }
            }
        }

        info!("peer poll: {}/{} online", online_count, peers.len());
    }
}
