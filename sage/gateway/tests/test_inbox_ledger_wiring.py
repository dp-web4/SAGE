"""THE INBOX LEDGER AT ITS CALL SITE (#164, GPT re-review of c25999cf6).

test_heartbeat_compose.py pins render_inbox + inbox_ledger as pure functions, driven the way
main() is believed to drive them. That belief was the untested part: main() reads the last
record's ledger, renders the inbox with it, collects what was shown, and writes the next
record's ledger after the beat. These tests run heartbeat.main() itself, beat after beat, on a
temp instance with a fake dispatcher and scripted turns, and read what the being was handed and
what the record says.

Nothing live: no model, no daemon (the dispatcher is a fake and its service URLs are a closed
port), no systemd (conftest), no activity reports (conftest).
"""
import json
from types import SimpleNamespace as NS

import pytest

from sage.gateway import heartbeat as hb
from sage.gateway.being_gate_client import BeingIntent, ResultEnvelope
from sage.gateway.being_tool_loop import ToolTurnResult

CLOSED = "http://127.0.0.1:9/mcp"

COORD = {"id": 501, "kind": "coordination", "from_plugin": "legion-claude",
         "queued_at": "2026-10-02T10:00:00Z", "pointer_uri": "shared-context/plans/coord-plan.md"}
REVIEW = {"id": 502, "kind": "review_done", "from_plugin": "claude-code",
          "queued_at": "2026-10-02T10:01:00Z", "pointer_uri": "hestia://appeal/feedface#ruled-review-done"}
REPLY = {"id": 503, "kind": "reply", "from_plugin": "claude-code",
         "queued_at": "2026-10-02T10:02:00Z", "pointer_uri": "sage://conversation/cbp-claude#seq=4100"}


class FakeDispatcher:
    """drain_inbox is the only door main() uses here. No `_call`, so scope and appeals are
    skipped; the service endpoints point at a closed port."""
    endpoint = CLOSED
    membot_endpoint = CLOSED

    def __init__(self, notices):
        self.notices = notices
        self.peeks = []

    def drain_inbox(self, peek=False):
        self.peeks.append(peek)
        return ResultEnvelope(ok=True, result={"notices": list(self.notices)})


def _act(effector, path, ok=True):
    return (BeingIntent(effector=effector, args={"path": path}),
            ResultEnvelope(ok=ok, result={"ok": ok}, error=None if ok else "refused"))


@pytest.fixture
def beat(tmp_path, monkeypatch):
    """Returns run(explore_trace) -> (inbox text the explore turn was handed, record written)."""
    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / "identity.json").write_text(json.dumps({"identity": {"name": "t", "machine": "testbox"}}))
    (inst / "instance.json").write_text(json.dumps({"machine": "testbox"}))
    forum = tmp_path / "forum"
    forum.mkdir()
    disp = FakeDispatcher([COORD, REVIEW, REPLY])
    seeds = []
    script = {"explore": []}

    from sage.gateway import governed_turn, being_tool_loop

    llm = NS(num_ctx=32768, get_chat_response=lambda msgs: {"content": "", "raw": {}})
    monkeypatch.setattr(governed_turn, "build_client",
                        lambda *a, **k: (NS(_dispatcher=disp), llm))

    def fake_turn(client, llm_, messages, *a, **kw):
        # the FIRST turn of a beat is explore: record the seed it was handed, act as scripted
        script["calls"] += 1
        if script["calls"] == 1:
            seeds.append("\n".join(str(m.get("content") or "") for m in messages if isinstance(m, dict)))
            return ToolTurnResult(reply="done", trace=list(script["explore"]), steps=1)
        return ToolTurnResult(reply="", trace=[], steps=0)

    monkeypatch.setattr(being_tool_loop, "run_ollama_tool_turn", fake_turn)
    monkeypatch.setattr(hb, "fleet_digest", lambda *a, **k: "(no digest)")
    from sage.gateway import egress_drain
    monkeypatch.setattr(egress_drain, "drain_once", lambda **k: {"drained": 0})

    def run(explore_trace):
        script["explore"], script["calls"] = explore_trace, 0
        n = len(seeds)
        rc = hb.main(["--member", "test-being", "--model", "qwen3.8-distill:4b",
                      "--instance", str(inst), "--forum-dir", str(forum), "--repos", "",
                      "--no-hub-drain", "--no-escalate"])
        assert rc == 0
        assert len(seeds) == n + 1
        rec = json.loads((inst / "heartbeats.jsonl").read_text().strip().splitlines()[-1])
        return seeds[-1], rec

    run.disp = disp
    return run


def test_main_applies_the_ledger_coordination_waits_for_its_pointer_to_be_opened(beat):
    """Beat 1 shows all three and acts on something unrelated. Beat 2: the finished review
    folds (shown to a beat that acted); the coordination note and the reply are still mail,
    because nobody opened them. Beat 2 opens the coordination pointer; beat 3 folds it too,
    and the reply is still mail."""
    inbox1, rec1 = beat([_act("memory_write", "journal.md")])
    assert all(p is True for p in beat.disp.peeks), "the beat must only peek"
    for ptr in ("coord-plan.md", "feedface", "seq=4100"):
        assert ptr in inbox1, inbox1
    assert rec1["inbox"]["presented"] == [502], rec1["inbox"]
    assert rec1["inbox"]["opened"] == [], rec1["inbox"]

    inbox2, rec2 = beat([_act("memory_read", "shared-context/plans/coord-plan.md")])
    assert "feedface" not in inbox2 and "1 notice(s) already handled" in inbox2, inbox2
    assert "coord-plan.md" in inbox2, "a coordination note shown once is not handled"
    assert "seq=4100" in inbox2, inbox2
    assert rec2["inbox"]["opened"] == [501] and rec2["inbox"]["opened_this_beat"] == [501], rec2["inbox"]

    inbox3, rec3 = beat([_act("memory_write", "journal.md")])
    assert "coord-plan.md" not in inbox3 and "2 notice(s) already handled" in inbox3, inbox3
    assert "seq=4100" in inbox3, "an unopened reply never folds"


def test_main_a_beat_that_never_acted_presents_nothing_and_a_failed_open_opens_nothing(beat):
    """A beat whose explore turn made no call has not been shown anything: all three stay. A
    refused memory_read of the coordination pointer acknowledges nothing: the coordination note
    stays mail, though that beat did act, so the finished review folds after it."""
    _, rec1 = beat([])
    assert rec1["inbox"]["opened"] == [] and rec1["inbox"]["presented"] == [], rec1["inbox"]
    inbox2, rec2 = beat([_act("memory_read", "shared-context/plans/coord-plan.md", ok=False)])
    for ptr in ("coord-plan.md", "feedface", "seq=4100"):
        assert ptr in inbox2, inbox2
    assert "already handled" not in inbox2, inbox2
    assert rec2["inbox"]["opened"] == [] and rec2["inbox"]["presented"] == [502], rec2["inbox"]
    inbox3, _ = beat([])
    assert "coord-plan.md" in inbox3 and "seq=4100" in inbox3 and "feedface" not in inbox3, inbox3
