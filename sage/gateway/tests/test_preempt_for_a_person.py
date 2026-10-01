"""The awareness loop as an RTOS, R1 + R2 (2026-10-01): priority classes on wake events, and a beat that
yields to a person who speaks after it began.

dp, after a spoken question never reached the being: "our awareness loop still needs work. it should be
like a RTOS." A reply to a person was the LAST phase of a full beat, and a person arriving mid-beat waited
for that beat to end and most of the next (voice median 4.6 min on 2026-09-30)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import heartbeat as hb  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.being_tool_loop import run_tool_turn  # noqa: E402
from sage.gateway.tests.test_being_tool_loop import OK_DISPATCH, _client, _scripted  # noqa: E402


def test_event_classes():
    assert hb.event_class({"kind": "heard", "key": "heard:1:hi"}) == "P0"
    assert hb.event_class({"kind": "dp_turn"}) == "P0"
    assert hb.event_class({"kind": "x", "key": "turn:dp:88"}) == "P0"
    assert hb.event_class({"kind": "sense"}) == "P3"
    assert hb.event_class({"kind": "stay_awake"}) == "P4"


def test_only_a_person_after_the_beat_began_counts():
    t0 = 1000.0
    pending = [{"kind": "heard", "first_ts": 999.0, "descriptor": "before"},
               {"kind": "sense", "first_ts": 1005.0, "descriptor": "motion"},
               {"kind": "heard", "first_ts": 1006.0, "descriptor": 'heard a voice: "what do you want to remember?"'}]
    got = hb.p0_since(t0, pending)
    assert [e["descriptor"] for e in got] == ['heard a voice: "what do you want to remember?"']


def test_a_turn_yields_before_its_next_generate_and_keeps_what_it_did():
    gen, calls = _scripted(
        {"content": "looking", "intents": [BeingIntent("witness", {"event": "x"})]},
        {"content": "more", "intents": [BeingIntent("witness", {"event": "y"})]},
    )
    asks = iter([None, 'heard a voice: "hi"'])
    r = run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "hi"}], max_steps=4,
                      should_yield=lambda: next(asks, None))
    assert r.yielded == 'heard a voice: "hi"'
    assert len(calls["seen"]) == 1, "no generate after the yield"
    assert r.steps == 1 and len(r.trace) == 1 and r.trace[0][1].ok, "the executed act is kept"


def test_no_yield_without_a_reason_and_a_broken_check_never_yields():
    gen, _ = _scripted({"content": "done", "intents": []})
    assert run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "x"}],
                         should_yield=lambda: None).yielded is None

    def boom():
        raise OSError("pending set unreadable")
    gen, _ = _scripted({"content": "done", "intents": []})
    assert run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "x"}],
                         should_yield=boom).reply == "done"


def test_preemption_is_opt_in(tmp_path):
    assert hb.preempt_on(tmp_path) is False
    (tmp_path / "instance.json").write_text('{"preempt": true}')
    assert hb.preempt_on(tmp_path) is True


def test_the_beat_wires_the_yield_and_the_preempted_branch():
    src = Path(hb.__file__).read_text()
    assert src.count("should_yield=_yield_for_a_person") == 3, "explore, posture and reflection"
    # GPT on #310: the clock starts before the first claim, and every generate boundary is rechecked
    assert src.index("_beat_started = time.time()") < src.index("_claimed = _arousal_claim.claim_pending(")
    assert "p0_since(_beat_started)" in src and "p0_since(t0)" not in src
    i_acc = src.index("aresp = llm.get_chat_response(ask_msgs)")
    assert i_acc < src.index('_check_preempt("account")') < src.index('_check_preempt("reflect")')
    assert src.count("= _take_late()") == 2 and "(preempted or not _said_in(reflect))" in src
    assert 'claim_pending(f"{host_session_id}.preempt")' in src
    assert 'release_claim(f"{host_session_id}.preempt")' in src
    assert '"preempted": preempted,' in src and 'woke["classes"]' in src
