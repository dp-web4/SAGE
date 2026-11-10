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


def _write(tmp_path, recs, trailing="\n"):
    (tmp_path / "heartbeats.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + trailing)


def test_reverse_reader_matches_a_forward_read_across_block_edges(tmp_path):
    recs = [beat(ts=f"t{i:03d}", explore=phase("x" * (i * 7 % 50), [act("run")])) for i in range(60)]
    _write(tmp_path, recs)
    for block in (16, 97, 1 << 20):
        got = list(bh.iter_beats_newest_first(tmp_path, block=block))
        assert [r["ts"] for r in got] == [r["ts"] for r in reversed(recs)], block
    assert [r["ts"] for r in bh.read_beats(tmp_path, 3)] == ["t057", "t058", "t059"]


def test_mute_run_counts_back_to_the_last_beat_that_reached_the_model(tmp_path):
    w = beat(ts="w", explore=phase("", [act("run")]))
    _write(tmp_path, [w] + [beat(ts=f"m{i}", explore=phase(TIMEOUT)) for i in range(30)])
    assert bh.mute_run(tmp_path) == {"n": 30, "first": "m0", "last": "m29", "error": TIMEOUT, "ongoing": True}


def test_the_being_is_told_its_mute_beats_never_happened(tmp_path):
    w = beat(ts="2026-11-02T10:00:00Z", explore=phase("", [act("memory_write")]))
    mute = [beat(ts=f"2026-11-0{d}T00:00:00Z", explore=phase(TIMEOUT)) for d in range(3, 9)]
    _write(tmp_path, [w] + mute)
    text = bh.render_for_being(tmp_path)
    assert text.startswith("## Your last beats")
    assert "WMMMMMM" in text
    assert "6 of your beats, from 2026-11-03T00:00:00Z to 2026-11-08T00:00:00Z, never reached your model" in text
    assert "timed out" in text and "nothing you planned for those beats happened" in text


def test_a_healthy_record_shows_the_strip_and_no_outage(tmp_path):
    _write(tmp_path, [beat(explore=phase("", [act("memory_write")]))] * 3)
    text = bh.render_for_being(tmp_path)
    assert "WWW" in text and "never reached your model" not in text


def test_no_record_renders_nothing(tmp_path):
    assert bh.render_for_being(tmp_path) == ""


def test_param_is_operator_only_and_off_by_default(tmp_path):
    from sage.gateway import being_params
    p = being_params.PARAMS["beat_health"]
    assert p.default is False and p.self_tunable is False
    assert being_params.value(tmp_path, "beat_health", False) is False


def test_own_state_shows_the_block_only_when_the_operator_turns_it_on(tmp_path):
    from sage.gateway import heartbeat
    _write(tmp_path, [beat(explore=phase(TIMEOUT))])
    assert "## Your last beats" not in heartbeat.own_state(tmp_path)
    (tmp_path / "instance.json").write_text(json.dumps({"params": {"beat_health": True}}))
    state = heartbeat.own_state(tmp_path)
    assert "## Your last beats" in state and "never reached your model" in state


def test_an_outage_that_has_ended_is_still_explained_while_it_is_in_view(tmp_path):
    """The first beat after the repair finishes before the being reads the block, so the newest beat is
    worked — the outage just behind it must still be named, whole, not only the part inside the strip."""
    w = lambda ts: beat(ts=ts, explore=phase("", [act("memory_write")]))  # noqa: E731
    mute = [beat(ts=f"m{i:03d}", explore=phase(TIMEOUT)) for i in range(40)]
    _write(tmp_path, [w("before")] + mute + [w("after1"), w("after2")])
    text = bh.render_for_being(tmp_path)
    assert "MMMMMMMMMMWW" in text
    assert "40 of your beats, from m000 to m039, never reached your model" in text
    run = bh.mute_run(tmp_path, within=12)
    assert run["n"] == 40 and run["ongoing"] is False


def test_an_outage_older_than_the_strip_is_not_raised_again(tmp_path):
    w = lambda ts: beat(ts=ts, explore=phase("", [act("memory_write")]))  # noqa: E731
    _write(tmp_path, [beat(ts="old", explore=phase(TIMEOUT))] + [w(f"w{i}") for i in range(12)])
    assert bh.mute_run(tmp_path, within=12) is None
    assert "never reached your model" not in bh.render_for_being(tmp_path)
    assert bh.mute_run(tmp_path)["first"] == "old"
