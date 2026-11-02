//! Proprioception: the daemon samples the machine body (GPU, CPU, memory, disk) on a cadence
//! and serves the last snapshot at `GET /body`.
//!
//! dp, 2026-10-06: *"basic proprioception: gpu (usage, memory, temp), cpu (usage, memory, temp),
//! disk (usage, space). basically awareness of its embodied resources. and indicators for same."*
//!
//! ONE SENSOR, ONE SOURCE. The sensor is `sage.gateway.proprioception` (Python, standard library
//! only, one code path for WSL, Linux, Jetson and macOS; NVIDIA, AMD, Intel and Apple GPUs). This
//! module does not reimplement it: like `conversations::arouse`, it runs the canonical module as a
//! subprocess, so a second copy cannot drift. The snapshot carries its own rendered `line`, and both
//! readers take it from here: the being's beat (body.py reads `/body`) and the dashboard. They show
//! the same reading, so they cannot disagree.
//!
//! OFF THE BEAT. The sample runs in this task every `INTERVAL_SECS`; a beat reads a cached snapshot
//! in one loopback request and never waits on nvidia-smi or a `/proc/stat` window. A failed sample
//! is recorded with its reason and the previous snapshot keeps its own `sampled_at`, so staleness
//! is visible instead of hidden.
//!
//! AN INDICATOR, NOT A CONTROL. Nothing in the daemon reads the snapshot to decide anything.

use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde_json::{json, Value};

/// How often the body is sampled.
pub const INTERVAL_SECS: u64 = 10;
/// The Windows host's memory (WSL only) costs ~0.5 s of a Windows process, so it is asked for
/// once every this many samples and carried into the others with its own `sampled_at`.
pub const HOST_EVERY: u64 = 6;
/// A sample that takes longer than this is killed and recorded as a failure.
pub const SAMPLE_TIMEOUT_SECS: u64 = 30;

#[derive(Default)]
pub struct BodyState {
    pub snapshot: Option<Value>,
    pub samples: u64,
    pub failures: u64,
    /// (unix secs, why) of the most recent failed sample, kept until a sample succeeds.
    pub last_error: Option<(u64, String)>,
    /// The most recent Windows-host block, carried into samples that did not re-ask Windows.
    pub wsl_host: Option<Value>,
}

pub type SharedBody = Arc<Mutex<BodyState>>;

/// The sampler's argv after `python3`. Pure, so the contract with the Python CLI is testable.
pub fn sampler_args(instance: &Path, root: &Path, ask_host: bool, carried: Option<&Value>) -> Vec<String> {
    let mut a = vec![
        "-m".to_string(), "sage.gateway.proprioception".to_string(), "--json".to_string(),
        "--disk".to_string(), format!("instance={}", instance.display()),
        "--disk".to_string(), format!("sage={}", root.display()),
    ];
    if !ask_host {
        a.push("--no-wsl-host".to_string());
        if let Some(h) = carried {
            a.push("--wsl-host-from".to_string());
            a.push(h.to_string());
        }
    }
    a
}

/// Record one sample's outcome.
pub fn absorb(st: &mut BodyState, now: u64, result: Result<Value, String>) {
    st.samples += 1;
    match result {
        Ok(v) if v.get("schema").and_then(|s| s.as_str()).map_or(false, |s| s.starts_with("sage.body/")) => {
            if let Some(h) = v.get("wsl_host") {
                st.wsl_host = Some(h.clone());
            }
            st.snapshot = Some(v);
            st.last_error = None;
        }
        Ok(_) => {
            st.failures += 1;
            st.last_error = Some((now, "the sampler answered without a sage.body snapshot".to_string()));
        }
        Err(e) => {
            st.failures += 1;
            st.last_error = Some((now, e));
        }
    }
}

/// What `GET /body` answers: the last snapshot plus how old it is, or 503 with the reason.
pub fn view(st: &BodyState, now: u64) -> (u16, Value) {
    let sampler = json!({
        "interval_secs": INTERVAL_SECS,
        "samples": st.samples,
        "failures": st.failures,
        "last_error": st.last_error.as_ref().map(|(t, e)| json!({"at": t, "error": e})),
    });
    match &st.snapshot {
        Some(snap) => {
            let mut out = snap.clone();
            let at = snap.get("sampled_at").and_then(|v| v.as_f64()).unwrap_or(0.0);
            if let Some(o) = out.as_object_mut() {
                o.insert("served_age_s".to_string(), json!(((now as f64) - at).max(0.0).round()));
                o.insert("sampler".to_string(), sampler);
            }
            (200, out)
        }
        None => (503, json!({
            "unavailable": match &st.last_error {
                Some((_, e)) => format!("no body snapshot yet: {e}"),
                None => "no body snapshot yet: the first sample has not finished".to_string(),
            },
            "sampler": sampler,
        })),
    }
}

async fn sample_once(root: &Path, args: &[String]) -> Result<Value, String> {
    let mut cmd = tokio::process::Command::new("python3");
    cmd.args(args).current_dir(root).kill_on_drop(true);
    let out = tokio::time::timeout(Duration::from_secs(SAMPLE_TIMEOUT_SECS), cmd.output())
        .await
        .map_err(|_| format!("the sampler did not finish in {SAMPLE_TIMEOUT_SECS} s"))?
        .map_err(|e| format!("the sampler could not run: {e}"))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        let last = err.lines().last().unwrap_or("").chars().take(200).collect::<String>();
        return Err(format!("the sampler exited {}: {last}", out.status));
    }
    serde_json::from_slice(&out.stdout).map_err(|e| format!("the sampler's JSON did not parse: {e}"))
}

/// Sample forever, every INTERVAL_SECS, until shutdown.
pub async fn run(cell: SharedBody, root: PathBuf, instance: PathBuf,
                 mut shutdown: tokio::sync::watch::Receiver<bool>) {
    let mut n: u64 = 0;
    let mut tick = tokio::time::interval(Duration::from_secs(INTERVAL_SECS));
    tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    loop {
        tokio::select! {
            _ = tick.tick() => {}
            _ = shutdown.changed() => return,
        }
        let carried = cell.lock().ok().and_then(|s| s.wsl_host.clone());
        let args = sampler_args(&instance, &root, n % HOST_EVERY == 0, carried.as_ref());
        n += 1;
        let r = sample_once(&root, &args).await;
        if let Ok(mut st) = cell.lock() {
            absorb(&mut st, crate::now_secs(), r);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn snap(at: f64) -> Value {
        json!({"schema": "sage.body/1", "sampled_at": at, "line": "GPU 1%", "memory_topology": "discrete"})
    }

    #[test]
    fn before_any_sample_the_endpoint_says_why_not_a_zero() {
        let st = BodyState::default();
        let (code, v) = view(&st, 100);
        assert_eq!(code, 503);
        assert!(v["unavailable"].as_str().unwrap().contains("first sample"));
    }

    #[test]
    fn a_sample_is_served_with_its_age() {
        let mut st = BodyState::default();
        absorb(&mut st, 100, Ok(snap(90.0)));
        let (code, v) = view(&st, 104);
        assert_eq!(code, 200);
        assert_eq!(v["served_age_s"], json!(14.0));
        assert_eq!(v["line"], "GPU 1%");
        assert_eq!(v["sampler"]["samples"], 1);
    }

    #[test]
    fn a_failed_sample_keeps_the_last_snapshot_and_its_old_timestamp() {
        let mut st = BodyState::default();
        absorb(&mut st, 100, Ok(snap(100.0)));
        absorb(&mut st, 110, Err("the sampler exited 1: boom".into()));
        let (code, v) = view(&st, 130);
        assert_eq!(code, 200);
        assert_eq!(v["served_age_s"], json!(30.0), "staleness must be visible, not refreshed");
        assert_eq!(v["sampler"]["failures"], 1);
        assert!(v["sampler"]["last_error"]["error"].as_str().unwrap().contains("boom"));
    }

    #[test]
    fn a_failure_with_no_snapshot_is_reported_as_the_reason() {
        let mut st = BodyState::default();
        absorb(&mut st, 100, Err("the sampler could not run: No such file".into()));
        let (code, v) = view(&st, 101);
        assert_eq!(code, 503);
        assert!(v["unavailable"].as_str().unwrap().contains("No such file"));
    }

    #[test]
    fn a_non_snapshot_answer_is_not_accepted() {
        let mut st = BodyState::default();
        absorb(&mut st, 100, Ok(json!({"hello": 1})));
        assert!(st.snapshot.is_none());
        assert_eq!(st.failures, 1);
    }

    #[test]
    fn the_wsl_host_block_is_carried_into_samples_that_did_not_ask_windows() {
        let mut st = BodyState::default();
        let mut s = snap(100.0);
        s["wsl_host"] = json!({"sampled_at": 100.0, "memory_total_bytes": {"value": 34, "source": "w"}});
        absorb(&mut st, 100, Ok(s));
        let a = sampler_args(Path::new("/i"), Path::new("/r"), false, st.wsl_host.as_ref());
        let i = a.iter().position(|x| x == "--wsl-host-from").expect("carried block passed on");
        assert!(a[i + 1].contains("\"sampled_at\":100.0"));
        assert!(a.contains(&"--no-wsl-host".to_string()));
        let asked = sampler_args(Path::new("/i"), Path::new("/r"), true, st.wsl_host.as_ref());
        assert!(!asked.contains(&"--no-wsl-host".to_string()));
        assert!(!asked.contains(&"--wsl-host-from".to_string()));
    }

    #[test]
    fn the_sampler_is_the_canonical_python_module_with_the_beings_disks() {
        let a = sampler_args(Path::new("/inst"), Path::new("/root"), true, None);
        assert_eq!(&a[..3], &["-m", "sage.gateway.proprioception", "--json"]);
        assert!(a.contains(&"instance=/inst".to_string()));
        assert!(a.contains(&"sage=/root".to_string()));
    }
}
