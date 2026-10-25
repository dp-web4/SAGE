"""being_self: the being's own words about itself, editable with an audit trail. dp, 2026-10-24:
"is the being allowed to edit its own identity? it should be. with audit trail." """
import json
import tempfile
from pathlib import Path

import pytest

from sage.gateway import being_self as bs
from sage.gateway.being_gate_client import BeingIntent, GatewayVerdict
from sage.gateway.hestia_dispatch import HestiaF1aDispatcher
from sage.gateway.tests.test_hestia_dispatch import FakeMcp

_ALLOW = GatewayVerdict("allow")


def _log(h):
    return [json.loads(l) for l in (h / bs.SELF_LOG).read_text().splitlines()]


def test_a_field_is_written_replaced_and_every_version_kept(tmp_path):
    ok, text = bs.edit(tmp_path, "values", "honest records over tidy ones", "first time", now=0)
    assert ok and "honest records" in text
    ok, text = bs.edit(tmp_path, "values", "attention over speed", "I changed my mind", now=60)
    assert ok and "earlier text is kept" in text
    cur, err = bs.read(tmp_path)
    assert err is None and cur["values"]["text"] == "attention over speed"
    assert [(e["from"], e["to"], e["why"]) for e in _log(tmp_path)] == [
        (None, "honest records over tidy ones", "first time"),
        ("honest records over tidy ones", "attention over speed", "I changed my mind")]


def test_no_field_lists_and_writes_nothing(tmp_path):
    ok, text = bs.edit(tmp_path, None, None, "")
    assert ok and "description" in text and "not written yet" in text
    assert not (tmp_path / bs.SELF_FILE).exists() and not (tmp_path / bs.SELF_LOG).exists()


@pytest.mark.parametrize("field,text,why,says", [
    ("trust_ceiling", "1.0", "x", "not one of your identity fields"),
    ("lct", "lct://elsewhere", "x", "not one of your identity fields"),
    ("values", "", "x", "give the text"),
    ("values", "a", "", "give a why"),
    ("values", "x" * (bs.FIELD_MAX_CHARS + 1), "x", "at most"),
])
def test_a_refused_edit_says_why_and_changes_nothing(tmp_path, field, text, why, says):
    ok, msg = bs.edit(tmp_path, field, text, why)
    assert not ok and says in msg and "Nothing was changed" in msg
    assert not (tmp_path / bs.SELF_FILE).exists() and not (tmp_path / bs.SELF_LOG).exists()


def test_an_edit_that_cannot_be_logged_is_undone(tmp_path):
    bs.edit(tmp_path, "description", "a small being", "start")
    before = (tmp_path / bs.SELF_FILE).read_bytes()
    (tmp_path / bs.SELF_LOG).unlink()
    (tmp_path / bs.SELF_LOG).mkdir()                 # appending to a directory raises OSError
    ok, msg = bs.edit(tmp_path, "description", "something else", "why")
    assert not ok and "undone" in msg
    assert (tmp_path / bs.SELF_FILE).read_bytes() == before


def test_it_is_registered_offered_and_judged_as_a_write_of_exactly_what_it_touches(tmp_path):
    from sage.gateway import being_gate_client as g
    from sage.gateway import toolset
    assert "identity_edit" in g._REGISTRY and "identity_edit" in g._CONSEQUENTIAL
    assert "identity_edit" in [t["function"]["name"] for t in toolset.specs()]
    declared = set(g.self_paths({"field": "values"}, {"memory_root": str(tmp_path)}))
    assert g.self_paths({}, {"memory_root": str(tmp_path)}) == []
    with pytest.raises(ValueError):
        g.self_paths({"field": "values"}, {})
    for i in range(2):
        before = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
        assert bs.edit(tmp_path, "values", f"v{i}", "why")[0]
        after = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
        changed = {str(p.resolve()) for p in set(before) | set(after) if before.get(p) != after.get(p)}
        assert changed and changed <= declared, changed - declared


def _disp():
    FakeMcp.calls = []
    root = tempfile.mkdtemp(prefix="hs-")
    return HestiaF1aDispatcher("sprout-being", root, mcp_factory=lambda ep, pid: FakeMcp(ep, pid)), Path(root)


def test_the_verb_edits_and_witnesses_and_direct_writes_are_refused():
    d, root = _disp()
    env = d(BeingIntent("identity_edit", {"field": "questions", "text": "what does a test question look like?",
                                          "why": "a test reason"}), _ALLOW)
    assert env.ok and env.witness_id, env.error
    assert bs.read(root)[0]["questions"]["text"] == "what does a test question look like?"
    for verb, args in (("memory_write", {"path": "self.json", "content": "{}"}),
                       ("memory_write", {"path": "self_log.jsonl", "content": "{}"}),
                       ("memory_edit", {"path": "self_log.jsonl", "start_line": 1, "end_line": 1,
                                        "content": "{}"})):
        env = d(BeingIntent(verb, args), _ALLOW)
        assert not env.ok and "identity_edit" in env.error, (verb, args, env)
    assert len(_log(root)) == 1


def test_the_beat_shows_its_words_only_once_it_has_written_some(tmp_path):
    assert bs.render(tmp_path) == ""
    bs.edit(tmp_path, "description", "a test description", "start")
    shown = bs.render(tmp_path)
    assert "Who you say you are" in shown and "a test description" in shown
    from sage.gateway.heartbeat import own_state
    assert "a test description" in own_state(tmp_path, "sprout-being", body_reading={})
