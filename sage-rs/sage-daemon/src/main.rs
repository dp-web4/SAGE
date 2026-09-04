mod ollama;
mod consciousness;
mod federation;

use std::sync::Arc;
use std::time::Instant;

use axum::{
    extract::State,
    http::StatusCode,
    response::{Html, sse::{Event, Sse}},
    routing::{get, post},
    Json, Router,
};
use futures_util::stream::Stream;
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;
use tracing::{info, warn};

use sage_lib::experience::buffer::{ExperienceBuffer, DEFAULT_CAPTURE_THRESHOLD};
use sage_lib::federation::fleet::FleetRegistry;
use sage_lib::federation::peer_trust::PeerTrustTracker;
use sage_lib::metabolic::controller::{CycleData, MetabolicController, MetabolicState};
use sage_lib::snarc::arousal::ArousalDetector;
use sage_lib::snarc::conflict::ConflictDetector;
use sage_lib::snarc::novelty::NoveltyDetector;
use sage_lib::snarc::reward::RewardEstimator;
use sage_lib::snarc::surprise::SurpriseDetector;
use sage_lib::snarc::temporal;

use crate::consciousness::{ConsciousnessHandle, ConsciousnessLoop};
use crate::federation::client::PeerClient;
use crate::federation::monitor::PeerMonitor;
use crate::ollama::client::{ChatMessage, OllamaClient};

struct AppState {
    surprise: Mutex<SurpriseDetector>,
    novelty: Mutex<NoveltyDetector>,
    arousal: Mutex<ArousalDetector>,
    reward: Mutex<RewardEstimator>,
    conflict: Mutex<ConflictDetector>,
    metabolic: Mutex<MetabolicController>,
    consciousness: ConsciousnessHandle,
    ollama: OllamaClient,
    fleet: Option<FleetRegistry>,
    peer_client: Option<PeerClient>,
    peer_states: Option<Arc<Mutex<std::collections::HashMap<String, federation::monitor::PeerState>>>>,
    started: Instant,
    model: String,
    machine: String,
    chat_history_file: std::path::PathBuf,
    images_dir: std::path::PathBuf,
}

// --- Request/Response types ---

#[derive(Serialize)]
struct HealthResponse {
    status: &'static str,
    uptime_secs: f64,
    version: &'static str,
    port: u16,
    model: String,
    ollama_available: bool,
    consciousness_loop: bool,
}

#[derive(Serialize)]
struct StatusResponse {
    daemon: &'static str,
    sprint: &'static str,
    snarc_detectors: Vec<&'static str>,
    half_lives: Vec<(&'static str, f64)>,
    metabolic_state: &'static str,
    atp_percentage: f64,
    total_cycles: u64,
    model: String,
    fleet_size: usize,
    consciousness_loop: bool,
}

#[derive(Deserialize)]
struct SnarcRequest {
    observation: f64,
    sensor_id: Option<String>,
}

#[derive(Serialize)]
struct SnarcResponse {
    surprise: f64,
    novelty: f64,
    arousal: f64,
    reward: f64,
    sensor_id: String,
}

#[derive(Deserialize)]
struct MetabolicCycleRequest {
    max_salience: Option<f64>,
    crisis_detected: Option<bool>,
}

#[derive(Serialize)]
struct MetabolicResponse {
    state: &'static str,
    atp_current: f64,
    atp_percentage: f64,
    total_cycles: u64,
    transitions: usize,
}

#[derive(Deserialize)]
struct ChatRequest {
    message: String,
    #[serde(default)]
    system: Option<String>,
    #[serde(default)]
    conversation: Option<Vec<ChatMessage>>,
    // Cortex-supplied blended perceptual salience [0,1]. When present it drives the being's
    // metabolic response + experience gate instead of the word-count proxy derived from the text.
    #[serde(default)]
    salience: Option<f64>,
    // Cortex-supplied cross-modal coherence [0,1]. When present it becomes the being's reward
    // (valence) axis instead of the word-count proxy — coherence-as-reward (H1).
    #[serde(default)]
    coherence: Option<f64>,
}

#[derive(Serialize)]
struct ChatResponse {
    response: String,
    model: String,
    metabolic_state: String,
    atp_percentage: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    salience: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    cycle: Option<u64>,
}

#[derive(Deserialize)]
struct StreamRequest {
    message: String,
    #[serde(default)]
    system: Option<String>,
}

#[derive(Serialize)]
struct PeerInfo {
    name: String,
    gateway_url: String,
    pool: String,
    model: String,
    device: String,
    hardware: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    online: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    latency_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    metabolic_state: Option<String>,
}

#[derive(Serialize)]
struct PeersResponse {
    self_machine: String,
    peers: Vec<PeerInfo>,
    fleet_version: u32,
}

#[derive(Deserialize)]
struct DelegateRequest {
    target: String,
    message: String,
    #[serde(default)]
    conversation_id: Option<String>,
}

#[derive(Serialize)]
struct DelegateResponse {
    success: bool,
    target: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    response: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    metabolic_state: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    latency_ms: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

async fn dashboard() -> Html<&'static str> {
    Html(include_str!("dashboard.html"))
}

const PORT: u16 = 8760;

// Path + identity resolution (Sprint 7: per-machine via env vars).
//
// Defaults: SAGE_MACHINE=sprout (keeps Sprout's existing deploy working without
// env change). All other machines set SAGE_MACHINE + SAGE_MODEL in their
// systemd service environment. Per-path explicit overrides
// (SAGE_FLEET_JSON / SAGE_EXPERIENCE_PATH / SAGE_TRUST_PATH) win over the
// derived defaults if set.

fn sage_root() -> std::path::PathBuf {
    use std::path::PathBuf;
    if let Ok(p) = std::env::var("SAGE_ROOT") {
        return PathBuf::from(p);
    }
    if let Ok(exe) = std::env::current_exe() {
        // Built layout: <SAGE_ROOT>/sage-rs/target/release/sage-daemon
        // Walk up four parents to land at SAGE_ROOT.
        if let Some(root) = exe
            .parent()
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
            .and_then(|p| p.parent())
        {
            if root.join("sage/federation/fleet.json").exists() {
                return root.to_path_buf();
            }
        }
    }
    PathBuf::from(".")
}

fn instance_slug(machine: &str, model: &str) -> String {
    // sage/instances/{machine}-{model} convention; colons in model become dashes.
    format!("{}-{}", machine, model.replace(':', "-"))
}

fn fleet_json_path(root: &std::path::Path) -> std::path::PathBuf {
    if let Ok(p) = std::env::var("SAGE_FLEET_JSON") {
        return std::path::PathBuf::from(p);
    }
    root.join("sage/federation/fleet.json")
}

fn experience_path(root: &std::path::Path, machine: &str, model: &str) -> std::path::PathBuf {
    if let Ok(p) = std::env::var("SAGE_EXPERIENCE_PATH") {
        return std::path::PathBuf::from(p);
    }
    root.join(format!(
        "sage/instances/{}/experience_buffer_rs.jsonl",
        instance_slug(machine, model)
    ))
}

fn trust_path(root: &std::path::Path, machine: &str, model: &str) -> std::path::PathBuf {
    if let Ok(p) = std::env::var("SAGE_TRUST_PATH") {
        return std::path::PathBuf::from(p);
    }
    root.join(format!(
        "sage/instances/{}/peer_trust_rs.json",
        instance_slug(machine, model)
    ))
}

fn chat_history_path(root: &std::path::Path, machine: &str, model: &str) -> std::path::PathBuf {
    if let Ok(p) = std::env::var("SAGE_CHAT_HISTORY_PATH") {
        return std::path::PathBuf::from(p);
    }
    root.join(format!(
        "sage/instances/{}/chat_history.jsonl",
        instance_slug(machine, model)
    ))
}

// --- Handlers ---

async fn health(State(state): State<Arc<AppState>>) -> Json<HealthResponse> {
    let available = state.ollama.is_available().await;
    Json(HealthResponse {
        status: "ok",
        uptime_secs: state.started.elapsed().as_secs_f64(),
        version: env!("CARGO_PKG_VERSION"),
        port: PORT,
        model: state.model.clone(),
        ollama_available: available,
        consciousness_loop: true,
    })
}

async fn status(State(state): State<Arc<AppState>>) -> Json<StatusResponse> {
    let ctrl = state.metabolic.lock().await;
    Json(StatusResponse {
        daemon: "sage-daemon",
        sprint: "6 — dashboard + cutover",
        snarc_detectors: vec!["surprise", "novelty", "arousal", "reward", "conflict"],
        half_lives: temporal::DEFAULT_HALF_LIVES.to_vec(),
        metabolic_state: ctrl.current_state.as_str(),
        atp_percentage: ctrl.atp_percentage(),
        total_cycles: ctrl.total_cycles,
        model: state.model.clone(),
        fleet_size: state.fleet.as_ref().map_or(0, |f| f.fleet_size()),
        consciousness_loop: true,
    })
}

async fn snarc_observe(
    State(state): State<Arc<AppState>>,
    Json(req): Json<SnarcRequest>,
) -> Json<SnarcResponse> {
    let sensor_id = req.sensor_id.unwrap_or_else(|| "default".to_string());
    let obs = req.observation;

    let surprise = state.surprise.lock().await.compute(obs, &sensor_id);
    let novelty = state.novelty.lock().await.compute(obs, &sensor_id);
    let arousal = state.arousal.lock().await.compute(obs, &sensor_id);
    let reward = state.reward.lock().await.compute(obs, &sensor_id);

    Json(SnarcResponse { surprise, novelty, arousal, reward, sensor_id })
}

async fn metabolic_cycle(
    State(state): State<Arc<AppState>>,
    Json(req): Json<MetabolicCycleRequest>,
) -> Json<MetabolicResponse> {
    let data = CycleData {
        max_salience: req.max_salience.unwrap_or(0.0),
        crisis_detected: req.crisis_detected.unwrap_or(false),
        ..Default::default()
    };
    let mut ctrl = state.metabolic.lock().await;
    ctrl.update(&data);
    Json(MetabolicResponse {
        state: ctrl.current_state.as_str(),
        atp_current: ctrl.atp_current,
        atp_percentage: ctrl.atp_percentage(),
        total_cycles: ctrl.total_cycles,
        transitions: ctrl.history.len(),
    })
}

async fn chat(
    State(state): State<Arc<AppState>>,
    Json(req): Json<ChatRequest>,
) -> (StatusCode, Json<serde_json::Value>) {
    if let Some(conversation) = req.conversation {
        let mut messages = conversation;
        messages.push(ChatMessage {
            role: "user".to_string(),
            content: req.message,
        });
        match state.ollama.chat(&messages).await {
            Ok(text) => {
                let ctrl = state.metabolic.lock().await;
                (StatusCode::OK, Json(serde_json::json!({
                    "response": text,
                    "model": state.model,
                    "metabolic_state": ctrl.current_state.as_str(),
                    "atp_percentage": ctrl.atp_percentage(),
                })))
            }
            Err(e) => (StatusCode::BAD_GATEWAY, Json(serde_json::json!({
                "error": e,
            }))),
        }
    } else {
        match state.consciousness.send_message(req.message, req.system, req.salience, req.coherence, "http").await {
            Ok(resp) => (StatusCode::OK, Json(serde_json::json!({
                "response": resp.text,
                "model": state.model,
                "metabolic_state": resp.metabolic_state,
                "atp_percentage": resp.atp_percentage,
                "salience": resp.salience.total,
                "cycle": resp.cycle,
            }))),
            Err(e) => (StatusCode::BAD_GATEWAY, Json(serde_json::json!({
                "error": e,
            }))),
        }
    }
}

async fn stream_chat(
    State(state): State<Arc<AppState>>,
    Json(req): Json<StreamRequest>,
) -> Sse<impl Stream<Item = Result<Event, std::convert::Infallible>>> {
    let (tx, mut rx) = tokio::sync::mpsc::channel::<String>(64);

    let ollama = state.ollama.clone();
    let prompt = req.message;
    let system = req.system;

    tokio::spawn(async move {
        let _ = ollama.generate_stream(&prompt, system.as_deref(), tx).await;
    });

    let stream = async_stream::stream! {
        while let Some(token) = rx.recv().await {
            let data = serde_json::json!({ "token": token });
            yield Ok(Event::default().data(data.to_string()));
        }
        yield Ok(Event::default().data(r#"{"done":true}"#.to_string()));
    };

    Sse::new(stream)
}

async fn peers(State(state): State<Arc<AppState>>) -> Json<PeersResponse> {
    let (self_machine, peer_list, version) = match &state.fleet {
        Some(fleet) => {
            let live_states = match &state.peer_states {
                Some(ps) => Some(ps.lock().await),
                None => None,
            };

            let peers: Vec<PeerInfo> = fleet.get_peers()
                .into_iter()
                .map(|(name, info)| {
                    let (online, latency, metabolic) = live_states.as_ref()
                        .and_then(|s| s.get(name))
                        .map(|ps| (Some(ps.online), ps.latency_ms, ps.metabolic_state.clone()))
                        .unwrap_or((None, None, None));

                    PeerInfo {
                        name: name.to_string(),
                        gateway_url: format!("http://{}:{}", info.gateway_host, info.gateway_port),
                        pool: info.pool.clone(),
                        model: info.model_default.clone(),
                        device: info.device.clone(),
                        hardware: info.hardware.clone(),
                        online,
                        latency_ms: latency,
                        metabolic_state: metabolic,
                    }
                })
                .collect();
            (state.machine.clone(), peers, fleet.version())
        }
        None => (state.machine.clone(), vec![], 0),
    };

    Json(PeersResponse {
        self_machine,
        peers: peer_list,
        fleet_version: version,
    })
}

async fn delegate(
    State(state): State<Arc<AppState>>,
    Json(req): Json<DelegateRequest>,
) -> Result<Json<DelegateResponse>, (StatusCode, String)> {
    let client = state.peer_client.as_ref()
        .ok_or_else(|| (StatusCode::SERVICE_UNAVAILABLE, "federation not configured".to_string()))?;

    match client.send_message(&req.target, &req.message, req.conversation_id.as_deref()).await {
        Ok(result) => Ok(Json(DelegateResponse {
            success: true,
            target: req.target,
            response: Some(result.response),
            metabolic_state: result.metabolic_state,
            latency_ms: Some(result.latency_ms),
            error: None,
        })),
        Err(e) => Ok(Json(DelegateResponse {
            success: false,
            target: req.target,
            response: None,
            metabolic_state: None,
            latency_ms: None,
            error: Some(e),
        })),
    }
}

async fn serve_image(
    State(state): State<Arc<AppState>>,
    axum::extract::Path(filename): axum::extract::Path<String>,
) -> Result<(StatusCode, [(String, String); 1], Vec<u8>), StatusCode> {
    if filename.contains("..") || filename.contains('/') {
        return Err(StatusCode::BAD_REQUEST);
    }
    let path = state.images_dir.join(&filename);
    let bytes = std::fs::read(&path).map_err(|_| StatusCode::NOT_FOUND)?;
    let content_type = if filename.ends_with(".png") {
        "image/png"
    } else if filename.ends_with(".jpg") || filename.ends_with(".jpeg") {
        "image/jpeg"
    } else {
        "application/octet-stream"
    };
    Ok((
        StatusCode::OK,
        [("content-type".to_string(), content_type.to_string())],
        bytes,
    ))
}

async fn chat_history(
    State(state): State<Arc<AppState>>,
    axum::extract::Query(params): axum::extract::Query<std::collections::HashMap<String, String>>,
) -> Json<serde_json::Value> {
    let limit: usize = params.get("limit").and_then(|s| s.parse().ok()).unwrap_or(50);
    let path = &state.chat_history_file;

    let entries = match std::fs::read_to_string(path) {
        Ok(content) => {
            let lines: Vec<&str> = content.lines().collect();
            let start = lines.len().saturating_sub(limit);
            lines[start..]
                .iter()
                .filter_map(|line| serde_json::from_str::<serde_json::Value>(line).ok())
                .collect::<Vec<_>>()
        }
        Err(_) => vec![],
    };

    Json(serde_json::json!({
        "messages": entries,
        "total": entries.len(),
        "path": path.display().to_string(),
    }))
}

fn run_simulation(cycles: u64) {
    println!("sage-daemon --simulate {cycles}");
    println!("{:-<60}", "");

    let mut ctrl = MetabolicController::with_defaults();
    let mut surprise = SurpriseDetector::with_defaults();
    let mut state_counts = std::collections::HashMap::<MetabolicState, u32>::new();
    let start = Instant::now();

    for i in 0..cycles {
        let salience: f64 = if (i % 80) < 15 { 0.6 } else { 0.15 };
        let obs = if (i % 80) < 15 { 10.0 + (i as f64 * 0.1) } else { 1.0 };
        let s = surprise.compute(obs, "sim");

        let data = CycleData {
            max_salience: salience.max(s),
            ..Default::default()
        };
        let state = ctrl.update(&data);
        *state_counts.entry(state).or_insert(0) += 1;

        if i < 20 || i % (cycles / 10).max(1) == 0 {
            println!(
                "cycle {:>5}  state={:<7}  ATP={:5.1}  salience={:.2}  surprise={:.3}",
                i, state.as_str(), ctrl.atp_current, salience, s
            );
        }
    }

    let elapsed = start.elapsed();
    println!("{:-<60}", "");
    println!("{cycles} cycles in {:.3}s ({:.0} cycles/s)", elapsed.as_secs_f64(), cycles as f64 / elapsed.as_secs_f64());
    println!("transitions: {}", ctrl.history.len());
    println!("state distribution:");
    let mut sorted: Vec<_> = state_counts.iter().collect();
    sorted.sort_by_key(|(_, c)| std::cmp::Reverse(**c));
    for (state, count) in sorted {
        println!("  {:<10} {:>5} ({:.1}%)", state.as_str(), count, *count as f64 / cycles as f64 * 100.0);
    }
}

#[tokio::main]
async fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() >= 2 && args[1] == "--simulate" {
        let cycles = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(1000);
        run_simulation(cycles);
        return;
    }

    tracing_subscriber::fmt::init();

    let machine = std::env::var("SAGE_MACHINE").unwrap_or_else(|_| {
        info!("SAGE_MACHINE not set, defaulting to 'sprout' (backward-compat); set explicitly for other machines");
        "sprout".to_string()
    });
    let model = std::env::var("SAGE_MODEL").unwrap_or_else(|_| "qwen3.5:0.8b".to_string());

    let root = sage_root();
    let fleet_path = fleet_json_path(&root);
    let exp_path = experience_path(&root, &machine, &model);
    let tr_path = trust_path(&root, &machine, &model);
    let chat_path = chat_history_path(&root, &machine, &model);
    info!(
        "paths: root={} fleet={} exp={} trust={}",
        root.display(),
        fleet_path.display(),
        exp_path.display(),
        tr_path.display()
    );

    let fleet = FleetRegistry::load(&machine, &fleet_path).ok();
    if let Some(ref f) = fleet {
        info!("fleet loaded: {} machines, v{}", f.fleet_size(), f.version());
    } else {
        info!("fleet registry unavailable (file missing or unreadable): {}", fleet_path.display());
    }

    let (shutdown_tx, shutdown_rx) = tokio::sync::watch::channel(false);

    // Consciousness loop
    let (msg_tx, msg_rx) = tokio::sync::mpsc::channel(64);
    let consciousness_handle = ConsciousnessHandle::new(msg_tx);

    // Capture gate: the salience bar an admitted percept must clear to become
    // memory (band semantics documented at DEFAULT_CAPTURE_THRESHOLD, buffer.rs).
    // Whether to align it with presence's wake bar or keep the band is a raising
    // decision (dp) — env-tunable so choosing doesn't need a rebuild. This is
    // the knob dp is expected to reach for, so a bad value complains loudly
    // instead of silently running the default.
    let capture_gate = match std::env::var("SAGE_CAPTURE_THRESHOLD") {
        Ok(raw) => match raw.parse::<f64>() {
            Ok(v) if (0.0..=1.0).contains(&v) => v,
            Ok(v) => {
                warn!(
                    "SAGE_CAPTURE_THRESHOLD={} outside [0,1] — using default {}",
                    v, DEFAULT_CAPTURE_THRESHOLD
                );
                DEFAULT_CAPTURE_THRESHOLD
            }
            Err(_) => {
                warn!(
                    "SAGE_CAPTURE_THRESHOLD={:?} unparseable — using default {}",
                    raw, DEFAULT_CAPTURE_THRESHOLD
                );
                DEFAULT_CAPTURE_THRESHOLD
            }
        },
        Err(_) => DEFAULT_CAPTURE_THRESHOLD,
    };
    let experience = ExperienceBuffer::new(&exp_path, capture_gate);
    info!(
        "experience buffer: {} existing entries (capture gate {})",
        experience.count(),
        capture_gate
    );

    // Non-forcing shadow-metabolism experiment log (sibling of the experience buffer).
    let shadow_path = exp_path.with_file_name("atp_shadow.jsonl");
    info!("shadow metabolism log: {}", shadow_path.display());
    let consciousness_loop = ConsciousnessLoop::new(
        OllamaClient::default_local(&model),
        experience,
        msg_rx,
        &machine,
        &model,
        Some(shadow_path),
    );

    let loop_shutdown = shutdown_rx.clone();
    let loop_handle = tokio::spawn(async move {
        consciousness_loop.run(loop_shutdown).await;
    });

    // Federation: peer monitor + client
    let trust = Arc::new(Mutex::new(
        PeerTrustTracker::with_defaults(&tr_path)
    ));

    let (peer_client, peer_states) = if let Some(ref fleet) = fleet {
        let monitor = PeerMonitor::new(fleet.clone(), trust.clone(), 30);
        let peer_states = monitor.states();
        let client = PeerClient::new(fleet.clone(), trust.clone(), peer_states.clone(), &machine);

        let monitor_shutdown = shutdown_rx.clone();
        tokio::spawn(async move {
            monitor.run(monitor_shutdown).await;
        });

        info!("federation: peer monitor + client active");
        (Some(client), Some(peer_states))
    } else {
        (None, None)
    };

    let state = Arc::new(AppState {
        surprise: Mutex::new(SurpriseDetector::with_defaults()),
        novelty: Mutex::new(NoveltyDetector::with_defaults()),
        arousal: Mutex::new(ArousalDetector::with_defaults()),
        reward: Mutex::new(RewardEstimator::with_defaults()),
        conflict: Mutex::new(ConflictDetector::with_defaults()),
        metabolic: Mutex::new(MetabolicController::with_defaults()),
        consciousness: consciousness_handle,
        ollama: OllamaClient::default_local(&model),
        fleet,
        peer_client,
        peer_states,
        started: Instant::now(),
        model: model.clone(),
        machine: machine.clone(),
        chat_history_file: chat_path,
        images_dir: root.join("images"),
    });

    let app = Router::new()
        .route("/", get(dashboard))
        .route("/health", get(health))
        .route("/status", get(status))
        .route("/snarc/observe", post(snarc_observe))
        .route("/metabolic/cycle", post(metabolic_cycle))
        .route("/chat", post(chat))
        .route("/chat/history", get(chat_history))
        .route("/chat-history", get(chat_history))
        .route("/stream", post(stream_chat))
        .route("/peers", get(peers))
        .route("/delegate", post(delegate))
        .route("/images/:filename", get(serve_image))
        .with_state(state);

    let addr = format!("0.0.0.0:{PORT}");
    info!("sage-daemon listening on {addr} (model={model}, consciousness=active, federation=active)");
    println!("sage-daemon listening on {addr} (model={model}, consciousness=active, federation=active)");

    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();

    let server = axum::serve(listener, app)
        .with_graceful_shutdown(async move {
            let ctrl_c = tokio::signal::ctrl_c();
            let mut sigterm = tokio::signal::unix::signal(
                tokio::signal::unix::SignalKind::terminate()
            ).expect("failed to install SIGTERM handler");

            tokio::select! {
                _ = ctrl_c => info!("received Ctrl+C"),
                _ = sigterm.recv() => info!("received SIGTERM"),
            }

            info!("initiating graceful shutdown...");
            let _ = shutdown_tx.send(true);
        });

    server.await.unwrap();

    let _ = loop_handle.await;
    info!("sage-daemon shut down cleanly");
}
