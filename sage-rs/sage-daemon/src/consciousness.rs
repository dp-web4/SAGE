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

// --- What the ATP controller is now (SAGE #291) ---------------------------------------
// dp, 2026-09-30: "the state display is an indicator not a control", and "the snarc is
// likewise an indicator not a control." The `MetabolicController` below still ticks every
// 100 ms, but it is an INTERNAL number now. It is not what `/status` or the dashboard call
// the being's state; that is the activity indicator (`crate::activity`), which only reports
// of real activity set. Its ATP is a free-running oscillator whose "day" is 10 s. Nothing
// the being experiences moves it: SNARC salience no longer feeds `update`, so no score
// steers it, and nothing reads its state to decide anything. It keeps running because the
// shadow-metabolism experiment below is measured against it, and `atp_percentage` is still
// published (labelled internal) for the readers that parse it.
//
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
    pub tick: u64,
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
    /// Loop ticks: one per 100 ms idle timer or message (uptime x 10). Named `ticks` since
    /// SAGE #295: as `total_cycles` it was read as a count of something the being did. Beats are
    /// counted from the heartbeat's reports (`crate::activity::BeatsView`).
    pub ticks: u64,
    pub messages_processed: u64,
    pub experiences_recorded: u64,
    /// Transitions of the INTERNAL ATP controller, which is not the displayed state (#291).
    pub state_transitions: u64,
    // No `metabolic_state` here any more (SAGE #291). The displayed state is the activity
    // indicator, read by the HTTP layer directly from `crate::activity`; publishing a second
    // copy from the loop would be the parallel-state bug of #111 over again.
    /// The internal ATP number (see the note at the top of this file). Not an activity.
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
    /// 100 ms loop ticks (uptime x 10). Not beats, not cycles of anything the being did (#295).
    pub ticks: u64,
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
    /// 100 ms loop ticks (SAGE #295: was `cycle`).
    tick: u64,
    stats: LoopStats,
    machine_name: String,
    model_name: String,
    // Non-forcing shadow metabolism — observation only, never fed back into behavior.
    shadow_atp: f64,
    shadow_atp_max: f64,
    shadow_log: Option<std::path::PathBuf>,
    /// Published state (SAGE #111). The loop writes; the HTTP layer reads a clone.
    snapshot: Option<std::sync::Arc<tokio::sync::Mutex<LoopSnapshot>>>,
    /// The activity indicator (SAGE #291). The loop marks its own generations on it (wake
    /// while it generates); it never sets the indicator from the ATP controller.
    activity: Option<crate::activity::SharedActivity>,
    /// Distinct SNARC sensor ids seen so far, bounded by `MAX_SENSOR_IDS`. The detectors
    /// keep per-sensor predictors and memories for the life of the process, so an id taken
    /// from a request would otherwise be an unbounded map.
    sensor_ids: std::collections::HashSet<String>,
}

/// How many distinct sources may carry their own SNARC history before the rest share one.
/// Generous for the real population (dp, the seat, the cortex, the fleet's peers) and small
/// enough that the detector maps cannot be grown without limit by whoever reaches a route.
const MAX_SENSOR_IDS: usize = 24;

/// Rotate the shadow-metabolism log past this size; one prior generation is kept.
const SHADOW_LOG_MAX_BYTES: u64 = 4 * 1024 * 1024;

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
            tick: 0,
            stats: LoopStats {
                ticks: 0,
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
            activity: None,
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

    /// Give the loop the activity indicator the HTTP layer reads (SAGE #291), so its own
    /// generations show as wake. Optional like the snapshot: without it nothing is shown.
    pub fn with_activity(mut self, cell: crate::activity::SharedActivity) -> Self {
        self.activity = Some(cell);
        self
    }

    /// The displayed state right now: the indicator's, or "rest" when the loop has none.
    fn shown_state(&self) -> String {
        match self.activity.as_ref() {
            Some(c) => crate::activity::read(c, crate::activity::now_secs()).state.to_string(),
            None => crate::activity::Activity::Rest.as_str().to_string(),
        }
    }

    /// The loop's own reading of itself, for publishing.
    fn snapshot_now(&self, salience: Option<sage_lib::consciousness::observation::SalienceScore>,
                    salience_source: Option<String>) -> LoopSnapshot {
        LoopSnapshot {
            ticks: self.stats.ticks,
            messages_processed: self.stats.messages_processed,
            observations_felt: self.stats.observations_felt,
            experiences_recorded: self.stats.experiences_recorded,
            state_transitions: self.stats.state_transitions,
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
        // `real_state` is the internal controller's state, kept under its old key so the
        // experiment's existing rows and readers stay comparable. It is not the being's
        // displayed state (SAGE #291). Likewise the `cycle` key: it is the loop tick (#295), kept
        // under its old name so the shadow log's rows stay comparable across the rename.
        let line = format!(
            "{{\"cycle\":{},\"event\":\"{}\",\"real_atp\":{:.3},\"real_state\":\"{}\",\"coherence\":{},\"valence_delta\":{:.3},\"shadow_atp\":{:.3},\"divergence\":{:.3}}}",
            self.tick, event, real_atp, self.metabolic.current_state.as_str(),
            coh, valence_delta, self.shadow_atp, self.shadow_atp - real_atp,
        );
        use std::io::Write;
        // Bounded. This log is an INSTRUMENT (observation only, never read back by the loop or
        // by anything in the Python tree) and it grew one row per noticing — 92k rows / 14 MB in
        // five days on Sprout, 1 GB/year, in every being's home, and over private-context's
        // 9 MB mirror guard on the first run (2026-09-22). One rotation keeps the recent
        // trajectory legible offline, which is all it was ever for.
        if let Ok(md) = std::fs::metadata(path) {
            if md.len() > SHADOW_LOG_MAX_BYTES {
                let _ = std::fs::rename(path, path.with_extension("jsonl.1"));
            }
        }
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

            self.tick += 1;
            self.stats.ticks = self.tick;
            // Publish what this loop knows, every cycle. Ten writes a second of a small struct
            // behind a try_lock; a contended tick simply skips and the next one wins.
            self.publish(None, None).await;

            if self.tick % 100 == 0 {
                info!(
                    "tick={} internal_state={} internal_ATP={:.1} msgs={} felt={} exp={}",
                    self.tick,
                    self.metabolic.current_state.as_str(),
                    self.metabolic.atp_current,
                    self.stats.messages_processed,
                    self.stats.observations_felt,
                    self.stats.experiences_recorded,
                );
            }
            // Shadow-metabolism baseline heartbeat (~every 60s) — samples the trajectory
            // shape between noticings so the divergence curve is legible offline.
            if self.tick % 600 == 0 {
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
    ///
    /// SNARC IS AN INDICATOR, NOT A CONTROL (dp, 2026-09-30; SAGE #291). What is felt is
    /// scored, published and recorded. It no longer moves the metabolic controller: salience
    /// above 0.45 used to flip it to `focus` and change its ATP rates. It no longer decides
    /// what is remembered either (see `ExperienceBuffer::record`).
    async fn feel(&mut self, content: &str, supplied_salience: Option<f64>,
                  coherence: Option<f64>, sender: &str) -> SalienceScore {
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

        // No controller update here (SAGE #291): the salience used to be fed in as
        // `max_salience`, which let SNARC steer the state and the ATP rates. The real ATP now
        // moves only on the idle tick, so its base delta for this noticing is zero.
        // Non-forcing shadow metabolism: observe how coherence-as-valence WOULD move ATP.
        // Uses the coherence the cortex supplied (same value now driving the reward axis).
        let valence_delta = self.shadow_step(0.0, coherence);
        self.shadow_log_line("noticing", coherence, valence_delta);

        // Publish what was just felt, before any generation (SAGE #111). The salience is real
        // whether or not a model answers, generation takes up to a minute on this hardware,
        // and a reader watching the being react should not wait on the reply to see it.
        self.publish(Some(salience.clone()), Some(id)).await;
        salience
    }

    async fn process_message(&mut self, pending: PendingMessage) {
        let PendingMessage { content, system: supplied_system, salience: supplied_salience,
                             coherence, sender, response_tx } = pending;

        // Felt first, always. Whether the being also ANSWERS here is a separate question.
        let salience = self.feel(&content, supplied_salience, coherence, &sender).await;

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
        // The being is acting from here until the reply is back: wake, shown for exactly as
        // long as the generation lasts (SAGE #291). The guard ends it on every path out.
        let generating = crate::activity::GenerationGuard::begin(
            self.activity.as_ref(), crate::activity::now_secs());
        let shown = self.shown_state();

        // The state named here is the one the display shows while this reply is generated.
        // The internal ATP is no longer quoted to the model: it is a free-running number, not
        // the being's energy (SAGE #291).
        let system_prompt = format!(
            "You are {}, a learning AI on {}. Metabolic state: {}. Salience: {:.2}. Be concise.",
            display_name,
            self.machine_name,
            shown,
            salience.total,
        );

        let system = supplied_system.unwrap_or(system_prompt);

        let result = self.ollama.generate(&content, Some(&system)).await;
        drop(generating);

        match result {
            Ok(text) => {
                let mut entry = ExperienceEntry::new(
                    content.clone(),
                    text.clone(),
                    salience.clone(),
                    &shown,
                    self.metabolic.atp_percentage(),
                    self.tick,
                );
                entry.machine = Some(self.machine_name.clone());
                entry.model = Some(self.model_name.clone());
                // The beat this exchange happened in, when one is running (SAGE #295).
                entry.beat_id = self.activity.as_ref().and_then(|c| {
                    crate::activity::read_beats(c, crate::activity::now_secs()).current.map(|b| b.beat_id)
                });

                if self.experience.record(entry) {
                    self.stats.experiences_recorded += 1;
                }

                self.stats.messages_processed += 1;

                let response = ConsciousnessResponse {
                    text,
                    salience,
                    metabolic_state: shown.clone(),
                    atp_percentage: self.metabolic.atp_percentage(),
                    tick: self.tick,
                };
                let _ = response_tx.send(Ok(response));
            }
            Err(e) => {
                warn!("ollama error in consciousness loop: {}", e);
                let _ = response_tx.send(Err(e));
            }
        }
    }

    /// Advance the INTERNAL ATP controller one 100 ms cycle. This never touches what is
    /// displayed (SAGE #291): the controller's state is its own, and the activity indicator
    /// is set only by reports of real activity. `crisis_detected` is always false: nothing
    /// real reports a crisis to this tick, and the fake ATP must not manufacture one.
    fn idle_tick(&mut self) {
        let data = CycleData {
            max_salience: 0.0,
            crisis_detected: false,
            ..Default::default()
        };
        let prev_state = self.metabolic.current_state;
        let atp_before = self.metabolic.atp_current;
        self.metabolic.update(&data);
        if self.metabolic.current_state != prev_state {
            self.stats.state_transitions += 1;
        }
        // Shadow tracks the real base dynamics on idle too (no valence — no experience this tick).
        let base_delta = self.metabolic.atp_current - atp_before;
        self.shadow_step(base_delta, None);
    }

    fn print_summary(&self) {
        info!("=== Consciousness Loop Summary ===");
        info!("  loop ticks: {}", self.stats.ticks);
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
            ExperienceBuffer::new(&std::path::PathBuf::from("/dev/null")),
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

        let salience = l.feel("dp asked a long and unexpected question about the museum",
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
        let first_cortex = l.feel(same, None, None, "cortex").await.novelty;
        for _ in 0..12 {
            l.feel(same, None, None, "cortex").await;
        }
        let worn = l.feel(same, None, None, "cortex").await.novelty;
        assert!(worn < first_cortex,
                "the cortex's own stream grows familiar: {first_cortex} -> {worn}");

        // The very same words arriving from dp are a stream that has heard nothing yet.
        let from_dp = l.feel(same, None, None, "dp").await.novelty;
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

        assert_eq!(cell.lock().await.ticks, 0, "nothing published yet");
        assert_eq!(cell.lock().await.published_at, 0, "and it says so");

        l.tick = 1_593_000;
        l.stats.ticks = l.tick;
        l.stats.messages_processed = 12;
        l.publish(None, None).await;

        let s = cell.lock().await.clone();
        assert_eq!(s.ticks, 1_593_000);
        assert_eq!(s.messages_processed, 12);
        assert!((s.atp_current - l.metabolic.atp_current).abs() < 1e-12, "the loop's own ATP");
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

    /// SAGE #291. THE REGRESSION TEST FOR THE FREE-RUNNING DISPLAY. The idle tick still drives
    /// the internal ATP oscillator (it must, for the shadow experiment), and the oscillator
    /// still transitions. What is SHOWN must not move with it. 20,000 ticks is 33 simulated
    /// minutes and 200 of the controller's 10-second "days". If idle_tick ever writes the
    /// indicator again, or the display is re-pointed at the controller, this fails.
    #[tokio::test]
    async fn the_idle_tick_never_changes_what_is_shown() {
        let cell = std::sync::Arc::new(tokio::sync::Mutex::new(LoopSnapshot::default()));
        let act: crate::activity::SharedActivity = std::sync::Arc::new(std::sync::Mutex::new(
            crate::activity::ActivityIndicator::new(crate::activity::now_secs())));
        let mut l = loop_with(cell.clone()).with_activity(act.clone());

        let mut controller_states = std::collections::HashSet::new();
        for _ in 0..20_000 {
            l.idle_tick();
            controller_states.insert(l.metabolic.current_state.as_str());
            assert_eq!(l.shown_state(), "rest", "an idle tick moved the display");
        }
        assert!(controller_states.len() >= 3,
                "the internal oscillator still runs (the test would be vacuous otherwise): {controller_states:?}");
        assert!(l.stats.state_transitions > 100, "and it transitioned {} times", l.stats.state_transitions);

        // A report moves it, and the ticks that follow do not move it back.
        act.lock().unwrap().report(crate::activity::Activity::WrapUp, "heartbeat:reflect", None, None,
                                   crate::activity::now_secs());
        for _ in 0..2_000 {
            l.idle_tick();
            assert_eq!(l.shown_state(), "wrap-up");
        }
    }

    /// SAGE #291: SNARC is an indicator, not a control. Feeling something, however salient,
    /// is scored and published and leaves the controller where it was. Salience above 0.45
    /// used to flip it to `focus`.
    #[tokio::test]
    async fn salience_steers_nothing() {
        let cell = std::sync::Arc::new(tokio::sync::Mutex::new(LoopSnapshot::default()));
        let mut l = loop_with(cell.clone());
        let (state0, atp0, cycles0) = (l.metabolic.current_state, l.metabolic.atp_current, l.metabolic.total_cycles);
        for i in 0..50 {
            let s = l.feel(&format!("an urgent, surprising thing number {i}!"), Some(0.99), Some(0.9), "cortex").await;
            assert!((s.total - 0.99).abs() < 1e-9, "the score is still computed and carried");
        }
        assert_eq!(l.metabolic.current_state, state0, "no salience moved the state");
        assert_eq!(l.metabolic.atp_current, atp0, "or the ATP");
        assert_eq!(l.metabolic.total_cycles, cycles0, "feeling is not a controller cycle");
        assert!(cell.lock().await.salience.is_some(), "and it was published");
    }

    /// SAGE #291: the loop's own generation (a `/chat/raw` reply) IS the being acting, so the
    /// display shows wake for exactly as long as it lasts and then returns to rest. The
    /// exchange is recorded whatever its salience, with the state it was generated in.
    /// Against a fake Ollama on an ephemeral port: this test must never reach the live one.
    #[tokio::test]
    async fn a_generation_shows_wake_while_it_runs_and_is_recorded_whatever_its_salience() {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let (release_tx, release_rx) = oneshot::channel::<()>();
        let server = tokio::spawn(async move {
            let (mut sock, _) = listener.accept().await.unwrap();
            let mut buf = vec![0u8; 65536];
            let _ = sock.read(&mut buf).await;
            let _ = release_rx.await;   // hold the "generation" open until the test has looked
            let body = r#"{"response":"a quiet reply"}"#;
            let resp = format!("HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{}",
                               body.len(), body);
            let _ = sock.write_all(resp.as_bytes()).await;
        });

        let dir = tempfile::tempdir().unwrap();
        let exp = dir.path().join("experience_buffer_rs.jsonl");
        let act: crate::activity::SharedActivity = std::sync::Arc::new(std::sync::Mutex::new(
            crate::activity::ActivityIndicator::new(crate::activity::now_secs())));
        let (_tx, rx) = mpsc::channel(4);
        let mut l = ConsciousnessLoop::new(
            OllamaClient::new(&format!("http://{addr}"), "test-model"),
            ExperienceBuffer::new(&exp), rx, "testmachine", "test-model", None,
        ).with_activity(act.clone());

        let (resp_tx, resp_rx) = oneshot::channel();
        let run = tokio::spawn(async move {
            l.process_message(PendingMessage {
                content: "ok".to_string(), system: None, salience: Some(0.05), coherence: None,
                sender: "presence".to_string(), response_tx: Some(resp_tx),
            }).await;
            l
        });

        let mut saw_wake = false;
        for _ in 0..200 {
            if crate::activity::read(&act, crate::activity::now_secs()).state == "wake" { saw_wake = true; break; }
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        }
        assert!(saw_wake, "the display showed wake while the being generated");
        assert_eq!(crate::activity::read(&act, crate::activity::now_secs()).source, "daemon:generate");
        release_tx.send(()).unwrap();

        let resp = tokio::time::timeout(std::time::Duration::from_secs(10), resp_rx).await
            .expect("bounded").expect("answered").expect("generated");
        let l = run.await.unwrap();
        server.await.unwrap();
        assert_eq!(resp.text, "a quiet reply");
        assert_eq!(resp.metabolic_state, "wake", "the reply names the state it was generated in");
        assert_eq!(crate::activity::read(&act, crate::activity::now_secs()).state, "rest", "and it ends");

        assert_eq!(l.stats.experiences_recorded, 1, "salience 0.05 is still remembered");
        let rec = std::fs::read_to_string(&exp).unwrap();
        assert!(rec.contains(r#""metabolic_state":"wake""#), "{rec}");
        assert!(rec.contains(r#""total":0.05"#), "with its score as an annotation: {rec}");
    }

    /// A loop with no cell runs exactly as before and publishes nothing.
    #[tokio::test]
    async fn publishing_is_optional() {
        let (_tx, rx) = mpsc::channel(4);
        let l = ConsciousnessLoop::new(
            OllamaClient::default_local("test-model"),
            ExperienceBuffer::new(&std::path::PathBuf::from("/dev/null")),
            rx,
            "testmachine",
            "test-model",
            None,
        );
        l.publish(None, None).await; // must not panic
    }
}
