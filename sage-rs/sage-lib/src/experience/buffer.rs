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
    /// The daemon's INTERNAL ATP controller at the moment of the exchange: a free-running
    /// oscillator ticked every 100 ms for the shadow-metabolism experiment, which nothing the
    /// being does moves (SAGE #291). Written as `internal_atp` since SAGE #295 so no reader
    /// takes it for the being's energy; older lines named it `atp_percentage` and still read.
    #[serde(rename = "internal_atp", alias = "atp_percentage")]
    pub internal_atp: f64,
    /// The consciousness loop's tick count (100 ms idle ticks: uptime x 10), not a beat or a
    /// cycle of anything the being did. Older lines named it `cycle` and still read.
    #[serde(rename = "tick", alias = "cycle")]
    pub tick: u64,
    pub timestamp: f64,
    /// The heartbeat beat that was running when this exchange happened, from the activity
    /// reports (SAGE #295). Absent when no beat was running (a presence noticing between beats).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub beat_id: Option<String>,
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
        internal_atp: f64,
        tick: u64,
    ) -> Self {
        let id = Self::compute_id(&prompt, &response);
        let timestamp = crate::snarc::temporal::now_secs();
        Self {
            id,
            prompt,
            response,
            salience,
            metabolic_state: metabolic_state.to_string(),
            internal_atp,
            tick,
            timestamp,
            beat_id: None,
            machine: None,
            model: None,
        }
    }
}

/// Rotate the experience record past this size, keeping one prior generation (`.jsonl.1`),
/// the same shape as the shadow-metabolism log's bound. Recording every exchange (SAGE #291)
/// removes the salience gate that used to thin it. The largest record in the fleet was
/// 540 KB after months (sprout-qwen3.8-distill-2b, 696 rows, measured 2026-09-30), so this is
/// ~30x headroom. It only has to be a bound, not a tight one.
pub const EXPERIENCE_MAX_BYTES: u64 = 16 * 1024 * 1024;

/// The being's record of what it generated.
///
/// SNARC IS AN INDICATOR, NOT A CONTROL (dp, 2026-09-30; SAGE #291). `record` used to drop
/// every exchange whose `salience.total` was under 0.5, so SNARC decided what the being
/// remembered. That is the "capture gate" of #24/#58. Now every exchange is recorded, with
/// its SNARC score as an annotation. A reader that wants the salient ones selects them
/// (ollama_raising_session.py already sorts by `salience.total`; prepare_training_data.py
/// takes a `min_salience`).
///
/// The repetition filter stays. It does not read salience: it drops near-duplicate text
/// (word-Jaccard >= 0.85 against the last 10 responses). It is still a filter on memory,
/// and #291 flags it for dp rather than changing it.
pub struct ExperienceBuffer {
    path: PathBuf,
    recent_responses: Vec<String>,
    repetition_window: usize,
    count: u64,
    max_bytes: u64,
}

impl ExperienceBuffer {
    pub fn new(path: &Path) -> Self {
        let count = Self::count_lines(path);
        Self {
            path: path.to_path_buf(),
            recent_responses: Vec::new(),
            repetition_window: 10,
            count,
            max_bytes: EXPERIENCE_MAX_BYTES,
        }
    }

    pub fn with_defaults(path: &Path) -> Self {
        Self::new(path)
    }

    /// A smaller bound, for tests of the rotation.
    pub fn with_max_bytes(mut self, max_bytes: u64) -> Self {
        self.max_bytes = max_bytes;
        self
    }

    fn count_lines(path: &Path) -> u64 {
        fs::read_to_string(path)
            .map(|s| s.lines().filter(|l| !l.trim().is_empty()).count() as u64)
            .unwrap_or(0)
    }

    fn is_repetitive(&self, response: &str) -> bool {
        let response_words: std::collections::HashSet<&str> = response.split_whitespace().collect();
        if response_words.is_empty() {
            return true;
        }
        for recent in &self.recent_responses {
            let recent_words: std::collections::HashSet<&str> = recent.split_whitespace().collect();
            if recent_words.is_empty() {
                continue;
            }
            let intersection = response_words.intersection(&recent_words).count();
            let union = response_words.union(&recent_words).count();
            let jaccard = intersection as f64 / union as f64;
            if jaccard >= 0.85 {
                return true;
            }
        }
        false
    }

    pub fn record(&mut self, entry: ExperienceEntry) -> bool {
        // No salience gate (SAGE #291): the score is recorded on the entry, not used to
        // decide whether there is an entry.
        if self.is_repetitive(&entry.response) {
            return false;
        }

        if let Some(parent) = self.path.parent() {
            let _ = fs::create_dir_all(parent);
        }

        // Bounded, like the shadow log: past the cap the file becomes `.jsonl.1` (replacing
        // any older one) and a fresh file starts. `count` is this file's rows.
        if let Ok(md) = fs::metadata(&self.path) {
            if md.len() > self.max_bytes
                && fs::rename(&self.path, self.path.with_extension("jsonl.1")).is_ok()
            {
                self.count = 0;
            }
        }

        let line = match serde_json::to_string(&entry) {
            Ok(s) => s,
            Err(_) => return false,
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
        }

        ok
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

    #[test]
    fn records_salient_experience() {
        let path = temp_path();
        let mut buf = ExperienceBuffer::with_defaults(&path);
        let entry = make_entry("hello", "world", 0.8);
        assert!(buf.record(entry));
        assert_eq!(buf.count(), 1);
        let _ = fs::remove_file(&path);
    }

    /// SAGE #291: SNARC is an indicator, not a control. A low-salience exchange is still
    /// remembered, and its score travels with it for a reader to select on. This was
    /// `rejects_low_salience`, the test that pinned the gate.
    #[test]
    fn a_low_salience_exchange_is_still_recorded_with_its_score() {
        let path = temp_path();
        let mut buf = ExperienceBuffer::with_defaults(&path);
        assert!(buf.record(make_entry("hello", "world", 0.2)));
        assert!(buf.record(make_entry("quiet", "nothing much stood out here", 0.0)));
        assert_eq!(buf.count(), 2);
        let got = buf.load_recent(10);
        assert!((got[0].salience.total - 0.2).abs() < 1e-9, "the score is kept as an annotation");
        assert_eq!(got[1].salience.total, 0.0);
        let _ = fs::remove_file(&path);
    }

    #[test]
    fn the_record_is_bounded_and_keeps_one_prior_generation() {
        let path = temp_path();
        let rotated = path.with_extension("jsonl.1");
        let mut buf = ExperienceBuffer::with_defaults(&path).with_max_bytes(600);
        for i in 0..12 {
            assert!(buf.record(make_entry(&format!("q{i}"),
                &format!("answer number {i} with its own distinct words {}", "x".repeat(i)), 0.1)));
        }
        let live = fs::metadata(&path).unwrap().len();
        assert!(live <= 600 + 400, "the live file stays near its bound: {live}");
        assert!(rotated.exists(), "the prior generation is kept");
        assert_eq!(buf.count() as usize, buf.load_recent(100).len(), "count is this file's rows");
        let _ = fs::remove_file(&path);
        let _ = fs::remove_file(&rotated);
    }

    #[test]
    fn rejects_repetitive() {
        let path = temp_path();
        let mut buf = ExperienceBuffer::with_defaults(&path);
        let e1 = make_entry("q1", "the quick brown fox jumps over the lazy dog", 0.8);
        let e2 = make_entry("q2", "the quick brown fox jumps over the lazy dog", 0.8);
        assert!(buf.record(e1));
        assert!(!buf.record(e2));
        assert_eq!(buf.count(), 1);
        let _ = fs::remove_file(&path);
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

    /// SAGE #295: the internal ATP and the loop tick are written under names no reader takes for
    /// the being's energy or its beats, the beat is stamped when known, and older lines still read.
    #[test]
    fn records_name_the_internal_atp_and_the_tick_and_carry_the_beat() {
        let mut e = make_entry("hi", "there", 0.4);
        e.beat_id = Some("heartbeat-abc".into());
        let v: serde_json::Value = serde_json::to_value(&e).unwrap();
        assert!(v.get("atp_percentage").is_none() && v.get("cycle").is_none(), "{v}");
        assert_eq!(v["internal_atp"], 100.0);
        assert_eq!(v["tick"], 0);
        assert_eq!(v["beat_id"], "heartbeat-abc");

        let unbeaten = serde_json::to_value(make_entry("a", "b", 0.1)).unwrap();
        assert!(unbeaten.get("beat_id").is_none(), "no beat running: no beat_id key");

        let old = r#"{"id":"x","prompt":"p","response":"r","salience":{"surprise":0.1,"novelty":0.1,"arousal":0.1,"reward":0.1,"conflict":0.1,"total":0.1},"metabolic_state":"wake","atp_percentage":42.5,"cycle":1593000,"timestamp":1.0}"#;
        let o: ExperienceEntry = serde_json::from_str(old).unwrap();
        assert_eq!((o.internal_atp, o.tick, o.beat_id), (42.5, 1_593_000, None));
    }
}
