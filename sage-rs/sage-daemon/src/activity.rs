//! The being's activity indicator: what `/status`, `/health` and the dashboard call its
//! "metabolic state".
//!
//! dp, 2026-09-30 (SAGE #291): *"only actual state should be shown, and it should reflect what
//! the being is doing. the state display is an indicator not a control."*
//!
//! WHY THIS IS NOT THE METABOLIC CONTROLLER. The display used to read
//! `MetabolicController::current_state`, a free-running ATP oscillator the consciousness loop
//! ticks every 100 ms. It was ported from a design where a "cycle" was meaningful. At 0.1 s a
//! cycle, its hysteresis is 0.5 s, a dream lasts at most ~1.8 s and its circadian "day" is 10 s.
//! Sampled on CBP with no beat running, it showed 10 state changes in 10 s. The beat itself
//! runs in the Python gateway and never told the daemon anything. So the display was a clock,
//! and no real activity ever reached it.
//!
//! Now only a REPORT of real activity sets the indicator:
//!   * the heartbeat (`POST /activity`): wake at beat start and through explore/posture/account,
//!     wrap-up for reflect/answer, rest when the beat ends;
//!   * the consolidation unit (`POST /activity`, from its ExecStartPre/ExecStopPost): dream
//!     while `sage.memory.consolidation` runs, rest after;
//!   * the loop's own generation (a `/chat/raw` reply through the loop): wake while it
//!     generates. This is an overlay; when it ends, the display returns to whatever the
//!     reports say.
//!
//! A report that is not refreshed within its `ttl_secs` decays to rest. A beat killed by
//! SIGKILL, a crashed gateway, or a lost final report cannot leave the indicator stuck
//! saying the being is awake. The decay is applied when the indicator is READ, so it needs
//! no timer and cannot be skipped.
//!
//! Nothing reads this to decide anything. It is an indicator.

/// What the being is doing, as reported. `crisis` exists for a report of a real crisis; the
/// fake ATP never sets it, and today nothing does.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Activity {
    Wake,
    WrapUp,
    Dream,
    Rest,
    Crisis,
}

impl Activity {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Wake => "wake",
            Self::WrapUp => "wrap-up",
            Self::Dream => "dream",
            Self::Rest => "rest",
            Self::Crisis => "crisis",
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        match s.trim().to_ascii_lowercase().as_str() {
            "wake" => Some(Self::Wake),
            "wrap-up" | "wrap_up" | "wrapup" => Some(Self::WrapUp),
            "dream" => Some(Self::Dream),
            "rest" => Some(Self::Rest),
            "crisis" => Some(Self::Crisis),
            _ => None,
        }
    }
}

/// How long a non-rest report stands without a refresh when the reporter names no bound.
///
/// This is the beat's own maximum. `sage/gateway/systemd/sage-heartbeat.service.example` and
/// CBP's installed `sage-heartbeat.service` both set `TimeoutStartSec=1500`. After SIGTERM,
/// systemd allows the default `TimeoutStopSec` of 90 s for the beat to write its record
/// (heartbeat.py `BeatKilled`), and the rest report comes after that. A beat reports at every
/// phase boundary, so the longest a live beat can go between reports is the whole beat.
/// Reporters that know a different bound (consolidation: `TimeoutStartSec=600`) send
/// `ttl_secs`.
pub const DEFAULT_TTL_SECS: u64 = 1500 + 90;

/// No report may hold the indicator longer than a day, whatever `ttl_secs` it asks for.
pub const MAX_TTL_SECS: u64 = 24 * 3600;

#[derive(Debug, Clone)]
pub struct ActivityIndicator {
    reported: Activity,
    source: String,
    beat_id: Option<String>,
    /// When the displayed state began (moves only on a change of state).
    since: u64,
    /// When the last report arrived (every report moves it); staleness counts from here.
    last_refresh: u64,
    ttl_secs: u64,
    /// Generations in flight in the daemon's own loop, and when the first began.
    generating: u32,
    generating_since: u64,
    /// Beats counted from the heartbeat's reports (SAGE #295).
    beats: BeatCounts,
}

#[derive(Debug, Clone, Default)]
struct BeatCounts {
    completed: u64,
    unended: u64,
    current: Option<CurrentBeat>,
    last_ended_at: Option<u64>,
    last_ended_id: Option<String>,
}

#[derive(Debug, Clone)]
struct CurrentBeat {
    beat_id: String,
    phase: String,
    phase_reports: u32,
    started_at: u64,
    last_report_at: u64,
}

/// The real counts `/status` and the dashboard show in place of the loop's 100 ms ticks.
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct BeatsView {
    /// Beats that reported their end since the daemon started.
    pub completed: u64,
    /// Beats superseded by another beat's reports without reporting an end (killed, lost report).
    pub unended: u64,
    /// The beat running now, if its reports are current.
    pub current: Option<CurrentBeatView>,
    /// Unix seconds when the last beat reported its end, and how long ago.
    pub last_ended_at: Option<u64>,
    pub since_last_beat_end_secs: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct CurrentBeatView {
    pub beat_id: String,
    /// The phase it last reported: start, explore, posture, account, reflect, answer.
    pub phase: String,
    /// Phase reports received for this beat. Phases, not acts: the beat does not report its acts.
    pub phase_reports: u32,
    pub started_at: u64,
    pub age_secs: u64,
}

/// What a reader sees: the displayed state with its age and where it came from.
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct ActivityView {
    pub state: &'static str,
    /// Unix seconds when the displayed state began.
    pub since: u64,
    pub age_secs: u64,
    /// Who set it: "heartbeat:reflect", "consolidation", "daemon:generate", "startup", ...
    pub source: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub beat_id: Option<String>,
    /// True when a report went unrefreshed past its bound and the display fell back to rest.
    pub decayed: bool,
}

impl ActivityIndicator {
    /// At startup nothing has been reported, so the being is shown at rest, with the reason.
    pub fn new(now: u64) -> Self {
        Self {
            reported: Activity::Rest,
            source: "startup".to_string(),
            beat_id: None,
            since: now,
            last_refresh: now,
            ttl_secs: DEFAULT_TTL_SECS,
            generating: 0,
            generating_since: now,
            beats: BeatCounts::default(),
        }
    }

    /// A report of real activity. `since` moves only when the reported state changes. A beat
    /// that reports wake for explore and again for posture has been awake since explore. Every
    /// report refreshes the staleness clock.
    ///
    /// Only the reporter that set an activity can end it. A `rest` from a different reporter
    /// is not applied while that activity still stands. The reporter is the part of `source`
    /// before the first ':' ("heartbeat" in "heartbeat:end"). This matters when consolidation
    /// (04:30) finishes during a beat: its ExecStopPost `rest` must not show a beat that is
    /// still running as over. A non-rest report always applies, and the latest report wins:
    /// two things really are happening. Returns whether the report was applied.
    pub fn report(&mut self, state: Activity, source: &str, beat_id: Option<String>,
                  ttl_secs: Option<u64>, now: u64) -> bool {
        let owner = |s: &str| s.split(':').next().unwrap_or("").to_string();
        if state == Activity::Rest && self.reported != Activity::Rest && !self.is_stale(now)
            && owner(source) != owner(&self.source)
        {
            return false;
        }
        // A state that has already decayed is not "unchanged": the reader has been shown rest.
        let shown_changed = state != self.reported || self.is_stale(now);
        if shown_changed {
            self.since = now;
        }
        self.count_beat(source, beat_id.as_deref(), now);
        self.reported = state;
        self.source = source.to_string();
        self.beat_id = beat_id;
        self.ttl_secs = ttl_secs.unwrap_or(DEFAULT_TTL_SECS).clamp(1, MAX_TTL_SECS);
        self.last_refresh = now;
        true
    }

    /// Beat bookkeeping from the heartbeat's own reports (SAGE #295). A heartbeat report carries
    /// its `beat_id` and names its phase after the ':' ("heartbeat:explore"). A phase that starts
    /// with "end" ends the beat: "heartbeat:end" (rest) and "heartbeat:end:continuing" (wake,
    /// handing off to a next beat that is already armed). A report naming a different beat while
    /// one is current means the current one never reported its end (killed, or a lost report):
    /// it is counted as `unended`, not as completed. Counts start at daemon start.
    fn count_beat(&mut self, source: &str, beat_id: Option<&str>, now: u64) {
        let (Some((owner, phase)), Some(id)) = (source.split_once(':'), beat_id) else { return };
        if owner != "heartbeat" || id.is_empty() {
            return;
        }
        let b = &mut self.beats;
        if phase.starts_with("end") {
            let is_current = b.current.as_ref().is_some_and(|c| c.beat_id == id);
            if is_current || b.last_ended_id.as_deref() != Some(id) {
                b.completed += 1;
                b.last_ended_at = Some(now);
                b.last_ended_id = Some(id.to_string());
            }
            if is_current {
                b.current = None;
            }
            return;
        }
        match b.current.as_mut() {
            Some(c) if c.beat_id == id => {
                c.phase = phase.to_string();
                c.phase_reports += 1;
                c.last_report_at = now;
            }
            _ => {
                if b.current.is_some() {
                    b.unended += 1;
                }
                b.current = Some(CurrentBeat {
                    beat_id: id.to_string(),
                    phase: phase.to_string(),
                    phase_reports: 1,
                    started_at: now,
                    last_report_at: now,
                });
            }
        }
    }

    /// Beats as the reports tell them, at `now`. A current beat whose reports went stale past
    /// the report's bound is no longer shown as running (the display has decayed to rest).
    pub fn beats(&self, now: u64) -> BeatsView {
        let b = &self.beats;
        let current = b.current.as_ref().filter(|c| {
            now.saturating_sub(c.last_report_at) <= self.ttl_secs
        }).map(|c| CurrentBeatView {
            beat_id: c.beat_id.clone(),
            phase: c.phase.clone(),
            phase_reports: c.phase_reports,
            started_at: c.started_at,
            age_secs: now.saturating_sub(c.started_at),
        });
        BeatsView {
            completed: b.completed,
            unended: b.unended,
            current,
            last_ended_at: b.last_ended_at,
            since_last_beat_end_secs: b.last_ended_at.map(|t| now.saturating_sub(t)),
        }
    }

    /// The loop began generating a reply: the being is acting, whatever was last reported.
    pub fn begin_generation(&mut self, now: u64) {
        if self.generating == 0 {
            self.generating_since = now;
        }
        self.generating += 1;
    }

    pub fn end_generation(&mut self) {
        self.generating = self.generating.saturating_sub(1);
    }

    fn is_stale(&self, now: u64) -> bool {
        self.reported != Activity::Rest && now.saturating_sub(self.last_refresh) > self.ttl_secs
    }

    /// The displayed state at `now`. Pure: reading never changes the indicator.
    pub fn view(&self, now: u64) -> ActivityView {
        if self.generating > 0 {
            return ActivityView {
                state: Activity::Wake.as_str(),
                since: self.generating_since,
                age_secs: now.saturating_sub(self.generating_since),
                source: "daemon:generate".to_string(),
                beat_id: None,
                decayed: false,
            };
        }
        if self.is_stale(now) {
            let since = self.last_refresh.saturating_add(self.ttl_secs);
            return ActivityView {
                state: Activity::Rest.as_str(),
                since,
                age_secs: now.saturating_sub(since),
                source: format!("stale:{}", self.source),
                beat_id: self.beat_id.clone(),
                decayed: true,
            };
        }
        ActivityView {
            state: self.reported.as_str(),
            since: self.since,
            age_secs: now.saturating_sub(self.since),
            source: self.source.clone(),
            beat_id: self.beat_id.clone(),
            decayed: false,
        }
    }
}

pub type SharedActivity = std::sync::Arc<std::sync::Mutex<ActivityIndicator>>;

pub fn now_secs() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

/// Read the shared indicator. A poisoned lock still holds a valid indicator (every write is
/// a few field stores), so it is read rather than treated as "unknown".
pub fn read(cell: &SharedActivity, now: u64) -> ActivityView {
    match cell.lock() {
        Ok(g) => g.view(now),
        Err(p) => p.into_inner().view(now),
    }
}

/// Read the beat counts off the shared indicator (SAGE #295).
pub fn read_beats(cell: &SharedActivity, now: u64) -> BeatsView {
    match cell.lock() {
        Ok(g) => g.beats(now),
        Err(p) => p.into_inner().beats(now),
    }
}

/// Marks a generation for as long as it lives. Dropping it ends the generation even when
/// the generating code returns early or panics, so the display cannot be left at wake.
pub struct GenerationGuard {
    cell: Option<SharedActivity>,
}

impl GenerationGuard {
    pub fn begin(cell: Option<&SharedActivity>, now: u64) -> Self {
        if let Some(c) = cell {
            let mut g = c.lock().unwrap_or_else(|p| p.into_inner());
            g.begin_generation(now);
        }
        Self { cell: cell.cloned() }
    }
}

impl Drop for GenerationGuard {
    fn drop(&mut self) {
        if let Some(c) = self.cell.take() {
            let mut g = c.lock().unwrap_or_else(|p| p.into_inner());
            g.end_generation();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn at_startup_the_being_is_shown_at_rest_and_says_why() {
        let a = ActivityIndicator::new(1000);
        let v = a.view(1005);
        assert_eq!(v.state, "rest");
        assert_eq!(v.source, "startup");
        assert_eq!(v.age_secs, 5);
    }

    #[test]
    fn a_beat_reads_wake_then_wrap_up_then_rest() {
        let mut a = ActivityIndicator::new(0);
        a.report(Activity::Wake, "heartbeat:start", Some("hb-1".into()), None, 10);
        a.report(Activity::Wake, "heartbeat:explore", Some("hb-1".into()), None, 12);
        let v = a.view(20);
        assert_eq!((v.state, v.since), ("wake", 10), "wake since the beat began, not since the last report");
        assert_eq!(v.source, "heartbeat:explore");
        assert_eq!(v.beat_id.as_deref(), Some("hb-1"));

        a.report(Activity::WrapUp, "heartbeat:reflect", Some("hb-1".into()), None, 300);
        let v = a.view(301);
        assert_eq!((v.state, v.since), ("wrap-up", 300));

        a.report(Activity::Rest, "heartbeat:end", Some("hb-1".into()), None, 400);
        assert_eq!(a.view(100_000).state, "rest", "rest never decays");
        assert!(!a.view(100_000).decayed);
    }

    #[test]
    fn only_the_reporter_that_set_an_activity_can_end_it() {
        let mut a = ActivityIndicator::new(0);
        assert!(a.report(Activity::Wake, "heartbeat:explore", Some("hb-3".into()), None, 10));
        // consolidation finished while the beat was still running
        assert!(!a.report(Activity::Rest, "consolidation", None, None, 20));
        assert_eq!(a.view(21).state, "wake", "a finished consolidation does not end a running beat");
        assert!(a.report(Activity::Rest, "heartbeat:end", Some("hb-3".into()), None, 30));
        assert_eq!(a.view(31).state, "rest");

        // anyone may start something; the latest non-rest report wins
        assert!(a.report(Activity::Dream, "consolidation", None, Some(690), 40));
        assert!(a.report(Activity::Wake, "heartbeat:start", None, None, 41));
        assert_eq!(a.view(42).state, "wake");

        // a stale activity can be ended by anyone (it is already shown as rest)
        a.report(Activity::Dream, "consolidation", None, Some(5), 100);
        assert!(a.report(Activity::Rest, "heartbeat:end", None, None, 200));
    }

    #[test]
    fn wrap_up_is_its_own_name_not_focus() {
        assert_eq!(Activity::WrapUp.as_str(), "wrap-up");
        assert_eq!(Activity::parse("wrap-up"), Some(Activity::WrapUp));
        assert_eq!(Activity::parse("focus"), None, "focus was the oscillator's salience state; nothing reports it");
        assert_eq!(Activity::parse("  Dream "), Some(Activity::Dream));
        assert_eq!(Activity::parse("sleeping"), None);
    }

    #[test]
    fn an_unrefreshed_report_decays_to_rest_at_its_bound() {
        let mut a = ActivityIndicator::new(0);
        a.report(Activity::Wake, "heartbeat:explore", Some("hb-2".into()), None, 100);
        assert_eq!(a.view(100 + DEFAULT_TTL_SECS).state, "wake", "at the bound it still stands");
        let v = a.view(100 + DEFAULT_TTL_SECS + 1);
        assert_eq!(v.state, "rest", "a crashed beat cannot leave the being shown awake");
        assert!(v.decayed);
        assert_eq!(v.source, "stale:heartbeat:explore", "and the reader can see why");
        assert_eq!(v.since, 100 + DEFAULT_TTL_SECS);

        // a reporter's own bound wins
        a.report(Activity::Dream, "consolidation", None, Some(690), 10_000);
        assert_eq!(a.view(10_690).state, "dream");
        assert_eq!(a.view(10_691).state, "rest");

        // and no report can hold it forever
        a.report(Activity::Wake, "x", None, Some(u64::MAX), 20_000);
        assert_eq!(a.view(20_000 + MAX_TTL_SECS + 1).state, "rest");
    }

    #[test]
    fn a_refresh_keeps_it_standing_and_a_report_after_decay_starts_fresh() {
        let mut a = ActivityIndicator::new(0);
        a.report(Activity::Wake, "heartbeat:explore", None, Some(100), 0);
        a.report(Activity::Wake, "heartbeat:posture", None, Some(100), 90);
        assert_eq!(a.view(180).state, "wake", "refreshed at 90");
        assert_eq!(a.view(180).since, 0);
        // decayed at 191; a new wake report is a new wake, not a continuation of the old one
        a.report(Activity::Wake, "heartbeat:start", None, Some(100), 500);
        assert_eq!(a.view(501).since, 500);
    }

    #[test]
    fn the_loops_generation_shows_wake_and_returns_to_the_reported_state() {
        let cell: SharedActivity = std::sync::Arc::new(std::sync::Mutex::new(ActivityIndicator::new(0)));
        {
            let _g = GenerationGuard::begin(Some(&cell), 50);
            let v = read(&cell, 55);
            assert_eq!((v.state, v.source.as_str(), v.since), ("wake", "daemon:generate", 50));
        }
        assert_eq!(read(&cell, 60).state, "rest", "back to rest when nothing else was reported");

        cell.lock().unwrap().report(Activity::WrapUp, "heartbeat:reflect", None, None, 70);
        {
            let _g = GenerationGuard::begin(Some(&cell), 71);
            assert_eq!(read(&cell, 72).state, "wake");
        }
        assert_eq!(read(&cell, 73).state, "wrap-up", "back to what the beat reported, not to rest");
    }

    #[test]
    fn a_generation_that_panics_still_ends() {
        let cell: SharedActivity = std::sync::Arc::new(std::sync::Mutex::new(ActivityIndicator::new(0)));
        let c2 = cell.clone();
        let r = std::panic::catch_unwind(move || {
            let _g = GenerationGuard::begin(Some(&c2), 1);
            panic!("generation blew up");
        });
        assert!(r.is_err());
        assert_eq!(read(&cell, 2).state, "rest");
    }

    fn beat(a: &mut ActivityIndicator, id: &str, t: u64, end: &str) {
        let s = |p: &str| format!("heartbeat:{p}");
        a.report(Activity::Wake, &s("start"), Some(id.into()), None, t);
        a.report(Activity::Wake, &s("explore"), Some(id.into()), None, t + 1);
        a.report(Activity::WrapUp, &s("reflect"), Some(id.into()), None, t + 2);
        let st = if end == "end" { Activity::Rest } else { Activity::Wake };
        a.report(st, &s(end), Some(id.into()), Some(300), t + 3);
    }

    #[test]
    fn beats_are_counted_from_the_heartbeats_reports_not_from_ticks() {
        let mut a = ActivityIndicator::new(0);
        assert_eq!(a.beats(5).completed, 0);
        assert_eq!(a.beats(5).since_last_beat_end_secs, None);

        a.report(Activity::Wake, "heartbeat:start", Some("hb-1".into()), None, 10);
        a.report(Activity::Wake, "heartbeat:explore", Some("hb-1".into()), None, 11);
        let v = a.beats(12);
        let cur = v.current.expect("a beat is running");
        assert_eq!((cur.beat_id.as_str(), cur.phase.as_str(), cur.phase_reports, cur.started_at, cur.age_secs),
                   ("hb-1", "explore", 2, 10, 2));
        assert_eq!(v.completed, 0);

        a.report(Activity::Rest, "heartbeat:end", Some("hb-1".into()), None, 20);
        let v = a.beats(50);
        assert_eq!((v.completed, v.current, v.last_ended_at, v.since_last_beat_end_secs),
                   (1, None, Some(20), Some(30)));
        // a second rest for the same beat is not a second beat
        a.report(Activity::Rest, "heartbeat:end", Some("hb-1".into()), None, 21);
        assert_eq!(a.beats(50).completed, 1);
    }

    #[test]
    fn back_to_back_beats_each_count_and_the_handoff_ends_the_first() {
        let mut a = ActivityIndicator::new(0);
        beat(&mut a, "hb-1", 100, "end:continuing");
        assert_eq!(a.view(104).state, "wake", "the hand-off keeps the display at wake");
        beat(&mut a, "hb-2", 105, "end");
        let v = a.beats(200);
        assert_eq!((v.completed, v.unended, v.last_ended_at), (2, 0, Some(108)));
    }

    #[test]
    fn a_beat_that_never_reported_its_end_is_unended_not_completed() {
        let mut a = ActivityIndicator::new(0);
        a.report(Activity::Wake, "heartbeat:explore", Some("hb-killed".into()), None, 10);
        a.report(Activity::Wake, "heartbeat:start", Some("hb-next".into()), None, 2000);
        let v = a.beats(2001);
        assert_eq!((v.completed, v.unended), (0, 1));
        assert_eq!(v.current.unwrap().beat_id, "hb-next");
    }

    #[test]
    fn other_reporters_and_reports_without_a_beat_id_count_no_beats() {
        let mut a = ActivityIndicator::new(0);
        a.report(Activity::Dream, "consolidation", None, Some(690), 1);
        a.report(Activity::Rest, "consolidation", None, None, 2);
        a.report(Activity::Wake, "heartbeat:start", None, None, 3);
        let v = a.beats(4);
        assert_eq!((v.completed, v.current), (0, None));
    }

    #[test]
    fn a_beat_whose_reports_went_stale_is_not_shown_running() {
        let mut a = ActivityIndicator::new(0);
        a.report(Activity::Wake, "heartbeat:start", Some("hb-1".into()), Some(60), 10);
        assert!(a.beats(60).current.is_some());
        assert!(a.beats(71).current.is_none());
    }
}
