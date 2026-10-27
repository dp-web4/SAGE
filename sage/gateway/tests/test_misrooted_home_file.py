"""SAGE #506: a home record named at a path no grant reaches is refused by the client, before the
law, so the gate opens no scope request and no peer is woken to rule on a moot ask."""
import pytest

from sage.gateway.being_gate_client import BeingIntent
from sage.gateway.tests.test_being_gate_client import _sg_client

ELSEWHERE = "/nonexistent-root/dp/journal.md"     # outside the home, every grant and the temp root


def _client(reach=(("/srv/granted", True),)):
    c, calls = _sg_client("deny", rule="mrh.path")
    c.memory_root = "/srv/homes/test-being"
    c._policy_grants = lambda: ((), list(reach))
    return c, calls


@pytest.mark.parametrize("verb,args", [
    ("memory_write", {"path": ELSEWHERE, "content": "entry"}),
    ("memory_edit", {"path": "/nonexistent-root/todo.md", "old": "a", "new": "b"}),
    ("memory_read", {"path": ELSEWHERE}),
])
def test_a_misrooted_home_record_is_refused_before_the_law(verb, args):
    c, calls = _client()
    v = c.gate(BeingIntent(verb, args))
    assert v.decision == "deny" and v.rule == "sage.home_file_misrooted", v
    assert calls == [], "the gate was not asked, so it opened no scope request"
    assert "/srv/homes/test-being/" in v.reason and "no scope request was opened" in v.reason, v.reason


def test_the_home_record_itself_goes_to_the_law():
    c, calls = _client()
    for path in ("journal.md", "/srv/homes/test-being/journal.md"):
        c.gate(BeingIntent("memory_write", {"path": path, "content": "x"}))
    assert len(calls) == 2


@pytest.mark.parametrize("path", ["/srv/granted/docs/journal.md", "/tmp/x/journal.md"])
def test_a_path_a_grant_or_the_temp_root_reaches_goes_to_the_law(path):
    c, calls = _client()
    v = c.gate(BeingIntent("memory_write", {"path": path, "content": "x"}))
    assert v.rule != "sage.home_file_misrooted" and len(calls) == 1, v


def test_with_no_grant_snapshot_the_law_decides():
    c, calls = _client(reach=())
    c.gate(BeingIntent("memory_write", {"path": ELSEWHERE, "content": "x"}))
    assert len(calls) == 1


def test_any_other_name_goes_to_the_law():
    c, calls = _client()
    c.gate(BeingIntent("memory_write", {"path": "/nonexistent-root/notes.md", "content": "x"}))
    assert len(calls) == 1


def test_the_refusal_the_being_reads_does_not_repeat_the_home_hint():
    from types import SimpleNamespace
    c, calls = _client()
    c._dispatcher = SimpleNamespace(memory_root=c.memory_root)   # a home _home_hint can name
    env = c._dispatch_resolved(BeingIntent("memory_write", {"path": ELSEWHERE, "content": "x"}))
    assert env.refused and env.error.count("no grant is needed") == 1, env.error
