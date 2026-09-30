"""Presence reads neither the state display nor the internal ATP as depletion (SAGE #291).

dp, 2026-09-30: "the state display is an indicator not a control." After #291 the daemon's
`metabolic_state` says what the being is doing, and "rest" means no beat is running, which is
most of the day. Read as depletion, it would pin presence at the 0.70 bar permanently. The
`atp_percentage` beside it is the daemon's internal oscillator, ticked every 100 ms; nothing the
being does moves it, so `atp < 25` raised the bar on a clock unrelated to the being.
"""
import urllib.request

from sage.embodiment import presence as P


def _presence(monkeypatch):
    monkeypatch.setattr(P.Presence, "_heard_size", staticmethod(lambda: 0))
    return P.Presence()


def test_a_being_between_beats_is_not_treated_as_depleted(monkeypatch):
    sal = {"salience": 0.5}   # above WAKE_TH (0.45), below WAKE_TH_REST (0.70)
    p = _presence(monkeypatch)
    wake, resting = p._should_wake(sal, "open", "someone walked in", now=10_000.0)
    assert wake is True, "a moderate moment wakes an open-eyed being"
    assert resting is False


def test_the_daemon_is_not_consulted_to_decide_a_wake(monkeypatch):
    """Whatever /status says (state `rest`, ATP 3%), it is not read: the decision is made from
    the moment, the being's gaze, and presence's own rate limits."""
    def refuse(*a, **k):
        raise AssertionError("presence read the daemon to decide a wake")
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    p = _presence(monkeypatch)
    wake, _ = p._should_wake({"salience": 0.5}, "open", "someone walked in", now=10_000.0)
    assert wake is True
    assert not hasattr(P, "LOW_ATP") and not hasattr(p, "_read_energy"), "no energy gate remains"


def test_a_conflict_still_wakes_an_engaged_being(monkeypatch):
    p = _presence(monkeypatch)
    wake, _ = p._should_wake({"salience": 0.1, "conflict": 1}, "open", "the cup moved", now=10_000.0)
    assert wake is True, "the reafference path no longer depends on ATP"


def test_the_beings_own_closed_eyes_still_raise_the_bar(monkeypatch):
    p = _presence(monkeypatch)
    wake, resting = p._should_wake({"salience": 0.5}, "closed", "someone walked in", now=10_000.0)
    assert (wake, resting) == (False, True), "gaze is the being's own act, not the indicator"
