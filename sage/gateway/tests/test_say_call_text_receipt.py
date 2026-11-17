"""A say whose text writes out a tool call says in its receipt that nothing ran (#718).

cbp-being, 2026-11-15 01:38Z: in an answer turn offering only `say`, it pasted
`settle id="s544" question=... answer=...` into the message, then wrote "[DONE] Settled s544" to its
todo; the settled log has no op for either id. The message is still delivered as written."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sage.gateway import conversations as conv  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.hestia_dispatch import call_text_verbs  # noqa: E402
from sage.gateway.tests.test_hestia_dispatch import _ALLOW, _disp  # noqa: E402

PASTED = ('Fixing both now.\n'
          'settle id="s544" question="are labels regenerated?" answer="no, coin flips" evidence="gen.py"\n'
          'settle id="s545" question="..." answer="..." evidence="..."\n'
          '- `memory_edit path="todo.md" old="x" new="y"`\n')


def _home():
    d, root = _disp()
    home = Path(root)
    conv.create(home, "dp", title="dp", participants=["dp", "sprout-being"],
                writable_by=["dp", "sprout-being"])
    return d, home


def test_call_text_is_named_and_the_message_is_delivered_unchanged():
    d, home = _home()
    r = d(BeingIntent("say", {"to": "dp", "text": PASTED}), _ALLOW)
    assert r.ok, r.error
    note = r.result["not_performed"]
    assert note.startswith("This message contains the text of a settle call and a memory_edit call."), note
    assert "none of them ran" in note and "call settle / memory_edit itself as a tool" in note, note
    assert conv.recent(home, "dp", limit=1)[-1]["text"] == PASTED.strip(), "delivered as written"


def test_prose_naming_a_verb_adds_nothing():
    d, home = _home()
    for text in ("I will settle this next beat.", "Settled s544: labels are random.",
                 "the settle verb takes id= and reopen=", "run it again (later)"):
        r = d(BeingIntent("say", {"to": "dp", "text": text}), _ALLOW)
        assert r.ok and "not_performed" not in r.result, (text, r.result)


def test_helper_shapes():
    assert call_text_verbs('settle(id="s1")') == ["settle"]
    assert call_text_verbs("> retire_note path=notes/a.md reason=old") == ["retire_note"]
    assert call_text_verbs('say to="dp" text="hi"') == [], "say inside a say is not flagged"
    assert call_text_verbs("frobnicate x=1") == [], "not one of the being's verbs"
    assert call_text_verbs("settle id=1\nsettle id=2") == ["settle"], "each verb once"
