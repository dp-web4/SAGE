"""beat_health: every beat lands in exactly one class, and a mute beat alarms the beat it happens.

The case that motivated it is the first one: 163 beats whose every phase said "[OllamaIRP: Error: timed
out]" and whose record nothing read (11-02 → 11-09)."""
import json

from sage.gateway import beat_health as bh

TIMEOUT = "[OllamaIRP: Error: timed out]"


def act(effector, ok=True, refused=False):
    return {"effector": effector, "args": {}, "ok": ok, "refused": refused, "error": None if ok else "x"}


def beat(ts="2026-11-09T00:00:00Z", explore=None, reflect=None, **extra):
    rec = {"ts": ts, "explore": explore, "reflect": reflect, "answer": None}
    rec.update(extra)
    return rec


def phase(reply="", trace=(), **kw):
    return {"reply": reply, "steps": len(trace), "trace": list(trace), **kw}


def test_every_phase_timed_out_is_mute():
    r = bh.classify(beat(explore=phase(TIMEOUT), reflect=phase(TIMEOUT)))
    assert r["cls"] == "mute"
    assert r["errors"] == [f"explore: {TIMEOUT}", f"reflect: {TIMEOUT}"]


def test_unreachable_and_closed_connection_are_mute_too():
    for reply in ("[OllamaIRP: Ollama not reachable]", "[OllamaIRP: Error: Remote end closed connection]"):
        assert bh.classify(beat(explore=phase(reply)))["cls"] == "mute"


def test_a_model_error_after_real_work_is_not_mute_but_is_flagged():
    r = bh.classify(beat(explore=phase("", [act("memory_write")]), reflect=phase(TIMEOUT)))
    assert r["cls"] == "worked"
    assert "model_error" in r["flags"]


def test_an_effecting_act_makes_a_worked_beat():
    for eff in ("memory_write", "run", "game", "settle", "say"):
        assert bh.classify(beat(explore=phase("", [act("memory_read"), act(eff)])))["cls"] == "worked", eff


def test_reads_alone_are_read_only():
    r = bh.classify(beat(explore=phase("", [act("memory_read"), act("search")])))
    assert r["cls"] == "read-only"
    assert r["acts"]["reads"] == 2


def test_stay_awake_alone_does_not_make_a_beat_worked():
    assert bh.classify(beat(explore=phase("", [act("stay_awake")])))["cls"] == "read-only"


def test_three_failures_and_nothing_effected_is_stuck():
    trace = [act("run", ok=False), act("memory_write", ok=False, refused=True), act("run", ok=False),
             act("memory_read")]
    r = bh.classify(beat(explore=phase("", trace)))
    assert r["cls"] == "stuck"
    assert r["acts"] == {"ok": 1, "failed": 2, "refused": 1, "effected": 0, "reads": 1}


def test_failures_do_not_make_stuck_when_something_was_effected():
    trace = [act("run", ok=False)] * 5 + [act("memory_write")]
    assert bh.classify(beat(explore=phase("", trace)))["cls"] == "worked"


def test_a_few_failures_and_nothing_else_is_idle_flagged():
    r = bh.classify(beat(explore=phase("", [act("run", ok=False)])))
    assert r["cls"] == "idle"
    assert "failed_acts" in r["flags"]


def test_no_acts_and_an_answer_is_idle():
    assert bh.classify(beat(explore=phase("I'll rest.", rested=True)))["cls"] == "idle"


def test_the_harness_loop_guard_wins_over_work():
    r = bh.classify(beat(explore=phase("", [act("memory_write")], looped={"effector": "search"})))
    assert r["cls"] == "looped"


def test_mute_wins_over_looped():
    assert bh.classify(beat(explore=phase(TIMEOUT, looped=True)))["cls"] == "mute"


def test_one_mute_beat_alarms():
    s = bh.summary([beat(explore=phase("", [act("run")])), beat(ts="t2", explore=phase(TIMEOUT))])
    assert s["streak"] == {"cls": "mute", "n": 1}
    assert s["alarm"] and s["alarm"].startswith("1 mute")


def test_stuck_alarms_only_on_a_streak_of_three():
    stuck = phase("", [act("run", ok=False)] * 3)
    assert bh.summary([beat(explore=stuck)] * 2)["alarm"] is None
    assert bh.summary([beat(explore=stuck)] * 3)["alarm"].startswith("3 stuck")


def test_a_worked_beat_after_mute_clears_the_alarm():
    beats = [beat(explore=phase(TIMEOUT))] * 5 + [beat(explore=phase("", [act("memory_write")]))]
    assert bh.summary(beats)["alarm"] is None


def test_outages_finds_each_maximal_mute_run():
    w = beat(explore=phase("", [act("run")]))
    m = lambda ts: beat(ts=ts, explore=phase(TIMEOUT))  # noqa: E731
    runs = bh.outages([w, m("a"), m("b"), w, m("c"), w])
    assert runs == [{"start": "a", "end": "b", "n": 2}, {"start": "c", "end": "c", "n": 1}]


def test_check_exits_3_on_alarm_and_0_when_healthy(tmp_path, capsys):
    path = tmp_path / "heartbeats.jsonl"
    path.write_text(json.dumps(beat(explore=phase(TIMEOUT))) + "\n")
    assert bh.main(["--instance", str(tmp_path), "--check"]) == 3
    assert "ALARM: 1 mute" in capsys.readouterr().out
    path.write_text(json.dumps(beat(explore=phase("", [act("memory_write")]))) + "\n")
    assert bh.main(["--instance", str(tmp_path), "--check"]) == 0


def test_a_torn_last_line_is_skipped_not_fatal(tmp_path):
    (tmp_path / "heartbeats.jsonl").write_text(json.dumps(beat(explore=phase(TIMEOUT))) + "\n{\"ts\": \"2026-")
    assert [r["cls"] for r in bh.summary(bh.read_beats(tmp_path))["rows"]] == ["mute"]


def test_no_record_is_no_alarm(tmp_path):
    s = bh.summary(bh.read_beats(tmp_path))
    assert s["beats"] == 0 and s["alarm"] is None
