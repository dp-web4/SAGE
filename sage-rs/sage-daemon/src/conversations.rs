//! Conversations — the daemon's half of a being's two-way channels.
//!
//! dp, 2026-09-07: *"let's keep going with conversations ui, and shift from raw llm chat to
//! sage-being chat canonically, so all machines can pick it up. do this carefully, but
//! deliberately."*
//!
//! The dashboard's chat box talked to the raw weights on the same GPU: no identity, no
//! governance gate, no memory, no entrustment. Useful for probing a model, and not a
//! conversation with the being that lives on this machine. This module makes the daemon a
//! participant in the SAME record the being reads and writes, rather than a second one.
//!
//! ONE STORE, TWO WRITERS. The files are the Python side's
//! `sage/gateway/conversations.py` format, byte for byte: append-only JSONL of attributed
//! turns beside a `.meta.json` naming participants and `writable_by`. Nothing is
//! re-implemented here that decides policy — who may speak comes from the meta file, and
//! whether a turn is worth waking the being for comes from `sage.gateway.arousal`, invoked
//! as a subprocess. Encoding those weights a second time in Rust would make two producers
//! of one fact, which is the defect this repository has now repaired four times in a single
//! day (the fleet gateway URL, the check command, the beat window, the fleet registry).
//!
//! WRITES TAKE flock(LOCK_EX). A turn is prose and routinely exceeds PIPE_BUF, so O_APPEND
//! alone is not atomic for it; without the lock two writers produce interleaved half-lines
//! in the one record that is supposed to be the durable account of what was said. The
//! sequence number is computed inside the lock for the same reason.

use serde::{Deserialize, Serialize};
use std::fs::{File, OpenOptions};
use std::io::{BufRead, BufReader, Seek, SeekFrom, Write};
use std::os::unix::io::AsRawFd;
use std::path::{Path, PathBuf};

/// The fleet's display convention, matching `/chat-history?limit=N` and the Python
/// `DEFAULT_LIMIT`: storage keeps everything, the view is bounded.
pub const DEFAULT_LIMIT: usize = 50;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Meta {
    pub id: String,
    pub title: String,
    #[serde(default)]
    pub participants: Vec<String>,
    #[serde(default)]
    pub writable_by: Vec<String>,
    #[serde(default)]
    pub summary: String,
    #[serde(default)]
    pub created: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Turn {
    #[serde(default)]
    pub ts: String,
    #[serde(default)]
    pub seq: u64,
    #[serde(rename = "from", default)]
    pub from: String,
    #[serde(default)]
    pub text: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub witness: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub beat: Option<String>,
    /// PROVENANCE: which channel asserted `from`. The Python writer records the same
    /// field ("say" for the being's gated verb, "dp-console" for the loopback page);
    /// this daemon writes "daemon-loopback". A turn without it predates the field.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub via: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Summary {
    #[serde(flatten)]
    pub meta: Meta,
    pub count: usize,
    pub last: Option<Turn>,
    /// Turns since the being last spoke — i.e. what is waiting on it. The one thing a
    /// reader should never have to infer.
    pub awaiting_being: usize,
}

/// Where a being's conversations live. This is the BEING's home, which is not always the
/// daemon's model-derived instance path: on Legion the daemon writes to
/// `legion-qwen38-heretic-q3km/` while the being has lived in `legion-gemma3-12b/` since
/// before a whole-model transplant. Identity is not substrate, so the being's home is
/// configured (`SAGE_BEING_INSTANCE`) rather than derived, and falls back to the daemon's
/// own instance dir for a machine where they coincide.
pub fn being_instance(root: &Path, machine: &str, model: &str) -> PathBuf {
    if let Ok(p) = std::env::var("SAGE_BEING_INSTANCE") {
        return PathBuf::from(p);
    }
    // The daemon's own instance slug replaces colons and NOTHING else, because that is what
    // the directories on disk are named: `sprout-qwen3.8-distill-2b`, dot intact. This
    // function also replaced dots, so on every machine whose model carries one the being's
    // conversations pointed at `sprout-qwen3-8-distill-2b` — a directory that has never
    // existed — while the daemon's experience buffer and chat history wrote to the real one.
    // One being, two homes, and the route that lets a person speak to it answered 503
    // forever with a path nobody could find.
    //
    // Prefer the real convention. A machine that already grew a home under the old
    // dot-replaced name keeps it: that directory holds real turns, and silently relocating
    // a being's conversations to fix a path bug would lose the conversations.
    let canonical = root.join(format!("sage/instances/{}-{}", machine, model.replace(':', "-")));
    let legacy = root.join(format!("sage/instances/{}-{}", machine, model.replace([':', '.'], "-")));
    if legacy != canonical && dir(&legacy).is_dir() && !dir(&canonical).is_dir() {
        return legacy;
    }
    canonical
}

fn dir(instance: &Path) -> PathBuf {
    instance.join("conversations")
}

fn paths(instance: &Path, id: &str) -> (PathBuf, PathBuf) {
    let d = dir(instance);
    (d.join(format!("{id}.jsonl")), d.join(format!("{id}.meta.json")))
}

/// Ids are used to build a path, so they are validated as a whole and never as a fragment:
/// lowercase alphanumerics and dashes, nothing else. `..`, `/` and `%` cannot survive this.
pub fn valid_id(id: &str) -> bool {
    !id.is_empty()
        && id.len() <= 41
        && id
            .chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
        && id.starts_with(|c: char| c.is_ascii_lowercase() || c.is_ascii_digit())
}

pub fn get_meta(instance: &Path, id: &str) -> Option<Meta> {
    if !valid_id(id) {
        return None;
    }
    let (_, meta) = paths(instance, id);
    serde_json::from_str(&std::fs::read_to_string(meta).ok()?).ok()
}

pub fn read_turns(instance: &Path, id: &str, limit: usize) -> (Vec<Turn>, usize) {
    if !valid_id(id) {
        return (vec![], 0);
    }
    let (log, _) = paths(instance, id);
    let content = match std::fs::read_to_string(&log) {
        Ok(c) => c,
        Err(_) => return (vec![], 0),
    };
    // TOTAL IS READABLE TURNS, NOT LINES. Found by legion-being from reading the Python
    // twin's source: counting every non-empty line while the reader skips unparseable ones
    // makes "showing the last X of {total}" claim history that is not there. Same defect,
    // same shape, one language over — which is exactly what a shared format invites.
    let lines: Vec<&str> = content.lines().filter(|l| !l.trim().is_empty()).collect();
    let parsed: Vec<Turn> = lines
        .iter()
        .filter_map(|l| serde_json::from_str::<Turn>(l).ok())
        .collect();
    let total = parsed.len();
    let start = total.saturating_sub(limit.max(1));
    (parsed[start..].to_vec(), total)
}

/// Turns `me` has NOT BEEN SHOWN — the Python side's definition, read from the same
/// `.seen.json` the heartbeat writes at compose time. The first cut counted "turns since
/// `me` last spoke", which missed a real case within a day: two turns arrived while a beat
/// ran, and the being replied at reflection without having read them. Two producers of
/// one fact again, so the daemon reads the record rather than re-deriving it, and falls
/// back to the proxy only for an instance with no seen-record.
fn awaiting(instance: &Path, id: &str, turns: &[Turn], me: &str) -> usize {
    let seen: u64 = std::fs::read_to_string(dir(instance).join(".seen.json"))
        .ok()
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
        .and_then(|v| v.get(format!("{me}:{id}")).and_then(|n| n.as_u64()))
        .unwrap_or(0);
    if seen > 0 {
        return turns.iter().filter(|t| t.seq > seen && t.from != me).count();
    }
    match turns.iter().rposition(|t| t.from == me) {
        Some(i) => turns.len() - i - 1,
        None => turns.len(),
    }
}

pub fn list(instance: &Path, being: &str) -> Vec<Summary> {
    let mut out = Vec::new();
    let d = dir(instance);
    let rd = match std::fs::read_dir(&d) {
        Ok(rd) => rd,
        Err(_) => return out,
    };
    for entry in rd.flatten() {
        let name = entry.file_name().to_string_lossy().to_string();
        let id = match name.strip_suffix(".meta.json") {
            Some(i) => i.to_string(),
            None => continue,
        };
        if let Some(meta) = get_meta(instance, &id) {
            // Enough turns to answer "is it their move", not the whole history: this is a
            // listing, and a listing that reads every file is a listing that gets slow and
            // then gets cached and then gets stale.
            let (turns, count) = read_turns(instance, &id, 200);
            out.push(Summary {
                awaiting_being: awaiting(instance, &id, &turns, being),
                last: turns.last().cloned(),
                count,
                meta,
            });
        }
    }
    out.sort_by(|a, b| {
        let ka = a.last.as_ref().map(|t| t.ts.clone()).unwrap_or_else(|| a.meta.created.clone());
        let kb = b.last.as_ref().map(|t| t.ts.clone()).unwrap_or_else(|| b.meta.created.clone());
        kb.cmp(&ka)
    });
    out
}

/// Append a turn, honouring `writable_by`. Returns the turn, or the refusal as written —
/// "you may read this and may not speak in it" is a different fact from "no such
/// conversation", and a caller should never have to guess which it hit.
pub fn append(instance: &Path, id: &str, speaker: &str, text: &str) -> Result<Turn, String> {
    append_via(instance, id, speaker, text, None)
}

/// `append` with the channel that asserted the speaker recorded on the turn. The daemon's
/// HTTP routes pass "daemon-loopback" — and only accept a speaker over loopback at all
/// (see `loopback_only` in main.rs): the daemon binds 0.0.0.0 for federation, and a LAN
/// peer must not be able to write `from: dp` into the operator's own conversation.
/// Where a conversation's high-water witness lives: OUTSIDE the repository. The Python writer
/// computes the same path (`conversations.py::witness_path`); the two MUST agree.
///
/// GPT's review of SAGE#126, finding 3: a high-water mark kept in the tracked meta beside the
/// log is rolled back by the same rebase/checkout/reset that rolls back the log, so it cannot
/// witness the failure it names. This is machine-local runtime state no Git command touches.
pub fn witness_path(instance: &Path, id: &str) -> PathBuf {
    let base = std::env::var("SAGE_CONV_WITNESS_DIR").ok().filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            // Unit tests never touch the machine's real witness (they did, once: a
            // `conv-rs-<pid>` directory turned up in ~/.sage beside the being's own).
            if cfg!(test) {
                return std::env::temp_dir().join("sage-conv-witness-test");
            }
            PathBuf::from(std::env::var("HOME").unwrap_or_else(|_| ".".into()))
                .join(".sage").join("conversation-witness")
        });
    let inst = std::fs::canonicalize(instance).unwrap_or_else(|_| instance.to_path_buf());
    let name = inst.file_name().map(|n| n.to_string_lossy().to_string()).unwrap_or_default();
    base.join(name).join(format!("{id}.json"))
}

/// The next sequence number — the same rule as `conversations.py::next_seq`, because there are
/// TWO writers and a rule only one of them follows is not an invariant (GPT, finding 2: this
/// side counted lines and knew nothing of the high-water mark, so after Python resumed past a
/// gap at seq 6 in a two-line file, a dashboard turn would have been written as seq 3).
///
/// `max(max seq in the log, the witness's high-water, lines occupied) + 1`. Never the line
/// count alone (finding 1: after a gap it is behind forever and re-detects the truncation on
/// every append). Call with the log's flock held.
fn next_seq(instance: &Path, id: &str, lines: &[String]) -> Result<u64, String> {
    let mut max_in_log: u64 = 0;
    let mut occupied: u64 = 0;
    for l in lines {
        if l.trim().is_empty() { continue; }
        occupied += 1;
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(l) {
            if let Some(n) = v.get("seq").and_then(|x| x.as_u64()) {
                max_in_log = max_in_log.max(n);
            }
        }
    }
    let wp = witness_path(instance, id);
    let mut w: serde_json::Value = std::fs::read_to_string(&wp).ok()
        .and_then(|t| serde_json::from_str(&t).ok())
        .filter(|v: &serde_json::Value| v.is_object())
        .unwrap_or_else(|| serde_json::json!({}));
    let hw = w.get("high_water_seq").and_then(|x| x.as_u64()).unwrap_or(0);
    if max_in_log < hw {
        let scar = serde_json::json!({"noticed": iso_utc_now(), "max_seq_in_log": max_in_log,
                                      "high_water": hw, "resumed_at": hw + 1});
        match w.get_mut("truncations").and_then(|t| t.as_array_mut()) {
            Some(a) => a.push(scar),
            None => { w["truncations"] = serde_json::json!([scar]); }
        }
    }
    let seq = max_in_log.max(hw).max(occupied) + 1;
    w["high_water_seq"] = serde_json::json!(seq);
    if let Some(parent) = wp.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("witness dir: {e}"))?;
    }
    let tmp = wp.with_extension("json.tmp");
    std::fs::write(&tmp, serde_json::to_string_pretty(&w).map_err(|e| e.to_string())? + "\n")
        .map_err(|e| format!("witness write: {e}"))?;
    std::fs::rename(&tmp, &wp).map_err(|e| format!("witness rename: {e}"))?;
    Ok(seq)
}

pub fn append_via(instance: &Path, id: &str, speaker: &str, text: &str,
                  via: Option<&str>) -> Result<Turn, String> {
    let meta = get_meta(instance, id).ok_or_else(|| format!("no such conversation: {id}"))?;
    let text = text.trim();
    if text.is_empty() {
        return Err("a turn needs something said in it".to_string());
    }
    if !meta.writable_by.iter().any(|w| w == speaker) {
        return Err(format!(
            "{speaker} may read '{id}' and may not speak in it (writable_by: {:?})",
            meta.writable_by
        ));
    }

    let (log, _) = paths(instance, id);
    if let Some(parent) = log.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    let mut f = OpenOptions::new()
        .read(true)
        .append(true)
        .create(true)
        .open(&log)
        .map_err(|e| format!("cannot open {}: {e}", log.display()))?;

    // Exclusive across processes: the Python heartbeat holds the same lock when the being
    // answers. Released when the fd closes, including on an early return or a panic.
    let _guard = FlockGuard::acquire(&f)?;

    f.seek(SeekFrom::Start(0)).map_err(|e| e.to_string())?;
    let lines: Vec<String> = BufReader::new(&f).lines().map_while(Result::ok).collect();
    let seq = next_seq(instance, id, &lines)?;

    let turn = Turn {
        ts: iso_utc_now(),
        seq,
        from: speaker.to_string(),
        text: text.to_string(),
        witness: None,
        beat: None,
        via: via.map(str::to_string),
    };
    let line = serde_json::to_string(&turn).map_err(|e| e.to_string())?;
    f.seek(SeekFrom::End(0)).map_err(|e| e.to_string())?;
    writeln!(f, "{line}").map_err(|e| format!("cannot append: {e}"))?;
    f.sync_all().map_err(|e| e.to_string())?;
    Ok(turn)
}

/// `2026-09-07T22:41:03Z`, the same shape the Python writer produces.
///
/// Hand-rolled rather than pulling in chrono for one call — and NOT reusing sage-lib's
/// `chrono_now_utc`, which emits "{days}d-{hh}:{mm}:{ss}Z" (its own comment says
/// "approximate date — good enough for a timestamp string"). It is not good enough here:
/// these turns interleave in one file with Python-written ISO timestamps, and a reader
/// sorting the record by `ts` would put every daemon turn in the wrong place forever.
fn iso_utc_now() -> String {
    let secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let (days, rem) = (secs.div_euclid(86_400), secs.rem_euclid(86_400));
    let (y, m, d) = civil_from_days(days);
    format!("{y:04}-{m:02}-{d:02}T{:02}:{:02}:{:02}Z", rem / 3600, (rem % 3600) / 60, rem % 60)
}

/// Days since 1970-01-01 -> (year, month, day). Hinnant's civil-from-days, which is exact
/// for the proleptic Gregorian calendar and needs no leap-year special cases at call sites.
fn civil_from_days(z: i64) -> (i64, u32, u32) {
    let z = z + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = (z - era * 146_097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let m = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (if m <= 2 { y + 1 } else { y }, m, d)
}

/// flock held for the lifetime of the guard, released on drop — so an early return or a
/// panic between acquire and write cannot leave the file locked against the being.
struct FlockGuard(i32);

impl FlockGuard {
    fn acquire(f: &File) -> Result<Self, String> {
        let fd = f.as_raw_fd();
        // SAFETY: fd is owned by the caller's File and outlives this guard.
        let rc = unsafe { libc::flock(fd, libc::LOCK_EX) };
        if rc != 0 {
            return Err(format!("cannot lock conversation: {}", std::io::Error::last_os_error()));
        }
        Ok(FlockGuard(fd))
    }
}

impl Drop for FlockGuard {
    fn drop(&mut self) {
        unsafe { libc::flock(self.0, libc::LOCK_UN) };
    }
}

/// Ask the canonical arousal policy whether this turn is worth waking the being for.
///
/// Deliberately a subprocess into `sage.gateway.arousal` rather than a reimplementation:
/// the salience weights, the engagement threshold and the refractory period are one policy
/// with two callers, and a second copy in Rust would drift the moment either moved.
/// A failure here is reported, never fatal — the turn is already durably recorded, and the
/// being reads it at its next beat regardless.
pub fn arouse(root: &Path, instance: &Path, kind: &str, descriptor: &str) -> serde_json::Value {
    let out = std::process::Command::new("python3")
        .arg("-m")
        .arg("sage.gateway.arousal")
        .arg("--instance")
        .arg(instance)
        .arg("--kind")
        .arg(kind)
        .arg("--descriptor")
        .arg(descriptor)
        .current_dir(root)
        .output();
    match out {
        Ok(o) => serde_json::from_slice(&o.stdout).unwrap_or_else(|_| {
            serde_json::json!({
                "engage": false,
                "reason": format!("arousal policy unreadable: {}",
                                  String::from_utf8_lossy(&o.stderr).chars().take(200).collect::<String>())
            })
        }),
        Err(e) => serde_json::json!({
            "engage": false,
            "reason": format!("arousal policy could not run ({e}); the turn is recorded and \
                               will be read at the next scheduled beat")
        }),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The being's home must be the directory that exists. `model.replace(['\:', '.'], "-")`
    /// pointed Sprout's conversations at `sprout-qwen3-8-distill-2b` while every other part
    /// of the daemon wrote to `sprout-qwen3.8-distill-2b`, so the route that lets a person
    /// speak to the being answered 503 against a path nobody could create by convention.
    #[test]
    fn the_beings_home_is_the_directory_that_exists() {
        let root = std::path::Path::new("/tmp/does-not-matter");
        assert_eq!(being_instance(root, "sprout", "qwen3.8-distill:2b"),
                   root.join("sage/instances/sprout-qwen3.8-distill-2b"),
                   "the dot belongs to the model name and survives");
        assert_eq!(being_instance(root, "legion", "gemma3:12b"),
                   root.join("sage/instances/legion-gemma3-12b"),
                   "colons still become dashes");
    }

    /// A machine that already grew a home under the old dot-replaced name keeps it: that
    /// directory holds real turns, and relocating a being's conversations to fix a path bug
    /// would lose them.
    #[test]
    fn an_existing_legacy_home_is_not_silently_abandoned() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("target")
            .join("legacy-home-test");
        // "q3.5:1b" -> canonical "m-q3.5-1b"; the old dot-replacing slug was "m-q3-5-1b"
        let legacy = root.join("sage/instances/m-q3-5-1b");
        let canonical = root.join("sage/instances/m-q3.5-1b");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(legacy.join("conversations")).unwrap();
        assert_eq!(being_instance(&root, "m", "q3.5:1b"), legacy,
                   "the home that already holds the conversations wins");

        // and once the canonical home exists too, that is the one used
        std::fs::create_dir_all(canonical.join("conversations")).unwrap();
        assert_eq!(being_instance(&root, "m", "q3.5:1b"), canonical,
                   "the convention wins as soon as following it costs nothing");
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn timestamps_match_the_python_writer_and_sort_correctly() {
        // known epoch seconds -> known UTC civil date, including a leap day and a century
        assert_eq!(civil_from_days(0), (1970, 1, 1));
        assert_eq!(civil_from_days(19_608), (2023, 9, 8));
        assert_eq!(civil_from_days(59), (1970, 3, 1));
        assert_eq!(civil_from_days(11_016), (2000, 2, 29), "2000 is a leap year");
        assert_eq!(civil_from_days(-1), (1969, 12, 31));

        let now = iso_utc_now();
        assert_eq!(now.len(), 20, "{now}");
        assert!(now.ends_with('Z') && now.as_bytes()[10] == b'T', "{now}");
        // lexicographic order must equal chronological order, which is the whole point
        assert!("2026-09-07T22:00:00Z" < "2026-09-07T22:41:03Z");
        assert!(now.starts_with("20"));
    }

    #[test]
    fn ids_that_could_escape_a_path_are_refused() {
        for good in ["dp", "legion-claude", "a1", "x-2-y"] {
            assert!(valid_id(good), "{good} should be a valid id");
        }
        for bad in ["", "..", "../etc", "a/b", "A", "a b", "a.b", "-lead", "%2e%2e"] {
            assert!(!valid_id(bad), "{bad:?} must be refused");
        }
    }

    #[test]
    fn a_damaged_line_is_not_counted_as_history() {
        let dir = std::env::temp_dir().join(format!("conv-rs-dmg-{}", std::process::id()));
        let cdir = dir.join("conversations");
        std::fs::create_dir_all(&cdir).unwrap();
        std::fs::write(cdir.join("c.meta.json"),
            r#"{"id":"c","title":"t","participants":["a"],"writable_by":["a"]}"#).unwrap();
        std::fs::write(cdir.join("c.jsonl"), concat!(
            "{\"ts\":\"2026-09-08T00:00:01Z\",\"seq\":1,\"from\":\"a\",\"text\":\"one\"}\n",
            "{\"ts\":\"2026-09-08T00:00:02Z\",\"seq\":2,\"from\":\"a\",\"te\n",
            "{\"ts\":\"2026-09-08T00:00:03Z\",\"seq\":3,\"from\":\"a\",\"text\":\"three\"}\n",
        )).unwrap();

        let (turns, total) = read_turns(&dir, "c", DEFAULT_LIMIT);
        assert_eq!(turns.len(), 2, "only readable turns are returned");
        assert_eq!(total, 2, "and total must agree with them, or the view claims lost history");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn awaiting_counts_turns_since_the_being_spoke() {
        let t = |from: &str| Turn {
            ts: String::new(), seq: 0, from: from.into(), text: String::new(),
            witness: None, beat: None,
            via: None,
        };
        let nowhere = std::env::temp_dir().join("conv-rs-no-seen");
        let aw = |ts: &[Turn]| awaiting(&nowhere, "x", ts, "being");
        assert_eq!(aw(&[t("dp"), t("being"), t("dp")]), 1);
        assert_eq!(aw(&[t("dp"), t("being")]), 0);
        // never spoken: everything is waiting on it, not zero
        assert_eq!(aw(&[t("dp"), t("dp")]), 2);
        assert_eq!(aw(&[]), 0);
    }

    #[test]
    fn append_honours_writable_by_and_refuses_distinctly() {
        let dir = std::env::temp_dir().join(format!("conv-rs-{}", std::process::id()));
        let cdir = dir.join("conversations");
        std::fs::create_dir_all(&cdir).unwrap();
        std::fs::write(
            cdir.join("seat.meta.json"),
            r#"{"id":"seat","title":"t","participants":["legion-claude","b"],"writable_by":["legion-claude","b"]}"#,
        )
        .unwrap();

        let refused = append(&dir, "seat", "dp", "dp butting in").unwrap_err();
        assert!(refused.contains("may not speak in it"), "{refused}");
        let missing = append(&dir, "nope", "dp", "x").unwrap_err();
        assert!(missing.contains("no such conversation"), "{missing}");
        assert!(append(&dir, "seat", "b", "  ").is_err(), "an empty turn is not a turn");

        let t1 = append(&dir, "seat", "b", "first").unwrap();
        let t2 = append(&dir, "seat", "b", "second").unwrap();
        assert_eq!((t1.seq, t2.seq), (1, 2), "sequence is assigned under the lock");
        let (turns, total) = read_turns(&dir, "seat", DEFAULT_LIMIT);
        assert_eq!(total, 2);
        assert_eq!(turns[1].text, "second");

        let _ = std::fs::remove_dir_all(&dir);
    }
}

#[cfg(test)]
mod cross_writer_tests {
    use super::*;

    /// THE TWO WRITERS MUST AGREE ON THE FORMAT, or the record silently splits in half.
    /// This reads a turn written by the Python side and writes one the Python side must be
    /// able to read back: same keys, same ISO timestamp shape, same `from` field name.
    #[test]
    fn a_python_written_turn_round_trips() {
        let python_line = r#"{"ts": "2026-09-07T22:22:49Z", "seq": 2, "from": "dp", "text": "hi", "witness": "act-9", "beat": "heartbeat-abc"}"#;
        let t: Turn = serde_json::from_str(python_line).expect("must parse the Python writer's line");
        assert_eq!((t.seq, t.from.as_str(), t.text.as_str()), (2, "dp", "hi"));
        assert_eq!(t.witness.as_deref(), Some("act-9"));
        assert_eq!(t.beat.as_deref(), Some("heartbeat-abc"));

        // and what Rust writes uses the same key names, so Python's json.loads sees them
        let mine = serde_json::to_string(&Turn {
            ts: iso_utc_now(), seq: 3, from: "dp".into(), text: "x".into(),
            witness: None, beat: None,
            via: None,
        }).unwrap();
        let v: serde_json::Value = serde_json::from_str(&mine).unwrap();
        assert!(v.get("from").is_some(), "the field is `from`, not `from_`: {mine}");
        assert!(v.get("witness").is_none(), "absent optionals are omitted, not null");
        let ts = v["ts"].as_str().unwrap();
        assert_eq!(ts.len(), 20, "same ISO shape the Python writer emits: {ts}");
    }

    /// A meta file with fields Rust does not know about must still load: the Python side
    /// owns this schema and will grow it, and a daemon that refuses the whole conversation
    /// over an unknown key is the fleet-registry defect again, one directory over.
    #[test]
    fn unknown_meta_fields_do_not_refuse_the_conversation() {
        let m: Meta = serde_json::from_str(
            r#"{"id":"dp","title":"t","participants":["dp"],"writable_by":["dp"],
                "summary":"s","created":"2026-09-07T00:00:00Z","some_future_field":42}"#,
        )
        .expect("an unknown field must not refuse the meta");
        assert_eq!(m.id, "dp");
    }
}
