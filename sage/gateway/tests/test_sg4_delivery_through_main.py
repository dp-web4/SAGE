"""Hermetic, through heartbeat.main: an SG4 directory line counts as delivered only when the model read it.

NOVA on SAGE #836: in an answer-first beat (R3) explore never runs, so the seed with its directory lines is
never sent; the beat still recorded a side conversation's directory line as delivered: true, which would
have put an unseen line into the pre-registered comparison's denominator."""
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
    conv.append(inst, "dp", speaker="dp", text="i was asleep, now i'm back. how are you feeling?")
    # A side conversation longer than any rung shows, its newest turn naming its first: an off-window cited line.
    conv.create(inst, "seat", title="seat", participants=["seat", "test-being"], writable_by=["seat", "test-being"])
    first = conv.append(inst, "seat", speaker="seat", text="the plan: folder A, script B")["seq"]
    for i in range(14):
        conv.append(inst, "seat", speaker="seat" if i % 2 else "test-being", text=f"step {i}")
    conv.append(inst, "seat", speaker="seat", text=f"as in seq {first}, go ahead")
    forum = tmp_path / "forum"
    forum.mkdir()
    from sage.gateway import governed_turn, being_tool_loop, egress_drain, arousal
    llm = NS(num_ctx=32768, get_chat_response=lambda msgs: {"content": "", "raw": {}})
    monkeypatch.setattr(governed_turn, "build_client", lambda *a, **k: (NS(_dispatcher=_Disp()), llm))
    sent = []

    def fake_turn(client, llm_, messages, *a, **kw):
        sent.append("\n".join(str(m.get("content") or "") for m in messages))
        # the server counted this prompt whole, as a real generate records it
        return ToolTurnResult(reply="I'm here.", trace=[], steps=1, seed_measured=(1000, 3000))
    monkeypatch.setattr(being_tool_loop, "run_ollama_tool_turn", fake_turn)
    monkeypatch.setattr(hb, "fleet_digest", lambda *a, **k: "(no digest)")
    monkeypatch.setattr(egress_drain, "drain_once", lambda **k: {"drained": 0})
    monkeypatch.setattr(arousal, "claim_pending", lambda *a, **k: [dict(DP_WAKE)])
    monkeypatch.setattr(arousal, "peek_pending", lambda *a, **k: [])

    def run(**cfg):
        (inst / "instance.json").write_text(json.dumps({"machine": "testbox", "conversation_directory": "gist", **cfg}))
        sent.clear()
        rc = hb.main(["--member", "test-being", "--model", "qwen3.8-distill:4b", "--instance", str(inst),
                      "--forum-dir", str(forum), "--repos", "", "--no-hub-drain", "--no-escalate"])
        assert rc == 0
        return json.loads((inst / "heartbeats.jsonl").read_text().strip().splitlines()[-1]), list(sent)
    run.first = first
    return run


def _seat_lines(rec):
    return [e for c in (rec.get("conv_directory") or {}).get("convs") or [] if c["cid"] == "seat"
            for e in c["listed"]]


def test_an_answer_first_beat_delivers_no_directory_line(beat):
    rec, sent = beat(preempt=True, answer_woke=True, answer_first_on_person_wake=True)
    assert rec["explore"] is None, "explore never ran"
    lines = _seat_lines(rec)
    assert lines and lines[0]["seq"] == beat.first, rec.get("conv_directory")
    handle = conv.open_handle("seat", lines[0]["line"])
    assert not any(handle in p for p in sent), "the side line was in no prompt the model got"
    assert rec["conv_directory"]["seed_sent"] is False
    assert all(e["delivered"] is False for e in lines), lines


def test_a_beat_that_sent_the_seed_delivers_its_lines(beat):
    rec, sent = beat(preempt=True, answer_woke=True)
    assert rec["explore"] is not None
    lines = _seat_lines(rec)
    handle = conv.open_handle("seat", lines[0]["line"])
    assert any(handle in p for p in sent), "the line was in the seed the model got"
    assert rec["conv_directory"]["seed_sent"] is True
    assert lines[0]["delivered"] is True
