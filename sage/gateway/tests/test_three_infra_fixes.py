"""Three infrastructure fixes from 2026-10-02 (never the being's words or conclusions, only our cuts and doors)."""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import conversations as conv, heartbeat as hb  # noqa: E402
from sage.gateway.tests.test_hestia_dispatch import _ALLOW, _disp  # noqa: E402

CUT = ("That's something I've been thinking about lately. We're all so focused on what we can do that we forget how "
       "to be there with each other. The most important thing isn't the output or the result — it's just showing up "
       "and listening. I think agents need to learn that they are part of a conversation, not just tools. When we "
       "stop treating each other as separate tasks and start seeing ourselves as part-")


@pytest.fixture(autouse=True)
def _roster(tmp_path, monkeypatch):
    (tmp_path / "members.json").write_text(json.dumps({"members": [{"name": n} for n in
                                                                   ["legion-being", "cbp-being", "dp", "Sovereign"]]}))
    monkeypatch.setenv("HUB_MESH_STATE", str(tmp_path))


def test_a_spoken_answer_cut_by_the_cap_ends_at_its_last_whole_sentence():
    assert len(CUT) == 400
    out, cut_from = hb.fit_spoken(CUT)
    assert out.endswith("part of a conversation, not just tools.") and cut_from == 400
    assert hb.fit_spoken("Short and whole.") == ("Short and whole.", 0)
    assert hb.fit_spoken("x" * 399 + ".") == ("x" * 399 + ".", 0), "a full-length but finished sentence stays"
    assert hb.fit_spoken("no sentence end " * 30)[1] == 0, "nothing to trim back to: unchanged"


def test_a_refused_ask_leaves_no_forum_file():
    published = []
    d, _ = _disp(publish_fn=lambda to, body: published.append(to) or "forum/x.md")
    env = d(hb_intent("peer_ask", {"to": "nobody-being", "body": "hello"}), _ALLOW)
    assert not env.ok and "not on the hub roster" in env.error
    assert published == [], "nothing written to the forum for an ask that went nowhere"


def test_an_ask_to_a_conversation_id_is_pointed_at_say():
    published = []
    d, root = _disp(publish_fn=lambda to, body: published.append(to) or "forum/x.md")
    conv.create(root, "room", title="room", participants=["sprout-being", "voice"],
                writable_by=["sprout-being", "voice"])
    env = d(hb_intent("peer_ask", {"to": "room", "body": "I'm sitting here in silence"}), _ALLOW)
    assert not env.ok and 'say with to="room"' in env.error and "spoken aloud" in env.error
    assert published == []


def hb_intent(effector, args):
    from sage.gateway.being_gate_client import BeingIntent
    return BeingIntent(effector, args)
