"""R3: a beat WOKEN by a person answers first (opt-in), through heartbeat.main.

Measured on Sprout 2026-10-02..06 (embodied-RTOS arc, Track E baseline): a person who spoke while a beat
ran was answered in p50 36 s via R2 preemption, but a person whose turn woke an idle being waited
199-225 s, because the waking event is claimed at the start and R2 only sees later arrivals. The beat ran
explore, posture, account and reflect, and answered last."""
import json
import os
import sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv, heartbeat as hb  # noqa: E402
from sage.gateway.being_gate_client import ResultEnvelope  # noqa: E402
from sage.gateway.being_tool_loop import ToolTurnResult  # noqa: E402

DP_WAKE = {"kind": "dp_turn", "key": "dp_turn:dp spoke in conversation 'dp'",
           "descriptor": "dp spoke in conversation 'dp'", "first_ts": 1.0, "salience": 0.9}


class _Disp:
    endpoint = membot_endpoint = "http://127.0.0.1:9/mcp"

    def drain_inbox(self, peek=False):
        return ResultEnvelope(ok=True, result={"notices": []})


@pytest.fixture
def beat(tmp_path, monkeypatch):
    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / "identity.json").write_text(json.dumps({"identity": {"name": "t", "machine": "testbox"}}))
    conv.create(inst, "dp", title="dp", participants=["dp", "test-being"], writable_by=["dp", "test-being"])
    # seq comes from the store: it is not 1 when another test in this process appended first
    woke_seq = conv.append(inst, "dp", speaker="dp", text="i was asleep, now i'm back. how are you feeling?")["seq"]
    forum = tmp_path / "forum"
    forum.mkdir()
    from sage.gateway import governed_turn, being_tool_loop, egress_drain, arousal
    llm = NS(num_ctx=32768, get_chat_response=lambda msgs: {"content": "", "raw": {}})
    monkeypatch.setattr(governed_turn, "build_client", lambda *a, **k: (NS(_dispatcher=_Disp()), llm))
    calls = []

    def fake_turn(client, llm_, messages, *a, **kw):
        calls.append(str((messages[-1] or {}).get("content") or "")[:200])
        return ToolTurnResult(reply="I'm here, and glad you are back.", trace=[], steps=1)
    monkeypatch.setattr(being_tool_loop, "run_ollama_tool_turn", fake_turn)
    monkeypatch.setattr(hb, "fleet_digest", lambda *a, **k: "(no digest)")
    monkeypatch.setattr(egress_drain, "drain_once", lambda **k: {"drained": 0})
    monkeypatch.setattr(arousal, "claim_pending", lambda *a, **k: [dict(DP_WAKE)])
    monkeypatch.setattr(arousal, "peek_pending", lambda *a, **k: [])

    def run(**cfg):
        (inst / "instance.json").write_text(json.dumps({"machine": "testbox", **cfg}))
        calls.clear()
        rc = hb.main(["--member", "test-being", "--model", "qwen3.8-distill:4b", "--instance", str(inst),
                      "--forum-dir", str(forum), "--repos", "", "--no-hub-drain", "--no-escalate"])
        assert rc == 0
        return json.loads((inst / "heartbeats.jsonl").read_text().strip().splitlines()[-1]), list(calls)
    run.woke_turn = f"dp:{woke_seq}"
    return run


def test_a_beat_woken_by_a_person_answers_first(beat):
    rec, calls = beat(preempt=True, answer_woke=True, answer_first_on_person_wake=True)
    assert rec["preempted"]["phase"] == "start" and rec["preempted"]["woke"] is True, rec["preempted"]
    assert rec["explore"] is None, "explore never ran"
    assert rec["selected"] == {"turn": beat.woke_turn, "expects_reply": True, "woke": True}, rec["selected"]
    assert rec["preempted"]["selected"] == beat.woke_turn
    assert (rec.get("account") or {}).get("skipped"), "the account waits for the next beat"
    assert rec.get("answer") is not None, "the answer turn ran"
    assert len(calls) == 1, f"only the answer turn generated: {calls}"


def test_without_the_flag_the_full_beat_runs_as_before(beat):
    rec, calls = beat(preempt=True, answer_woke=True)
    assert not rec.get("preempted"), rec.get("preempted")
    assert rec["explore"] is not None, "explore ran"
    assert len(calls) >= 2, calls


def test_r3_needs_preemption_on(beat):
    rec, _ = beat(answer_woke=True, answer_first_on_person_wake=True)
    assert not rec.get("preempted") and rec["explore"] is not None


def test_a_sense_wake_is_not_a_person(beat, monkeypatch):
    from sage.gateway import arousal
    monkeypatch.setattr(arousal, "claim_pending", lambda *a, **k: [
        {"kind": "sense", "key": "sense:x", "descriptor": "motion", "first_ts": 1.0}])
    rec, _ = beat(preempt=True, answer_woke=True, answer_first_on_person_wake=True)
    assert not rec.get("preempted") and rec["explore"] is not None
