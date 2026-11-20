//! The being's output as it is produced, for the dashboard: `GET /being/output`.
//!
//! dp, 2026-11-20: *"having the agent's stream in all major cli harnesses is a key feature and
//! liveness indicator, which sage has left out so far."* Each beat's model calls stream into
//! `<instance>/output_stream.jsonl` (Python `sage.gateway.being_stream`): one JSON event per line,
//! `k` = beat | call | think | text | tool | done | error | end. This module only READS that file;
//! the daemon decides nothing from it.
//!
//! INCREMENTAL BY BYTE OFFSET. The dashboard polls about once a second. The first poll (no
//! `after`) gets the tail; each later poll sends back the `offset` it was given and gets only what
//! was appended since. Only whole lines are returned: a line still being written stays for the
//! next poll. When the file was rotated (Python moves it to `.1` past 2 MiB) or replaced, `after`
//! lies past its end; the reply then starts again from the tail and says `reset: true`, so the
//! page clears instead of splicing two files.

use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

pub const STREAM_FILE: &str = "output_stream.jsonl";
/// What a first poll (or a reset) starts with: enough for the last beat or two.
pub const TAIL_BYTES: u64 = 64 * 1024;
/// The most one poll returns; a client far behind catches up over several polls.
pub const MAX_READ: u64 = 512 * 1024;

/// `{"offset", "size", "reset", "events": [...]}`, or `{"missing": true, ...}` with no file yet.
pub fn read_since(instance: &Path, after: Option<u64>) -> serde_json::Value {
    let path = instance.join(STREAM_FILE);
    let mut f = match std::fs::File::open(&path) {
        Ok(f) => f,
        Err(_) => {
            return serde_json::json!({
                "missing": true, "offset": 0, "size": 0, "reset": after.is_some(), "events": [],
                "path": path.display().to_string(),
            })
        }
    };
    let size = f.metadata().map(|m| m.len()).unwrap_or(0);
    let (start, reset) = match after {
        Some(a) if a <= size => (a, false),
        Some(_) => (size.saturating_sub(TAIL_BYTES), true),
        None => (size.saturating_sub(TAIL_BYTES), false),
    };
    let want = (size - start).min(MAX_READ);
    let mut buf = vec![0u8; want as usize];
    if f.seek(SeekFrom::Start(start)).is_err() || f.read_exact(&mut buf).is_err() {
        return serde_json::json!({"offset": start, "size": size, "reset": reset, "events": [],
                                  "error": "the stream file could not be read"});
    }
    // A tail starts mid-file: its first line is cut, so it is skipped. An incremental read starts
    // where the last whole line ended, so its first line is whole.
    let from_tail = after.is_none() || reset;
    let mut lo = 0usize;
    if from_tail && start > 0 {
        lo = buf.iter().position(|&b| b == b'\n').map(|i| i + 1).unwrap_or(buf.len());
    }
    // Only whole lines: the end is the last newline; a line still being written waits.
    let hi = buf.iter().rposition(|&b| b == b'\n').map(|i| i + 1).unwrap_or(0).max(lo);
    let events: Vec<serde_json::Value> = buf[lo..hi]
        .split(|&b| b == b'\n')
        .filter(|l| !l.is_empty())
        .filter_map(|l| serde_json::from_slice(l).ok())
        .collect();
    serde_json::json!({
        "offset": start + hi as u64, "size": size, "reset": reset, "events": events,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn home() -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("sage-output-stream-{}-{}", std::process::id(),
                                                  rand_suffix()));
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    fn rand_suffix() -> u128 {
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()
    }

    fn append(d: &Path, s: &str) {
        let mut f = std::fs::OpenOptions::new().create(true).append(true).open(d.join(STREAM_FILE)).unwrap();
        f.write_all(s.as_bytes()).unwrap();
    }

    fn kinds(v: &serde_json::Value) -> Vec<String> {
        v["events"].as_array().unwrap().iter().map(|e| e["k"].as_str().unwrap().to_string()).collect()
    }

    #[test]
    fn no_file_yet_is_an_empty_answer_not_an_error() {
        let d = home();
        let v = read_since(&d, None);
        assert_eq!(v["missing"], true);
        assert_eq!(v["events"].as_array().unwrap().len(), 0);
    }

    #[test]
    fn a_poll_returns_what_was_appended_since_and_a_half_written_line_waits() {
        let d = home();
        append(&d, "{\"k\":\"beat\"}\n{\"k\":\"call\"}\n");
        let first = read_since(&d, None);
        assert_eq!(kinds(&first), vec!["beat", "call"]);
        let off = first["offset"].as_u64().unwrap();
        append(&d, "{\"k\":\"think\",\"s\":\"a\"}\n{\"k\":\"te");
        let second = read_since(&d, Some(off));
        assert_eq!(kinds(&second), vec!["think"], "the cut line is not returned");
        append(&d, "xt\",\"s\":\"b\"}\n");
        let third = read_since(&d, Some(second["offset"].as_u64().unwrap()));
        assert_eq!(kinds(&third), vec!["text"]);
        assert_eq!(third["events"][0]["s"], "b");
        assert_eq!(third["reset"], false);
    }

    #[test]
    fn a_rotated_file_resets_from_its_tail() {
        let d = home();
        append(&d, "{\"k\":\"beat\"}\n");
        let v = read_since(&d, Some(10_000));
        assert_eq!(v["reset"], true);
        assert_eq!(kinds(&v), vec!["beat"]);
    }

    #[test]
    fn a_tail_skips_the_line_its_window_cut() {
        let d = home();
        let line = format!("{{\"k\":\"text\",\"s\":\"{}\"}}\n", "y".repeat(1000));
        for _ in 0..80 {
            append(&d, &line);
        }
        append(&d, "{\"k\":\"end\"}\n");
        let v = read_since(&d, None);
        let ev = v["events"].as_array().unwrap();
        assert!(!ev.is_empty() && ev.len() < 81);
        assert_eq!(ev.last().unwrap()["k"], "end");
        assert!(ev.iter().all(|e| e["k"].is_string()), "no cut fragment parsed");
    }
}
