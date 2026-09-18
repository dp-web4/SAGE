use std::collections::HashMap;

use tokio::sync::{mpsc, oneshot};
use tracing::{info, warn};

use sage_lib::consciousness::observation::SalienceScore;
use sage_lib::experience::buffer::{ExperienceBuffer, ExperienceEntry};
use sage_lib::metabolic::controller::{CycleData, MetabolicController};
use sage_lib::snarc::arousal::ArousalDetector;
use sage_lib::snarc::conflict::ConflictDetector;
use sage_lib::snarc::novelty::NoveltyDetector;
use sage_lib::snarc::reward::RewardEstimator;
use sage_lib::snarc::surprise::SurpriseDetector;

use crate::ollama::client::OllamaClient;

// --- Non-forcing shadow metabolism (experiment, dp 2026-07-19) ------------------
// The real ATP is driven ONLY by metabolic state (fixed per-state rates + circadian);
// nothing about the being's experience touches it. To learn how valence→metabolism
// WOULD behave before committing to wire it, we run a parallel "shadow" ATP that
// tracks the real base dynamics exactly but ALSO couples to cortex coherence — and is
// never fed back into behavior. Coherent noticings restore shadow ATP, incoherent ones
// drain it. We log both trajectories and study the divergence. Tunable; observation only.
const SHADOW_VALENCE_GAIN: f64 = 6.0;     // shadow ATP per unit (coherence - neutral), per noticing
const SHADOW_VALENCE_NEUTRAL: f64 = 0.5;  // coherence at which valence is metabolically neutral

pub struct PendingMessage {
    pub content: String,
    pub system: Option<String>,
    pub salience: Option<f64>,   // cortex-supplied real perceptual salience [0,1], if any
    pub coherence: Option<f64>,  // cortex-supplied cross-modal coherence [0,1] → the reward axis
    pub sender: String,
    /// `None` for an OBSERVATION: something the being felt but is not answering on this
    /// call. dp speaking in a conversation, the seat relaying, the cortex reporting a
    /// salient moment — all are felt the instant they arrive, while the reply (if any)
    /// comes on the being's own governed beat. Generation is what is optional here; being
    /// affected by what reached you is not.
    pub response_tx: Option<oneshot::Sender<Result<ConsciousnessResponse, String>>>,
}

pub struct ConsciousnessResponse {
    pub text: String,
    pub salience: SalienceScore,
    pub metabolic_state: String,
    pub atp_percentage: f64,
    pub cycle: u64,
}

/// What the loop knows about itself, published where the HTTP layer can read it.
///
/// WHY THIS EXISTS (SAGE #111). The loop owned its metabolic controller and its five SNARC
/// detectors; `AppState` built a SECOND set that nothing drove. `/status` read those, so it
/// answered `total_cycles: 0, atp_percentage: 100.0` while this loop was at cycle 1,593,000
/// with ATP 36.1% — same process, same second, two answers. Parallel state is not a display
/// bug: a healthy machine and a dead one rendered identically on every dashboard in the fleet.
///
/// The loop is the only writer. Readers get a clone; nobody else may mutate it.
#[derive(Clone, Debug, Default, serde::Serialize)]
pub struct LoopSnapshot {
    pub total_cycles: u64,
    pub messages_processed: u64,
    pub experiences_recorded: u64,
    pub state_transitions: u64,
    pub metabolic_state: String,
    pub atp_current: f64,
    pub atp_percentage: f64,
    /// The SNARC of the last message the being actually processed. `None` until one arrives —
    /// deliberately not zeros, because "nothing has happened yet" and "everything scored zero"
    /// are different facts and the dashboard showed both as 0.00 for months.
    pub salience: Option<sage_lib::consciousness::observation::SalienceScore>,
    /// Who the last felt input came from: "dp", the seat's name, "presence", a peer. Each
    /// source carries its own SNARC history, so this names which stream the published
    /// salience belongs to rather than implying one undifferentiated inbox.
    pub salience_source: Option<String>,
    /// Inputs felt without being answered — sensor moments and governed turns. Distinct
    /// from `messages_processed`, which counts generations.
    pub observations_felt: u64,
    /// Unix seconds when the loop last published. Staleness is the liveness signal: a loop
    /// that stopped leaves its last numbers behind, and only this field says so.
    pub published_at: u64,
}

pub struct LoopStats {
    pub total_cycles: u64,
    pub messages_processed: u64,
    pub observations_felt: u64,
    pub experiences_recorded: u64,
    pub state_transitions: u64,
}

pub struct ConsciousnessLoop {
    surprise: SurpriseDetector,
    novelty: NoveltyDetector,
    arousal: ArousalDetector,
    reward: RewardEstimator,
    conflict: ConflictDetector,
    metabolic: MetabolicController,
    ollama: OllamaClient,
    experience: ExperienceBuffer,
    message_rx: mpsc::Receiver<PendingMessage>,
    cycle: u64,
    stats: LoopStats,
    machine_name: String,
    model_name: String,
    // Non-forcing shadow metabolism — observation only, never fed back into behavior.
    shadow_atp: f64,
    shadow_atp_max: f64,
    shadow_log: Option<std::path::PathBuf>,
    /// Published state (SAGE #111). The loop writes; the HTTP layer reads a clone.
    snapshot: Option<std::sync::Arc<tokio::sync::Mutex<LoopSnapshot>>>,
    /// Distinct SNARC sensor ids seen so far, bounded by `MAX_SENSOR_IDS`. The detectors
    /// keep per-sensor predictors and memories for the life of the process, so an id taken
    /// from a request would otherwise be an unbounded map.
    sensor_ids: std::collections::HashSet<String>,
}

/// How many distinct sources may carry their own SNARC history before the rest share one.
/// Generous for the real population (dp, the seat, the cortex, the fleet's peers) and small
/// enough that the detector maps cannot be grown without limit by whoever reaches a route.
const MAX_SENSOR_IDS: usize = 24;

/// Normalise a speaker into a SNARC sensor id: lowercase, `[a-z0-9_-]`, bounded length.
/// Anything else collapses to `other`, which is a real stream too — it just does not get a
/// private habituation curve.
pub fn sensor_id(sender: &str) -> String {
    let cleaned: String = sender
        .trim()
        .to_lowercase()
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() || c == '-' || c == '_' { c } else { '-' })
        .collect::<String>()
        .trim_matches('-')
        .chars()
        .take(24)
        .collect();
    if cleaned.is_empty() { "other".to_string() } else { cleaned }
}

impl ConsciousnessLoop {
    pub fn new(
        ollama: OllamaClient,
        experience: ExperienceBuffer,
        message_rx: mpsc::Receiver<PendingMessage>,
        machine_name: &str,
        model_name: &str,
        shadow_log: Option<std::path::PathBuf>,
    ) -> Self {
        Self {
            surprise: SurpriseDetector::with_defaults(),
            novelty: NoveltyDetector::with_defaults(),
            arousal: ArousalDetector::with_defaults(),
            reward: RewardEstimator::with_defaults(),
            conflict: ConflictDetector::with_defaults(),
            metabolic: MetabolicController::with_defaults(),
            message_rx,
            ollama,
            experience,
            cycle: 0,
            stats: LoopStats {
                total_cycles: 0,
                messages_processed: 0,
                observations_felt: 0,
                experiences_recorded: 0,
                state_transitions: 0,
            },
            machine_name: machine_name.to_string(),
            model_name: model_name.to_string(),
            shadow_atp: 100.0,      // starts aligned with the real controller's initial ATP
            shadow_atp_max: 100.0,
            shadow_log,
            snapshot: None,
            sensor_ids: std::collections::HashSet::new(),
        }
    }

    /// Give the loop the cell it publishes into (SAGE #111). Called once at startup by the
    /// daemon, which hands the same Arc to the HTTP layer; without it the loop runs exactly
    /// as before and publishes nothing, so this stays optional for tests and `--simulate`.
    pub fn with_snapshot(mut self, cell: std::sync::Arc<tokio::sync::Mutex<LoopSnapshot>>) -> Self {
        self.snapshot = Some(cell);
        self
    }

    /// The loop's own reading of itself, for publishing.
    fn snapshot_now(&self, salience: Option<sage_lib::consciousness::observation::SalienceScore>,
                    salience_source: Option<String>) -> LoopSnapshot {
        LoopSnapshot {
            total_cycles: self.stats.total_cycles,
            messages_processed: self.stats.messages_processed,
            observations_felt: self.stats.observations_felt,
            experiences_recorded: self.stats.experiences_recorded,
            state_transitions: self.stats.state_transitions,
            metabolic_state: self.metabolic.current_state.as_str().to_string(),
            atp_current: self.metabolic.atp_current,
            atp_percentage: self.metabolic.atp_percentage(),
            salience,
            salience_source,
            published_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs())
                .unwrap_or(0),
        }
    }

    /// Publish, carrying forward the last salience unless this call supplies a newer one.
    /// Never blocks the loop: a contended lock skips this publish and the next one wins.
    async fn publish(&self, salience: Option<sage_lib::consciousness::observation::SalienceScore>,
                     source: Option<String>) {
        let Some(cell) = self.snapshot.as_ref() else { return };
        let Ok(mut cur) = cell.try_lock() else { return };
        let (carried, carried_src) = match salience {
            Some(s) => (Some(s), source),
            None => (cur.salience.clone(), cur.salience_source.clone()),
        };
        *cur = self.snapshot_now(carried, carried_src);
    }

    /// Advance the shadow ATP: apply the SAME base delta the real ATP just took, then add
    /// the valence coupling (only when cortex coherence was supplied). Returns valence_delta
    /// for logging. Purely observational — the shadow never influences state or the real ATP.
    fn shadow_step(&mut self, base_delta: f64, coherence: Option<f64>) -> f64 {
        self.shadow_atp += base_delta;
        let valence_delta = match coherence {
            Some(c) => SHADOW_VALENCE_GAIN * (c - SHADOW_VALENCE_NEUTRAL),
            None => 0.0,
        };
        self.shadow_atp += valence_delta;
        self.shadow_atp = self.shadow_atp.clamp(0.0, self.shadow_atp_max);
        valence_delta
    }

    /// Append one shadow-metabolism observation (real vs shadow ATP + the divergence).
    fn shadow_log_line(&self, event: &str, coherence: Option<f64>, valence_delta: f64) {
        let Some(ref path) = self.shadow_log else { return };
        let real_atp = self.metabolic.atp_current;
        let coh = match coherence {
            Some(c) => format!("{:.3}", c),
            None => "null".to_string(),
        };
        let line = format!(
            "{{\"cycle\":{},\"event\":\"{}\",\"real_atp\":{:.3},\"real_state\":\"{}\",\"coherence\":{},\"valence_delta\":{:.3},\"shadow_atp\":{:.3},\"divergence\":{:.3}}}",
            self.cycle, event, real_atp, self.metabolic.current_state.as_str(),
            coh, valence_delta, self.shadow_atp, self.shadow_atp - real_atp,
        );
        use std::io::Write;
        if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
            let _ = writeln!(f, "{}", line);
        }
    }

    pub async fn run(mut self, mut shutdown: tokio::sync::watch::Receiver<bool>) {
        info!("consciousness loop starting (machine={}, model={})", self.machine_name, self.model_name);

        loop {
            tokio::select! {
                _ = shutdown.changed() => {
                    if *shutdown.borrow() {
                        info!("consciousness loop: shutdown signal received");
                        break;
                    }
                }
                msg = self.message_rx.recv() => {
                    match msg {
                        Some(pending) => self.process_message(pending).await,
                        None => {
                            info!("consciousness loop: message channel closed");
                            break;
                        }
                    }
                }
                _ = tokio::time::sleep(std::time::Duration::from_millis(100)) => {
                    self.idle_tick();
                }
            }

            self.cycle += 1;
            self.stats.total_cycles = self.cycle;
            // Publish what this loop knows, every cycle. Ten writes a second of a small struct
            // behind a try_lock; a contended tick simply skips and the next one wins.
            self.publish(None, None).await;

            if self.cycle % 100 == 0 {
                info!(
                    "cycle={} state={} ATP={:.1} msgs={} felt={} exp={}",
                    self.cycle,
                    self.metabolic.current_state.as_str(),
                    self.metabolic.atp_current,
                    self.stats.messages_processed,
                    self.stats.observations_felt,
                    self.stats.experiences_recorded,
                );
            }
            // Shadow-metabolism baseline heartbeat (~every 60s) — samples the trajectory
            // shape between noticings so the divergence curve is legible offline.
            if self.cycle % 600 == 0 {
                self.shadow_log_line("heartbeat", None, 0.0);
            }
        }

        self.print_summary();
    }

    /// Score what arrived and let it move the being: SNARC, metabolism, the shadow, and the
    /// published snapshot. Shared by every input, answered or not.
    ///
    /// dp, 2026-09-17: *"video/audio and imu should trigger snarc, as should messages from me
    /// and you."* Before this split, SNARC lived inside the generation path, so the only input
    /// that could ever be felt was one the being immediately answered — which on a governed
    /// being is almost none of them. dp speaking in a conversation, the seat relaying, the
    /// cortex reporting a salient moment: all reached the record and none reached the being.
    ///
    /// The sensor id is the SOURCE, not the literal "message" it used to be. The detectors
    /// keep per-sensor predictors and habituation, so collapsing every stream into one id
    /// meant dp's first words in a week were measured against the cortex's 4 Hz chatter and
    /// scored as unremarkable. Each source now habituates on its own curve.
    async fn feel(&mut self, content: &str, supplied_salience: Option<f64>,
                  coherence: Option<f64>, sender: &str)
                  -> (SalienceScore, sage_lib::metabolic::controller::MetabolicState) {
        let obs = derive_observation(content);

        let id = sensor_id(sender);
        let id: &str = if self.sensor_ids.contains(&id) {
            self.sensor_ids.get(&id).map(|s| s.as_str()).unwrap_or("other")
        } else if self.sensor_ids.len() < MAX_SENSOR_IDS {
            self.sensor_ids.insert(id.clone());
            self.sensor_ids.get(&id).map(|s| s.as_str()).unwrap_or("other")
        } else {
            "other"
        };
        let id = id.to_string();

        let surprise = self.surprise.compute(obs, &id);
        let novelty = self.novelty.compute(obs, &id);
        let arousal = self.arousal.compute(obs, &id);
        let mut reward = self.reward.compute(obs, &id);
        // When the cortex supplied real cross-modal coherence, let it — not the word-count proxy —
        // BE the being's reward signal. Coherence-as-reward (H1): senses agreeing reads as "good,"
        // senses conflicting reads as "bad." Distinct from salience (attention intensity): this is
        // valence. Flows into conflict + the recorded experience, so incoherence is felt, not just seen.
        if let Some(c) = coherence {
            reward = c.clamp(0.0, 1.0);
        }

        let mut sensor_map = HashMap::new();
        sensor_map.insert("surprise".to_string(), surprise);
        sensor_map.insert("novelty".to_string(), novelty);
        sensor_map.insert("arousal".to_string(), arousal);
        sensor_map.insert("reward".to_string(), reward);
        let conflict = self.conflict.compute(&sensor_map, &id);

        let mut salience = SalienceScore::from_components(surprise, novelty, arousal, reward, conflict);
        // When the cortex supplied real perceptual salience, let it — not the word-count proxy —
        // drive the being's felt intensity (metabolic state + the experience-record gate).
        if let Some(s) = supplied_salience {
            salience.total = s.clamp(0.0, 1.0);
        }

        let prev_state = self.metabolic.current_state;
        let data = CycleData {
            max_salience: salience.total,
            crisis_detected: false,
            ..Default::default()
        };
        let atp_before = self.metabolic.atp_current;
        let new_state = self.metabolic.update(&data);
        if new_state != prev_state {
            self.stats.state_transitions += 1;
        }
        // Non-forcing shadow metabolism: observe how coherence-as-valence WOULD move ATP.
        // Uses the coherence the cortex supplied (same value now driving the reward axis).
        let base_delta = self.metabolic.atp_current - atp_before;
        let valence_delta = self.shadow_step(base_delta, coherence);
        self.shadow_log_line("noticing", coherence, valence_delta);

        // Publish what was just felt, before any generation (SAGE #111). The salience is real
        // whether or not a model answers, generation takes up to a minute on this hardware,
        // and a reader watching the being react should not wait on the reply to see it.
        self.publish(Some(salience.clone()), Some(id)).await;
        (salience, new_state)
    }

    async fn process_message(&mut self, pending: PendingMessage) {
        let PendingMessage { content, system: supplied_system, salience: supplied_salience,
                             coherence, sender, response_tx } = pending;

        // Felt first, always. Whether the being also ANSWERS here is a separate question.
        let (salience, new_state) =
            self.feel(&content, supplied_salience, coherence, &sender).await;

        let Some(response_tx) = response_tx else {
            // An observation: felt, not answered. dp's turn in a conversation, the seat
            // relaying, the cortex reporting — the being reacts now and replies on its beat.
            self.stats.observations_felt += 1;
            return;
        };

        let display_name = {
            let mut c = self.machine_name.chars();
            match c.next() {
                Some(first) => format!("{}{}", first.to_uppercase(), c.as_str()),
                None => "Sage".to_string(),
            }
        };
        let system_prompt = format!(
            "You are {}, a learning AI on {}. Metabolic state: {} (ATP: {:.0}%). Salience: {:.2}. Be concise.",
            display_name,
            self.machine_name,
            new_state.as_str(),
            self.metabolic.atp_percentage(),
            salience.total,
        );

        let system = supplied_system.unwrap_or(system_prompt);

        let result = self.ollama.generate(&content, Some(&system)).await;

        match result {
            Ok(text) => {
                let mut entry = ExperienceEntry::new(
                    content.clone(),
                    text.clone(),
                    salience.clone(),
                    new_state.as_str(),
                    self.metabolic.atp_percentage(),
                    self.cycle,
                );
                entry.machine = Some(self.machine_name.clone());
                entry.model = Some(self.model_name.clone());

                if self.experience.record(entry) {
                    self.stats.experiences_recorded += 1;
                }

                self.stats.messages_processed += 1;

                let response = ConsciousnessResponse {
                    text,
                    salience,
                    metabolic_state: new_state.as_str().to_string(),
                    atp_percentage: self.metabolic.atp_percentage(),
                    cycle: self.cycle,
                };
                let _ = response_tx.send(Ok(response));
            }
            Err(e) => {
                warn!("ollama error in consciousness loop: {}", e);
                let _ = response_tx.send(Err(e));
            }
        }
    }

    fn idle_tick(&mut self) {
        let data = CycleData {
            max_salience: 0.0,
            crisis_detected: false,
            ..Default::default()
        };
        let atp_before = self.metabolic.atp_current;
        self.metabolic.update(&data);
        // Shadow tracks the real base dynamics on idle too (no valence — no experience this tick).
        let base_delta = self.metabolic.atp_current - atp_before;
        self.shadow_step(base_delta, None);
    }

    fn print_summary(&self) {
        info!("=== Consciousness Loop Summary ===");
        info!("  total cycles: {}", self.stats.total_cycles);
        info!("  messages processed: {}", self.stats.messages_processed);
        info!("  experiences recorded: {}", self.stats.experiences_recorded);
        info!("  state transitions: {}", self.stats.state_transitions);
        info!("  final state: {} (ATP {:.1}%)", self.metabolic.current_state.as_str(), self.metabolic.atp_percentage());
        info!("  experience buffer: {} entries", self.experience.count());
    }
}

fn derive_observation(text: &str) -> f64 {
    let words = text.split_whitespace().count();
    let questions = text.chars().filter(|&c| c == '?').count();
    let exclamations = text.chars().filter(|&c| c == '!').count();
    let complexity = (words as f64).ln().max(1.0)
        + questions as f64 * 0.5
        + exclamations as f64 * 0.3;
    complexity
}

/// Shared handle that HTTP handlers use to submit messages to the loop.
#[derive(Clone)]
pub struct ConsciousnessHandle {
    tx: mpsc::Sender<PendingMessage>,
}

impl ConsciousnessHandle {
    pub fn new(tx: mpsc::Sender<PendingMessage>) -> Self {
        Self { tx }
    }

    pub async fn send_message(
        &self,
        content: String,
        system: Option<String>,
        salience: Option<f64>,
        coherence: Option<f64>,
        sender: &str,
    ) -> Result<ConsciousnessResponse, String> {
        let (response_tx, response_rx) = oneshot::channel();
        let msg = PendingMessage {
            content,
            system,
            salience,
            coherence,
            sender: sender.to_string(),
            response_tx: Some(response_tx),
        };
        self.tx.send(msg).await.map_err(|_| "consciousness loop not running".to_string())?;
        response_rx.await.map_err(|_| "consciousness loop dropped response".to_string())?
    }

    /// Let the being FEEL something without asking it to answer.
    ///
    /// This is the path for everything that reaches a governed being through its own proper
    /// channels: dp speaking in a conversation, the seat relaying, the cortex reporting a
    /// salient moment. The turn is recorded and answered on the being's beat; this makes
    /// sure the being is affected by it in the meantime instead of learning about its own
    /// week from a file.
    ///
    /// Non-blocking and lossy by design: if the loop's queue is full the observation is
    /// dropped rather than stalling whoever is speaking. A missed noticing is a missed
    /// noticing; a blocked conversation route would be a broken one.
    pub fn observe(&self, content: String, salience: Option<f64>, coherence: Option<f64>,
                   sender: &str) -> bool {
        let msg = PendingMessage {
            content,
            system: None,
            salience,
            coherence,
            sender: sender.to_string(),
            response_tx: None,
        };
        self.tx.try_send(msg).is_ok()
    }
}

#[cfg(test)]
mod snapshot_tests {
    use super::*;

    fn loop_with(cell: std::sync::Arc<tokio::sync::Mutex<LoopSnapshot>>) -> ConsciousnessLoop {
        let (_tx, rx) = mpsc::channel(4);
        ConsciousnessLoop::new(
            OllamaClient::default_local("test-model"),
            ExperienceBuffer::new(&std::path::PathBuf::from("/dev/null"), 0.5),
            rx,
            "testmachine",
            "test-model",
            None,
        )
        .with_snapshot(cell)
    }

    /// dp, 2026-09-17: *"video/audio and imu should trigger snarc, as should messages from me
    /// and you."* An observation is FELT without being answered: it moves SNARC and the
    /// metabolism and publishes, and it is not counted as a generation.
    #[tokio::test]
    async fn an_observation_is_felt_but_not_answered() {
        let cell = std::sync::Arc::new(tokio::sync::Mutex::new(LoopSnapshot::default()));
        let mut l = loop_with(cell.clone());

        let (salience, _state) = l.feel("dp asked a long and unexpected question about the museum",
                                        None, None, "dp").await;
        l.stats.observations_felt += 1;

        assert!(salience.total > 0.0, "something that arrived was felt");
        let snap = cell.lock().await.clone();
        assert!(snap.salience.is_some(), "and published");
        assert_eq!(snap.salience_source.as_deref(), Some("dp"), "under the name that caused it");
        assert_eq!(snap.messages_processed, 0, "feeling is not generating");
    }

    /// Each source habituates on its own curve. Collapsing every stream into the literal
    /// "message" meant dp's first words in a week were measured against the cortex's 4 Hz
    /// chatter, and scored as unremarkable.
    #[tokio::test]
    async fn each_source_carries_its_own_snarc_history() {
        let cell = std::sync::Arc::new(tokio::sync::Mutex::new(LoopSnapshot::default()));
        let mut l = loop_with(cell.clone());

        // The cortex reports at 4 Hz, and its own stream grows familiar with what it keeps
        // seeing — novelty is memory-based, so this is the axis that wears down.
        let same = "the scene is still; clear view";
        let first_cortex = l.feel(same, None, None, "cortex").await.0.novelty;
        for _ in 0..12 {
            l.feel(same, None, None, "cortex").await;
        }
        let worn = l.feel(same, None, None, "cortex").await.0.novelty;
        assert!(worn < first_cortex,
                "the cortex's own stream grows familiar: {first_cortex} -> {worn}");

        // The very same words arriving from dp are a stream that has heard nothing yet.
        let from_dp = l.feel(same, None, None, "dp").await.0.novelty;
        assert!(from_dp > worn,
                "dp's stream is not worn down by the cortex's: dp {from_dp} vs cortex {worn}");
        assert!((from_dp - first_cortex).abs() < 1e-9,
                "a fresh source starts fresh, whatever another source has been doing");
    }

    /// The detectors keep per-sensor state for the life of the process, so an id taken from a
    /// request must be normalised and bounded or it is an unbounded map.
    #[test]
    fn sensor_ids_are_normalised_and_bounded() {
        assert_eq!(sensor_id("dp"), "dp");
        assert_eq!(sensor_id("Sprout-Claude"), "sprout-claude");
        assert_eq!(sensor_id("  ../../etc/passwd  "), "etc-passwd");
        assert_eq!(sensor_id(""), "other");
        assert_eq!(sensor_id("!!!"), "other");
        assert_eq!(sensor_id(&"x".repeat(200)).len(), 24, "bounded length");
    }

    #[tokio::test]
    async fn beyond_the_cap_sources_share_one_stream_instead_of_growing_forever() {
        let cell = std::sync::Arc::new(tokio::sync::Mutex::new(LoopSnapshot::default()));
        let mut l = loop_with(cell.clone());
        for i in 0..(MAX_SENSOR_IDS + 50) {
            l.feel("hello there", None, None, &format!("caller{i}")).await;
        }
        assert_eq!(l.sensor_ids.len(), MAX_SENSOR_IDS, "the map cannot be grown without limit");
        let snap = cell.lock().await.clone();
        assert_eq!(snap.salience_source.as_deref(), Some("other"),
                   "and the overflow says so rather than pretending to be its own stream");
    }

    /// SAGE #111: `/status` read a controller nothing drove, so it answered 0 cycles / 100% ATP
    /// while the loop ran at 1.6M cycles / 36% ATP. What the loop publishes must BE the loop's.
    #[tokio::test]
    async fn publish_reports_the_loops_own_numbers_not_a_default_controller() {
        let cell = std::sync::Arc::new(tokio::sync::Mutex::new(LoopSnapshot::default()));
        let mut l = loop_with(cell.clone());

        assert_eq!(cell.lock().await.total_cycles, 0, "nothing published yet");
        assert_eq!(cell.lock().await.published_at, 0, "and it says so");

        l.cycle = 1_593_000;
        l.stats.total_cycles = l.cycle;
        l.stats.messages_processed = 12;
        l.publish(None, None).await;

        let s = cell.lock().await.clone();
        assert_eq!(s.total_cycles, 1_593_000);
        assert_eq!(s.messages_processed, 12);
        assert_eq!(s.metabolic_state, l.metabolic.current_state.as_str());
        assert!(s.published_at > 0, "a publish stamps its time; staleness is the liveness signal");
    }

    /// No salience is not zero salience — the distinction the dashboard could not draw.
    #[tokio::test]
    async fn salience_is_none_until_something_is_felt_then_carries_forward() {
        let cell = std::sync::Arc::new(tokio::sync::Mutex::new(LoopSnapshot::default()));
        let l = loop_with(cell.clone());

        l.publish(None, None).await;
        assert!(cell.lock().await.salience.is_none(), "nothing felt yet");

        let felt = sage_lib::consciousness::observation::SalienceScore::from_components(
            0.8, 0.6, 0.4, 0.2, 0.1,
        );
        l.publish(Some(felt.clone()), Some("test".to_string())).await;
        let got = cell.lock().await.salience.clone().expect("felt");
        assert!((got.surprise - 0.8).abs() < 1e-9 && (got.conflict - 0.1).abs() < 1e-9);

        // an idle tick afterwards must not erase what was felt
        l.publish(None, None).await;
        assert!(cell.lock().await.salience.is_some(), "an idle cycle is not a forgetting");
    }

    /// A loop with no cell runs exactly as before and publishes nothing.
    #[tokio::test]
    async fn publishing_is_optional() {
        let (_tx, rx) = mpsc::channel(4);
        let l = ConsciousnessLoop::new(
            OllamaClient::default_local("test-model"),
            ExperienceBuffer::new(&std::path::PathBuf::from("/dev/null"), 0.5),
            rx,
            "testmachine",
            "test-model",
            None,
        );
        l.publish(None, None).await; // must not panic
    }
}
