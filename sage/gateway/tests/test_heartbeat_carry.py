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
