use super::circadian::CircadianClock;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum MetabolicState {
    Wake,
    Focus,
    Rest,
    Dream,
    Crisis,
}

impl MetabolicState {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Wake => "wake",
            Self::Focus => "focus",
            Self::Rest => "rest",
            Self::Dream => "dream",
            Self::Crisis => "crisis",
        }
    }
}

#[derive(Debug, Clone)]
pub struct StateConfig {
    pub atp_consumption_rate: f64,
    pub atp_recovery_rate: f64,
    pub max_active_plugins: u32,
    pub sensor_poll_rate: f64,
    pub learning_enabled: bool,
    pub consolidation_enabled: bool,
}

fn default_config(state: MetabolicState) -> StateConfig {
    match state {
        MetabolicState::Wake => StateConfig {
            atp_consumption_rate: 0.5,
            atp_recovery_rate: 0.1,
            max_active_plugins: 3,
            sensor_poll_rate: 30.0,
            learning_enabled: true,
            consolidation_enabled: false,
        },
        MetabolicState::Focus => StateConfig {
            atp_consumption_rate: 0.8,
            atp_recovery_rate: 0.3,
            max_active_plugins: 1,
            sensor_poll_rate: 60.0,
            learning_enabled: true,
            consolidation_enabled: false,
        },
        MetabolicState::Rest => StateConfig {
            atp_consumption_rate: 0.1,
            atp_recovery_rate: 1.0,
            max_active_plugins: 1,
            sensor_poll_rate: 1.0,
            learning_enabled: false,
            consolidation_enabled: false,
        },
        MetabolicState::Dream => StateConfig {
            atp_consumption_rate: 0.3,
            atp_recovery_rate: 0.5,
            max_active_plugins: 0,
            sensor_poll_rate: 0.1,
            learning_enabled: false,
            consolidation_enabled: true,
        },
        MetabolicState::Crisis => StateConfig {
            atp_consumption_rate: 0.05,
            atp_recovery_rate: 0.8,
            max_active_plugins: 1,
            sensor_poll_rate: 5.0,
            learning_enabled: false,
            consolidation_enabled: false,
        },
    }
}

pub struct CycleData {
    pub atp_consumed: f64,
    pub attention_load: u32,
    pub max_salience: f64,
    pub crisis_detected: bool,
}

impl Default for CycleData {
    fn default() -> Self {
        Self {
            atp_consumed: 0.0,
            attention_load: 0,
            max_salience: 0.0,
            crisis_detected: false,
        }
    }
}

pub struct TransitionRecord {
    pub from: MetabolicState,
    pub to: MetabolicState,
    pub atp_at_transition: f64,
    pub cycles_in_old_state: u64,
}

/// How many transitions `history` keeps. The daemon ticks this controller every 100 ms for
/// the life of the process, and it transitions about once a second. An unbounded `history`
/// was a slow leak (~180k records after 2.5 days on CBP, SAGE #291). `transitions_total`
/// still counts all of them.
pub const HISTORY_CAP: usize = 1024;

pub struct MetabolicController {
    pub current_state: MetabolicState,
    pub atp_current: f64,
    pub atp_max: f64,
    pub total_cycles: u64,

    state_entry_cycle: u64,
    cycles_in_state: u64,
    min_cycles_in_state: u64,

    circadian: Option<CircadianClock>,
    /// The most recent `HISTORY_CAP` transitions.
    pub history: Vec<TransitionRecord>,
    /// Every transition since construction, including the ones `history` has let go.
    pub transitions_total: u64,
}

impl MetabolicController {
    pub fn new(initial_atp: f64, max_atp: f64, circadian_period: Option<u64>) -> Self {
        Self {
            current_state: MetabolicState::Wake,
            atp_current: initial_atp,
            atp_max: max_atp,
            total_cycles: 0,
            state_entry_cycle: 0,
            cycles_in_state: 0,
            min_cycles_in_state: 5,
            circadian: circadian_period.map(CircadianClock::day_night),
            history: Vec::new(),
            transitions_total: 0,
        }
    }

    pub fn with_defaults() -> Self {
        Self::new(100.0, 100.0, Some(100))
    }

    pub fn config(&self) -> StateConfig {
        default_config(self.current_state)
    }

    pub fn update(&mut self, data: &CycleData) -> MetabolicState {
        self.total_cycles += 1;

        let cfg = self.config();
        self.atp_current -= data.atp_consumed;
        self.atp_current -= cfg.atp_consumption_rate;
        self.atp_current += cfg.atp_recovery_rate;
        self.atp_current = self.atp_current.clamp(0.0, self.atp_max);

        let next = self.determine_next_state(data);
        if next != self.current_state {
            self.transition_to(next);
        }

        self.current_state
    }

    fn time_in_state(&self) -> f64 {
        (self.total_cycles - self.state_entry_cycle) as f64
    }

    fn determine_next_state(&mut self, data: &CycleData) -> MetabolicState {
        let (wake_bias, focus_bias, dream_bias) = if let Some(ref mut clock) = self.circadian {
            clock.tick();
            (
                clock.get_metabolic_bias("wake"),
                clock.get_metabolic_bias("focus"),
                clock.get_metabolic_bias("dream"),
            )
        } else {
            (1.0, 1.0, 1.0)
        };

        self.cycles_in_state += 1;

        // Crisis overrides everything
        if data.crisis_detected || self.atp_current < 10.0 {
            return MetabolicState::Crisis;
        }

        // Hysteresis
        if self.cycles_in_state < self.min_cycles_in_state {
            return self.current_state;
        }

        let tis = self.time_in_state();

        match self.current_state {
            MetabolicState::Wake => {
                let focus_threshold = 50.0 / focus_bias;
                if data.max_salience > 0.45 && self.atp_current > focus_threshold {
                    return MetabolicState::Focus;
                }
                let rest_threshold = 30.0 * wake_bias;
                if self.atp_current < rest_threshold {
                    return MetabolicState::Rest;
                }
                let dream_time = (30.0 / dream_bias).max(5.0);
                if self.atp_current > 40.0 && self.atp_current < 80.0 && tis > dream_time {
                    return MetabolicState::Dream;
                }
                MetabolicState::Wake
            }
            MetabolicState::Focus => {
                if data.max_salience < 0.35 || self.atp_current < 20.0 {
                    return MetabolicState::Wake;
                }
                if self.atp_current < 15.0 {
                    return MetabolicState::Rest;
                }
                MetabolicState::Focus
            }
            MetabolicState::Rest => {
                let wake_threshold = 50.0 * wake_bias;
                if self.atp_current > wake_threshold {
                    return MetabolicState::Wake;
                }
                let dream_atp = 40.0 / dream_bias;
                let dream_time = (6.0 / dream_bias).max(5.0);
                if self.atp_current > dream_atp && tis > dream_time {
                    return MetabolicState::Dream;
                }
                MetabolicState::Rest
            }
            MetabolicState::Dream => {
                let wake_threshold = 70.0 * wake_bias;
                let max_dream = 18.0 / dream_bias;
                if self.atp_current > wake_threshold || tis > max_dream {
                    return MetabolicState::Wake;
                }
                if self.atp_current < 40.0 {
                    return MetabolicState::Rest;
                }
                MetabolicState::Dream
            }
            MetabolicState::Crisis => {
                if self.atp_current > 15.0 && !data.crisis_detected {
                    return MetabolicState::Rest;
                }
                MetabolicState::Crisis
            }
        }
    }

    fn transition_to(&mut self, new_state: MetabolicState) {
        self.history.push(TransitionRecord {
            from: self.current_state,
            to: new_state,
            atp_at_transition: self.atp_current,
            cycles_in_old_state: self.cycles_in_state,
        });
        self.transitions_total += 1;
        if self.history.len() > HISTORY_CAP {
            let excess = self.history.len() - HISTORY_CAP;
            self.history.drain(..excess);
        }

        self.current_state = new_state;
        self.state_entry_cycle = self.total_cycles;
        self.cycles_in_state = 0;
    }

    pub fn force_state(&mut self, state: MetabolicState) {
        if state != self.current_state {
            self.transition_to(state);
        }
    }

    pub fn should_learn(&self) -> bool {
        self.config().learning_enabled
    }

    pub fn should_consolidate(&self) -> bool {
        let cfg_allows = self.config().consolidation_enabled;
        if let Some(ref clock) = self.circadian {
            cfg_allows && clock.should_consolidate_memory()
        } else {
            cfg_allows
        }
    }

    pub fn atp_percentage(&self) -> f64 {
        (self.atp_current / self.atp_max) * 100.0
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn idle_cycle() -> CycleData {
        CycleData::default()
    }

    fn salient_cycle(salience: f64) -> CycleData {
        CycleData { max_salience: salience, ..Default::default() }
    }

    fn crisis_cycle() -> CycleData {
        CycleData { crisis_detected: true, ..Default::default() }
    }

    #[test]
    fn history_is_bounded_but_every_transition_is_counted() {
        let mut ctrl = MetabolicController::with_defaults();
        for _ in 0..200_000 {
            ctrl.update(&idle_cycle());
        }
        assert!(ctrl.transitions_total as usize > HISTORY_CAP,
                "the oscillator transitioned {} times", ctrl.transitions_total);
        assert!(ctrl.history.len() <= HISTORY_CAP);
    }

    #[test]
    fn starts_in_wake() {
        let ctrl = MetabolicController::with_defaults();
        assert_eq!(ctrl.current_state, MetabolicState::Wake);
        assert_eq!(ctrl.atp_current, 100.0);
    }

    #[test]
    fn high_salience_triggers_focus() {
        let mut ctrl = MetabolicController::with_defaults();
        for _ in 0..10 {
            ctrl.update(&salient_cycle(0.8));
        }
        assert_eq!(ctrl.current_state, MetabolicState::Focus);
    }

    #[test]
    fn crisis_overrides_everything() {
        let mut ctrl = MetabolicController::with_defaults();
        ctrl.update(&crisis_cycle());
        assert_eq!(ctrl.current_state, MetabolicState::Crisis);
    }

    #[test]
    fn low_atp_triggers_crisis() {
        let mut ctrl = MetabolicController::new(5.0, 100.0, None);
        ctrl.update(&idle_cycle());
        assert_eq!(ctrl.current_state, MetabolicState::Crisis);
    }

    #[test]
    fn crisis_recovery_to_rest() {
        let mut ctrl = MetabolicController::new(5.0, 100.0, None);
        // Enter crisis
        ctrl.update(&idle_cycle());
        assert_eq!(ctrl.current_state, MetabolicState::Crisis);

        // Crisis config: consumption=0.05, recovery=0.8 → net +0.75/cycle
        // Need ATP > 15 to exit → about 14 cycles from ATP=5
        for _ in 0..20 {
            ctrl.update(&idle_cycle());
        }
        assert_eq!(ctrl.current_state, MetabolicState::Rest);
    }

    #[test]
    fn simulation_1000_cycles() {
        let mut ctrl = MetabolicController::with_defaults();
        let mut state_counts = std::collections::HashMap::new();

        for i in 0..1000 {
            let salience = if (i % 100) < 20 { 0.6 } else { 0.2 };
            let data = CycleData {
                max_salience: salience,
                ..Default::default()
            };
            let state = ctrl.update(&data);
            *state_counts.entry(state).or_insert(0u32) += 1;
        }

        // Should visit multiple states
        assert!(state_counts.len() >= 2, "only visited {:?}", state_counts);
        assert!(ctrl.total_cycles == 1000);
        assert!(ctrl.atp_current > 0.0);
        assert!(ctrl.atp_current <= ctrl.atp_max);
    }

    #[test]
    fn dream_entry_possible() {
        // No circadian → dream entry requires ATP in [40,80] and time_in_state > 30
        let mut ctrl = MetabolicController::new(60.0, 100.0, None);
        // Run enough idle cycles to cross threshold
        for _ in 0..50 {
            ctrl.update(&idle_cycle());
        }
        let visited_dream = ctrl.history.iter().any(|t| t.to == MetabolicState::Dream);
        // With ATP starting at 60, net change per cycle = -0.5 + 0.1 = -0.4
        // After ~50 cycles ATP ≈ 60 - 20 = 40, still in [40,80] range
        // time_in_state > 30 after cycle 30 → should enter dream
        assert!(visited_dream, "never entered dream state");
    }

    #[test]
    fn hysteresis_prevents_rapid_oscillation() {
        let mut ctrl = MetabolicController::with_defaults();
        // Feed alternating high/low salience — hysteresis should prevent thrashing
        let transitions_before = ctrl.history.len();
        for i in 0..20 {
            let salience = if i % 2 == 0 { 0.8 } else { 0.1 };
            ctrl.update(&salient_cycle(salience));
        }
        // With min_cycles_in_state=5, max transitions ≈ 4 (not 10)
        let transitions = ctrl.history.len() - transitions_before;
        assert!(transitions < 6, "too many transitions: {transitions}");
    }
}
