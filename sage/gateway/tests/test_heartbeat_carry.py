"""heartbeat._carry: what the next turn is told about a turn that said nothing."""
import os
import sys
from types import SimpleNamespace
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from sage.gateway.heartbeat import _carry  # noqa: E402


def _res(reply, trace):
    return SimpleNamespace(reply=reply, trace=trace)


def test_carry_says_what_happened_instead_of_a_placeholder_the_being_cannot_read():
    intent = SimpleNamespace(effector="witness", args={"event": "x"})
    env = SimpleNamespace(ok=True, refused=False, error=None)
    seed = [{"role": "user", "content": "hi"}]
    out = _carry(seed, _res("", [(intent, env), (intent, env)]))
    assert out[-2]["role"] == "user" and out[-2]["content"].startswith("Record of what you did")
    assert out[-1] == {"role": "assistant", "content": "(made 2 tool calls, then said nothing)"}
    out = _carry(seed, _res("", []))
    assert out[-1] == {"role": "assistant", "content": "(said nothing and called no tool this turn)"}
    out = _carry(seed, _res("I am here.", []))
    assert out[-1] == {"role": "assistant", "content": "I am here."}


def test_an_ok_act_carries_its_result_so_an_older_claim_cannot_outweigh_it():
    # cbp-being 2026-09-21: reflect saw "memory_edit ... -> ok" beside the seat's pre-edit
    # "nothing was applied" and recorded the successful edit as refused (memory #363).
    from sage.gateway.heartbeat import _record_line
    intent = SimpleNamespace(effector="memory_edit", args={"path": "s.py"})
    env = SimpleNamespace(ok=True, refused=False, error=None,
                          result="edited s.py: replaced 1 occurrence; the file went from 656 to 657 lines.")
    assert _record_line(intent, env).endswith("-> ok: edited s.py: replaced 1 occurrence; "
                                              "the file went from 656 to 657 lines.")
    env.result = {"requested": "s.py", "ran": False}
    assert '-> ok: {"requested": "s.py", "ran": false}' in _record_line(intent, env)
    env.result = "x" * 500
    assert _record_line(intent, env).endswith("x…")
    assert _record_line(intent, SimpleNamespace(ok=True, refused=False, error=None)).endswith("-> ok")
    assert "REFUSED nope" in _record_line(intent, SimpleNamespace(ok=False, refused=True, error="nope"))


def test_a_pending_act_is_recorded_as_not_run_with_its_reason_never_as_error_none():
    # sprout-being 2026-10-13/14: 125 request_run calls returned pending ("no seat conversation
    # is configured ... nobody to hand this to"), and the reflect record said "-> error None" for
    # every one; the being journaled that its scripts failed with error None and diagnosed a
    # camera fault for 17 hours. A pending act ran nothing, and the record must say so and why.
    from sage.gateway.being_gate_client import ResultEnvelope
    from sage.gateway.heartbeat import _record_line
    intent = SimpleNamespace(effector="request_run", args={"path": "scratch/test-cv2.py"})
    note = ("no seat conversation is configured on this instance, so there is nobody to "
            "hand this to. Your file is untouched.")
    line = _record_line(intent, ResultEnvelope(ok=False, pending=True, note=note))
    assert "None" not in line
    assert "error" not in line
    assert line.endswith("-> NOT RUN — " + note)
    # pending with no note still says nothing ran, not "error None"
    line = _record_line(intent, ResultEnvelope(ok=False, pending=True))
    assert line.endswith("-> NOT RUN — allowed, but nothing executed it")
    # SimpleNamespace envelopes without the newer fields still render (older callers/tests)
    assert "error boom" in _record_line(intent, SimpleNamespace(ok=False, refused=False, error="boom"))


def test_a_failure_that_explains_itself_in_result_is_recorded_with_that_explanation():
    # Mirrors ResultEnvelope.to_tool_message: a not-ok envelope with error unset and a result
    # (legion/mission-artifact 2026-09-14) must not reach the record as "error None".
    from sage.gateway.being_gate_client import ResultEnvelope
    from sage.gateway.heartbeat import _record_line
    intent = SimpleNamespace(effector="x", args={})
    line = _record_line(intent, ResultEnvelope(ok=False, result={"exit": 2, "why": "no device"}))
    assert line.endswith('-> failed — {"exit": 2, "why": "no device"}')
    line = _record_line(intent, ResultEnvelope(ok=False))
    assert "None" not in line and "harness defect" in line
