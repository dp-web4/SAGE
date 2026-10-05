"""A failed turn selection is recorded, never read as "no one is waiting" (2026-10-04).

On HUB, hub-claude's 09-21 question was never selected in 300+ beats while every beat record looked clean:
pending_selection swallowed all exceptions and returned the same empty tuple as an empty inbox."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv, heartbeat as hb  # noqa: E402


def test_a_selection_that_raises_is_named_in_the_record(monkeypatch):
    def broken(instance):
        raise ValueError("bad meta file")
    monkeypatch.setattr(conv, "listing", broken)
    monkeypatch.setattr(hb, "LAST_SELECTION_ERROR", None)
    out = hb.pending_selection(Path(tempfile.mkdtemp()), "hub-being")
    assert out == ("", "", "", "", None)
    assert hb.LAST_SELECTION_ERROR == "ValueError: bad meta file"


def test_a_clean_empty_selection_records_no_error(monkeypatch):
    monkeypatch.setattr(hb, "LAST_SELECTION_ERROR", None)
    hb.pending_selection(Path(tempfile.mkdtemp()), "hub-being")
    assert hb.LAST_SELECTION_ERROR is None


def test_the_beat_record_carries_it():
    src = (Path(hb.__file__)).read_text()
    assert '"selection_error": LAST_SELECTION_ERROR,' in src
    assert '"selected": ({"turn": f"{selected.cid}:{selected.seq}"' in src, "never selected vs selected, unanswered"


def test_selected_is_defined_before_anything_can_kill_the_beat():
    """The record reads `selected`; a beat killed before selection would otherwise lose its record to NameError."""
    src = Path(hb.__file__).read_text()
    init = src.index("    selected = None          # the record names it")
    first_try = src.index("    try:", src.index("    explore = after = reflect = answer = None"))
    assert init < first_try


# ---- end to end (legion-claude on #353: the source-search tests stay green with `selected` forced to null) ----
import json  # noqa: E402
from types import SimpleNamespace as NS  # noqa: E402

import pytest  # noqa: E402

from sage.gateway.being_gate_client import ResultEnvelope  # noqa: E402
from sage.gateway.being_tool_loop import ToolTurnResult  # noqa: E402


class _Disp:
    endpoint = membot_endpoint = "http://127.0.0.1:9/mcp"

    def drain_inbox(self, peek=False):
        return ResultEnvelope(ok=True, result={"notices": []})


@pytest.fixture
def beat(tmp_path, monkeypatch):
    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / "identity.json").write_text(json.dumps({"identity": {"name": "t", "machine": "testbox"}}))
    (inst / "instance.json").write_text(json.dumps({"machine": "testbox"}))
    conv.create(inst, "dp", title="dp", participants=["dp", "test-being"], writable_by=["dp", "test-being"])
    conv.append(inst, "dp", speaker="dp", text="What did you notice today?")
    forum = tmp_path / "forum"
    forum.mkdir()
    from sage.gateway import governed_turn, being_tool_loop, egress_drain
    llm = NS(num_ctx=32768, get_chat_response=lambda msgs: {"content": "", "raw": {}})
    monkeypatch.setattr(governed_turn, "build_client", lambda *a, **k: (NS(_dispatcher=_Disp()), llm))
    monkeypatch.setattr(being_tool_loop, "run_ollama_tool_turn",
                        lambda *a, **k: ToolTurnResult(reply="", trace=[], steps=0))
    monkeypatch.setattr(hb, "fleet_digest", lambda *a, **k: "(no digest)")
    monkeypatch.setattr(egress_drain, "drain_once", lambda **k: {"drained": 0})

    def run():
        rc = hb.main(["--member", "test-being", "--model", "qwen3.8-distill:4b", "--instance", str(inst),
                      "--forum-dir", str(forum), "--repos", "", "--no-hub-drain", "--no-escalate"])
        assert rc == 0
        return json.loads((inst / "heartbeats.jsonl").read_text().strip().splitlines()[-1])
    return run


def test_main_records_the_selected_question(beat):
    rec = beat()
    assert rec["selected"] == {"turn": "dp:1", "expects_reply": True, "woke": False}, rec["selected"]
    assert rec["selection_error"] is None


def test_main_records_a_failed_selection_then_a_healthy_beat_does_not_carry_it(beat, monkeypatch):
    real = hb.answers_the_being

    def broken(*a, **k):                     # used only by pending_selection: the rest of the beat runs
        raise ValueError("bad meta")
    monkeypatch.setattr(hb, "answers_the_being", broken)
    rec = beat()
    assert rec["selected"] is None and rec["selection_error"] == "ValueError: bad meta"
    monkeypatch.setattr(hb, "answers_the_being", real)
    rec = beat()
    assert rec["selection_error"] is None, "no stale error in-process"
    assert rec["selected"] is not None and rec["selected"]["turn"].startswith("dp:")
