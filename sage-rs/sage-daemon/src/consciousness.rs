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
    pub response_tx: oneshot::Sender<Result<ConsciousnessResponse, String>>,
}

pub struct ConsciousnessResponse {
    pub text: String,
    pub salience: SalienceScore,
    pub metabolic_state: String,
    pub atp_percentage: f64,
    pub cycle: u64,
}

pub struct LoopStats {
    pub total_cycles: u64,
    pub messages_processed: u64,
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
                experiences_recorded: 0,
                state_transitions: 0,
            },
            machine_name: machine_name.to_string(),
            model_name: model_name.to_string(),
            shadow_atp: 100.0,      // starts aligned with the real controller's initial ATP
            shadow_atp_max: 100.0,
            shadow_log,
        }
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

            if self.cycle % 100 == 0 {
                info!(
                    "cycle={} state={} ATP={:.1} msgs={} exp={}",
                    self.cycle,
                    self.metabolic.current_state.as_str(),
                    self.metabolic.atp_current,
                    self.stats.messages_processed,
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

    async fn process_message(&mut self, pending: PendingMessage) {
        // Decision-side time: the salience, metabolic state, and record/drop
        // decision below are all about THIS moment. ExperienceEntry::new's own
        // timestamp is LLM-completion time, a full generation latency later.
        let received_ts = sage_lib::snarc::temporal::now_secs();
        let obs = derive_observation(&pending.content);

        let surprise = self.surprise.compute(obs, "message");
        let novelty = self.novelty.compute(obs, "message");
        let arousal = self.arousal.compute(obs, "message");
        let mut reward = self.reward.compute(obs, "message");
        // When the cortex supplied real cross-modal coherence, let it — not the word-count proxy —
        // BE the being's reward signal. Coherence-as-reward (H1): senses agreeing reads as "good,"
        // senses conflicting reads as "bad." Distinct from salience (attention intensity): this is
        // valence. Flows into conflict + the recorded experience, so incoherence is felt, not just seen.
        if let Some(c) = pending.coherence {
            reward = c.clamp(0.0, 1.0);
        }

        let mut sensor_map = HashMap::new();
        sensor_map.insert("surprise".to_string(), surprise);
        sensor_map.insert("novelty".to_string(), novelty);
        sensor_map.insert("arousal".to_string(), arousal);
        sensor_map.insert("reward".to_string(), reward);
        let conflict = self.conflict.compute(&sensor_map, "message");

        let mut salience = SalienceScore::from_components(surprise, novelty, arousal, reward, conflict);
        // When the cortex supplied real perceptual salience, let it — not the word-count proxy —
        // drive the being's felt intensity (metabolic state + the experience-record gate).
        if let Some(s) = pending.salience {
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
        let valence_delta = self.shadow_step(base_delta, pending.coherence);
        self.shadow_log_line("noticing", pending.coherence, valence_delta);

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

        let system = pending.system.unwrap_or(system_prompt);

        let result = self.ollama.generate(&pending.content, Some(&system)).await;

        match result {
            Ok(text) => {
                let mut entry = ExperienceEntry::new(
                    pending.content.clone(),
                    text.clone(),
                    salience.clone(),
                    new_state.as_str(),
                    self.metabolic.atp_percentage(),
                    self.cycle,
                );
                entry.machine = Some(self.machine_name.clone());
                entry.model = Some(self.model_name.clone());
                entry.received_ts = Some(received_ts);

                let outcome = self.experience.record(entry);
                if outcome.recorded() {
                    self.stats.experiences_recorded += 1;
                } else if let Some(reason) = outcome.reason() {
                    info!(
                        "experience dropped ({}), salience {:.3}",
                        reason, salience.total
                    );
                }

                self.stats.messages_processed += 1;

                let response = ConsciousnessResponse {
                    text,
                    salience,
                    metabolic_state: new_state.as_str().to_string(),
                    atp_percentage: self.metabolic.atp_percentage(),
                    cycle: self.cycle,
                };
                let _ = pending.response_tx.send(Ok(response));
            }
            Err(e) => {
                warn!("ollama error in consciousness loop: {}", e);
                let _ = pending.response_tx.send(Err(e));
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
            response_tx,
        };
        self.tx.send(msg).await.map_err(|_| "consciousness loop not running".to_string())?;
        response_rx.await.map_err(|_| "consciousness loop dropped response".to_string())?
    }
}
