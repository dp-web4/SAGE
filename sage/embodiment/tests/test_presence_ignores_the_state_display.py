"""Presence does not read the state display as depletion (SAGE #291).

dp, 2026-09-30: "the state display is an indicator not a control." After #291 the daemon's
`metabolic_state` says what the being is doing, and "rest" means no beat is running, which is
most of the day. Read as depletion, it would pin presence at the 0.70 bar permanently.
"""
from sage.embodiment import presence as P


def _presence(monkeypatch, atp, mstate):
    monkeypatch.setattr(P.Presence, "_heard_size", staticmethod(lambda: 0))
    p = P.Presence()
    monkeypatch.setattr(p, "_read_energy", lambda now: (atp, mstate))
    return p


def test_a_being_between_beats_is_not_treated_as_depleted(monkeypatch):
    sal = {"salience": 0.5}   # above WAKE_TH (0.45), below WAKE_TH_REST (0.70)
    for mstate in ("rest", "dream", "wake", "wrap-up"):
        p = _presence(monkeypatch, 100.0, mstate)
        wake, resting = p._should_wake(sal, "open", "someone walked in", now=10_000.0)
        assert wake is True, f"shown state {mstate!r} raised the bar"
        assert resting is False


def test_the_beings_own_closed_eyes_still_raise_the_bar(monkeypatch):
    p = _presence(monkeypatch, 100.0, "wake")
    wake, resting = p._should_wake({"salience": 0.5}, "closed", "someone walked in", now=10_000.0)
    assert (wake, resting) == (False, True), "gaze is the being's own act, not the indicator"
