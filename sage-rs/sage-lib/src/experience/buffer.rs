use serde::{Deserialize, Serialize};
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use crate::consciousness::observation::SalienceScore;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExperienceEntry {
    pub id: String,
    pub prompt: String,
    pub response: String,
    pub salience: SalienceScore,
    pub metabolic_state: String,
    pub atp_percentage: f64,
    pub cycle: u64,
    pub timestamp: f64,
    /// When the daemon began deciding on this percept — set before LLM
    /// generation. `timestamp` is completion time and trails this by the full
    /// generation latency, so decision-side joins must not use it.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub received_ts: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub machine: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
}

impl ExperienceEntry {
    fn compute_id(prompt: &str, response: &str) -> String {
        use sha2::{Sha256, Digest};
        let mut hasher = Sha256::new();
        hasher.update(format!("{}|{}", prompt, response));
        let hash = hasher.finalize();
        hex::encode(&hash[..8])
    }

    pub fn new(
        prompt: String,
        response: String,
        salience: SalienceScore,
        metabolic_state: &str,
        atp_percentage: f64,
        cycle: u64,
    ) -> Self {
        let id = Self::compute_id(&prompt, &response);
        let timestamp = crate::snarc::temporal::now_secs();
        Self {
            id,
            prompt,
            response,
            salience,
            metabolic_state: metabolic_state.to_string(),
            atp_percentage,
            cycle,
            timestamp,
            received_ts: None,
            machine: None,
            model: None,
        }
    }

    /// Decision-time ts, falling back to completion time for entries that
    /// never set `received_ts`.
    pub fn decided_ts(&self) -> f64 {
        self.received_ts.unwrap_or(self.timestamp)
    }
}

/// Default capture gate — the salience bar an admitted percept must clear to
/// become memory. It sits ABOVE presence's wake bar (WAKE_TH = 0.45,
/// sage/embodiment/presence.py), so a 0.45..0.50 band wakes the being without
/// leaving an experience; align-or-keep is a raising decision, not a code
/// default. One definition, referenced by both the daemon's env fallback
/// (main.rs) and `with_defaults`, so the tests' gate and the daemon's cannot
/// drift apart silently.
pub const DEFAULT_CAPTURE_THRESHOLD: f64 = 0.5;

/// Why `record()` accepted or refused an entry. A refusal is stamped to a
/// sibling drops file so the panel can attribute drops to the capture gate,
/// the repetition filter, or an io failure instead of conflating the three.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RecordOutcome {
    Recorded,
    DroppedSalience,
    DroppedRepetition,
    DroppedIo,
}

impl RecordOutcome {
    pub fn recorded(self) -> bool {
        matches!(self, RecordOutcome::Recorded)
    }

    pub fn reason(self) -> Option<&'static str> {
        match self {
            RecordOutcome::Recorded => None,
            RecordOutcome::DroppedSalience => Some("salience"),
            RecordOutcome::DroppedRepetition => Some("repetition"),
            RecordOutcome::DroppedIo => Some("io"),
        }
    }
}

pub struct ExperienceBuffer {
    path: PathBuf,
    salience_threshold: f64,
    recent_responses: Vec<String>,
    repetition_window: usize,
    count: u64,
}

impl ExperienceBuffer {
    pub fn new(path: &Path, salience_threshold: f64) -> Self {
        let count = Self::count_lines(path);
        Self {
            path: path.to_path_buf(),
            salience_threshold,
            recent_responses: Vec::new(),
            repetition_window: 10,
            count,
        }
    }

    /// Constructor at DEFAULT_CAPTURE_THRESHOLD, for tests and tooling. The
    /// daemon does not call this — it resolves SAGE_CAPTURE_THRESHOLD in
    /// main.rs and calls `new` directly; both paths share the const above.
    pub fn with_defaults(path: &Path) -> Self {
        Self::new(path, DEFAULT_CAPTURE_THRESHOLD)
    }

    fn count_lines(path: &Path) -> u64 {
        fs::read_to_string(path)
            .map(|s| s.lines().filter(|l| !l.trim().is_empty()).count() as u64)
            .unwrap_or(0)
    }

    /// Highest Jaccard overlap (at or above the 0.85 bar) between `response`
    /// and the recent-response window, or None if nothing collides. An empty
    /// response counts as a full collision.
    fn repetition_match(&self, response: &str) -> Option<f64> {
        let response_words: std::collections::HashSet<&str> = response.split_whitespace().collect();
        if response_words.is_empty() {
            return Some(1.0);
        }
        let mut best: Option<f64> = None;
        for recent in &self.recent_responses {
            let recent_words: std::collections::HashSet<&str> = recent.split_whitespace().collect();
            if recent_words.is_empty() {
                continue;
            }
            let intersection = response_words.intersection(&recent_words).count();
            let union = response_words.union(&recent_words).count();
            let jaccard = intersection as f64 / union as f64;
            if jaccard >= 0.85 && best.map_or(true, |b| jaccard > b) {
                best = Some(jaccard);
            }
        }
        best
    }

    /// Sibling of the buffer file: `<stem>_drops.jsonl` next to it.
    fn drops_path(&self) -> PathBuf {
        let stem = self
            .path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("experience");
        self.path.with_file_name(format!("{stem}_drops.jsonl"))
    }

    /// Best-effort: an io-reason stamp can fail for the same cause as the drop
    /// it describes; a missing stamp then reads as unattributed, never as recorded.
    /// `ts` is decision-time (see `decided_ts`), but joins against the presence
    /// log should key on `prompt` — the wake descriptor passes through unchanged,
    /// so it is exact — not on ts proximity.
    fn stamp_drop(&self, entry: &ExperienceEntry, reason: &str, detail: serde_json::Value) {
        if let Some(parent) = self.path.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let mut stamp = serde_json::json!({
            "ts": entry.decided_ts(),
            "reason": reason,
            "salience": entry.salience.total,
            "prompt": entry.prompt,
        });
        if let (Some(obj), serde_json::Value::Object(extra)) = (stamp.as_object_mut(), detail) {
            obj.extend(extra);
        }
        let _ = OpenOptions::new()
            .create(true)
            .append(true)
            .open(self.drops_path())
            .and_then(|mut f| writeln!(f, "{}", stamp));
    }

    pub fn record(&mut self, entry: ExperienceEntry) -> RecordOutcome {
        if entry.salience.total < self.salience_threshold {
            self.stamp_drop(&entry, "salience", serde_json::json!({}));
            return RecordOutcome::DroppedSalience;
        }
        if let Some(score) = self.repetition_match(&entry.response) {
            // The deciding input for this reason is the response (vs the recent
            // window), so stamp it — the same standard the salience reason meets
            // by stamping `salience`.
            self.stamp_drop(
                &entry,
                "repetition",
                serde_json::json!({ "response": entry.response, "match": score }),
            );
            return RecordOutcome::DroppedRepetition;
        }

        if let Some(parent) = self.path.parent() {
            let _ = fs::create_dir_all(parent);
        }

        let line = match serde_json::to_string(&entry) {
            Ok(s) => s,
            Err(_) => {
                self.stamp_drop(&entry, "io", serde_json::json!({}));
                return RecordOutcome::DroppedIo;
            }
        };

        let ok = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .and_then(|mut f| writeln!(f, "{}", line))
            .is_ok();

        if ok {
            self.count += 1;
            self.recent_responses.push(entry.response);
            if self.recent_responses.len() > self.repetition_window {
                self.recent_responses.remove(0);
            }
            RecordOutcome::Recorded
        } else {
            self.stamp_drop(&entry, "io", serde_json::json!({}));
            RecordOutcome::DroppedIo
        }
    }

    pub fn count(&self) -> u64 {
        self.count
    }

    pub fn load_recent(&self, n: usize) -> Vec<ExperienceEntry> {
        let data = match fs::read_to_string(&self.path) {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        };
        let entries: Vec<ExperienceEntry> = data
            .lines()
            .filter_map(|line| serde_json::from_str(line).ok())
            .collect();
        let start = entries.len().saturating_sub(n);
        entries[start..].to_vec()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU32, Ordering};

    static COUNTER: AtomicU32 = AtomicU32::new(0);

    fn temp_path() -> PathBuf {
        let n = COUNTER.fetch_add(1, Ordering::Relaxed);
        std::env::temp_dir().join(format!("sage-exp-test-{}-{n}.jsonl", std::process::id()))
    }

    fn make_entry(prompt: &str, response: &str, total_salience: f64) -> ExperienceEntry {
        ExperienceEntry::new(
            prompt.to_string(),
            response.to_string(),
            SalienceScore::from_components(total_salience, total_salience, total_salience, total_salience, total_salience),
            "wake",
            100.0,
            0,
        )
    }

    fn drops_path_for(path: &PathBuf) -> PathBuf {
        let stem = path.file_stem().unwrap().to_str().unwrap();
        path.with_file_name(format!("{stem}_drops.jsonl"))
    }

    #[test]
    fn records_salient_experience() {
        let path = temp_path();
        let mut buf = ExperienceBuffer::with_defaults(&path);
        let entry = make_entry("hello", "world", 0.8);
        assert!(buf.record(entry).recorded());
        assert_eq!(buf.count(), 1);
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn rejects_low_salience_with_stamped_reason() {
        let path = temp_path();
        let mut buf = ExperienceBuffer::with_defaults(&path);
        let entry = make_entry("hello", "world", 0.2);
        assert_eq!(buf.record(entry), RecordOutcome::DroppedSalience);
        assert_eq!(buf.count(), 0);
        let drops = fs::read_to_string(drops_path_for(&path)).unwrap();
        assert!(drops.contains("\"reason\":\"salience\""));
        let _ = fs::remove_file(&path);
        let _ = fs::remove_file(drops_path_for(&path));
    }

    #[test]
    fn rejects_repetitive_with_stamped_reason() {
        let path = temp_path();
        let mut buf = ExperienceBuffer::with_defaults(&path);
        let e1 = make_entry("q1", "the quick brown fox jumps over the lazy dog", 0.8);
        let e2 = make_entry("q2", "the quick brown fox jumps over the lazy dog", 0.8);
        assert!(buf.record(e1).recorded());
        assert_eq!(buf.record(e2), RecordOutcome::DroppedRepetition);
        assert_eq!(buf.count(), 1);
        let drops = fs::read_to_string(drops_path_for(&path)).unwrap();
        let stamp: serde_json::Value = serde_json::from_str(drops.lines().next().unwrap()).unwrap();
        assert_eq!(stamp["reason"], "repetition");
        assert_eq!(stamp["response"], "the quick brown fox jumps over the lazy dog");
        assert_eq!(stamp["match"].as_f64().unwrap(), 1.0);
        let _ = fs::remove_file(&path);
        let _ = fs::remove_file(drops_path_for(&path));
    }

    #[test]
    fn drop_stamp_uses_decision_time_ts() {
        let path = temp_path();
        let mut buf = ExperienceBuffer::with_defaults(&path);
        let mut entry = make_entry("hello", "world", 0.2);
        entry.received_ts = Some(entry.timestamp - 42.0);
        let expected = entry.decided_ts();
        assert_eq!(buf.record(entry), RecordOutcome::DroppedSalience);
        let drops = fs::read_to_string(drops_path_for(&path)).unwrap();
        let stamp: serde_json::Value = serde_json::from_str(drops.lines().next().unwrap()).unwrap();
        assert_eq!(stamp["ts"].as_f64().unwrap(), expected);
        let _ = fs::remove_file(&path);
        let _ = fs::remove_file(drops_path_for(&path));
    }

    #[test]
    fn persistence_roundtrip() {
        let path = temp_path();
        {
            let mut buf = ExperienceBuffer::with_defaults(&path);
            buf.record(make_entry("q1", "answer one with unique content", 0.8));
            buf.record(make_entry("q2", "answer two with different words entirely", 0.9));
        }
        {
            let buf = ExperienceBuffer::with_defaults(&path);
            assert_eq!(buf.count(), 2);
            let recent = buf.load_recent(10);
            assert_eq!(recent.len(), 2);
            assert_eq!(recent[0].prompt, "q1");
        }
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn id_is_deterministic() {
        let e1 = make_entry("hello", "world", 0.8);
        let e2 = make_entry("hello", "world", 0.5);
        assert_eq!(e1.id, e2.id);
    }
}
