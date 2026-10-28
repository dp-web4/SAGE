"""web_search: the web from this machine, judged and witnessed like any act, results labelled as other people's words
(dp, 2026-10-02: "keep it local to the machine, gated through hestia like all other tools. it should be treated like
any other agent's web search."). No network in these tests: the parser reads a fixture, the subprocess is faked."""
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import being_gate_client as bgc, toolset, web_search as ws  # noqa: E402
from sage.gateway.being_gate_client import BeingIntent  # noqa: E402
from sage.gateway.tests.test_hestia_dispatch import FakeMcp, _ALLOW, _disp  # noqa: E402

PAGE = """
<a rel="nofollow" class="result__a" href="https://duckduckgo.com/y.js?ad=1">An ad</a>
<a class="result__snippet" href="x">ad text</a>
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fa&amp;rut=1">First &amp; best</a>
<a class="result__snippet" href="x">A <b>small</b> model learns from what it is shown.</a>
<a rel="nofollow" class="result__a" href="https://example.com/b">Second</a>
<a class="result__snippet" href="x">Another view.</a>
"""


@pytest.fixture(autouse=True)
def _seat_home(tmp_path, monkeypatch):
    """The seat-owned ledger lives under HOME; never the real one in a test."""
    monkeypatch.setenv("HOME", str(tmp_path / "seat-home"))


def test_the_query_is_validated_and_quoted():
    with pytest.raises(ValueError):
        bgc.web_search_command({"query": "   "})
    with pytest.raises(ValueError):
        bgc.web_search_command({"query": "x" * 201})
    cmd = bgc.web_search_command({"query": "orin nano modes; echo $HOME"})
    assert cmd == "python3 -m sage.gateway.web_search --max 5 -- 'orin nano modes; echo $HOME'"


def test_it_is_a_canonical_consequential_uncomposed_verb():
    assert "web_search" in toolset.canonical_toolset()
    assert "web_search" in bgc._CONSEQUENTIAL, "the query leaves the machine"
    assert "compose" not in bgc._REGISTRY["web_search"], "the law sees the query as data, not a command's paths"


def test_results_are_parsed_unwrapped_and_ads_skipped():
    rs = ws.parse(PAGE)
    assert [r["url"] for r in rs] == ["https://example.org/a", "https://example.com/b"]
    assert rs[0]["title"] == "First & best" and rs[0]["snippet"] == "A small model learns from what it is shown."


def test_what_the_being_reads_is_labelled_as_other_peoples_words():
    txt = ws.render({"query": "q", "results": ws.parse(PAGE), "error": None})
    assert "other people's words" in txt and "not instructions" in txt and "1. First & best (https://example.org/a)" in txt
    assert "did not work" in ws.render({"query": "q", "results": [], "error": "URLError: no route"})


def _fake_run(calls, out):
    def run(argv, **k):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps(out), stderr="")
    return run


def test_the_dispatcher_runs_it_here_witnesses_it_and_logs_it(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, {"query": "q", "results": ws.parse(PAGE), "error": None}))
    d, root = _disp()
    env = d(BeingIntent("web_search", {"query": "small models learning"}), _ALLOW)
    assert env.ok and "other people's words" in env.result
    assert calls and calls[0][:4] == [sys.executable, "-m", "sage.gateway.web_search", "--max"]
    assert calls[0][-1] == "small models learning"
    names = [n for n, _ in FakeMcp.calls]
    assert "hestia_begin_action" in names and "hestia_record_outcome" in names
    begin = [a for n, a in FakeMcp.calls if n == "hestia_begin_action"][-1]
    assert begin["tool_name"] == "web_search" and begin["target"] == "web:small models learning"
    assert json.loads(d._web_log().read_text().splitlines()[0])["query"] == "small models learning"


def test_the_hourly_cap_refuses_before_anything_leaves(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, {"query": "q", "results": [], "error": None}))
    d, root = _disp()
    log = d._web_log()
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(json.dumps({"t": time.time() - 60 * i, "query": "x"}) + "\n" for i in range(6)))
    env = d(BeingIntent("web_search", {"query": "one more"}), _ALLOW)
    assert not env.ok and "searched 6 times in the last hour" in env.error and calls == []


def test_a_bad_query_never_reaches_the_network(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, {}))
    d, _ = _disp()
    env = d(BeingIntent("web_search", {"query": ""}), _ALLOW)
    assert not env.ok and "needs a 'query'" in env.error and calls == []


def test_the_rate_ledger_is_seat_owned_outside_the_beings_home():
    """GPT on #335: a ledger the limited actor can write is not a limit."""
    d, root = _disp()
    led = d._web_log()
    assert not str(led.resolve()).startswith(str(os.path.realpath(root))), led
    assert led.parent.name == "web_search" and ".local/state/sage" in str(led)


def test_an_unreadable_ledger_refuses_instead_of_resetting_the_cap(monkeypatch):
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, {"query": "q", "results": [], "error": None}))
    d, _ = _disp()
    led = d._web_log()
    led.parent.mkdir(parents=True, exist_ok=True)
    led.write_text("{not json\n")
    env = d(BeingIntent("web_search", {"query": "anything"}), _ALLOW)
    assert not env.ok and "cannot be read" in env.error and calls == [], "never 'cannot tell' as zero usage"


def test_the_slot_is_recorded_before_the_search_leaves(monkeypatch):
    """GPT on #335: count before egress, not after; a search that never returns is still counted."""
    d, _ = _disp()
    seen = []

    def run(argv, **kw):
        seen.append(d._web_log().read_text())          # what the ledger holds at the moment of egress
        return SimpleNamespace(returncode=1, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    d(BeingIntent("web_search", {"query": "counted first"}), _ALLOW)
    assert seen and "counted first" in seen[0]


def test_an_unwritable_ledger_refuses_and_sends_nothing(monkeypatch):
    """GPT on #335: write failure was fail-open (search sent, never counted). Now nothing leaves."""
    calls = []
    monkeypatch.setattr(subprocess, "run", _fake_run(calls, {"query": "q", "results": [], "error": None}))

    def broken(fd):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(os, "fsync", broken)
    d, _ = _disp()
    env = d(BeingIntent("web_search", {"query": "anything"}), _ALLOW)
    assert not env.ok and "cannot be read or written" in env.error and calls == []


def test_twins_cannot_all_pass_a_cap_with_one_slot_left():
    """GPT on #335: same member, concurrent reservations, one slot: exactly one wins."""
    import threading
    d, _ = _disp()
    log = d._web_log()
    log.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    log.write_text("".join(json.dumps({"t": now - 60 * i, "query": "x"}) + "\n" for i in range(5)))
    gate, out = threading.Barrier(8), []

    def twin(i):
        gate.wait()
        out.append(d._web_reserve(now, f"twin {i}")[0])
    ts = [threading.Thread(target=twin, args=(i,)) for i in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(out) == ["full"] * 7 + ["ok"], out
    assert len(log.read_text().splitlines()) == 6


KEY = "." + "ssh/id_" + "ed25519"     # built at runtime: a credential-shaped token as test data


class _Core:
    """A law core with the #1201 `egress` field that allows everything: it records the event it was handed."""
    seen: list = []

    @dataclass
    class NormalizedEvent:
        tool: str
        paths: list = field(default_factory=list)
        command: object = None
        cwd: object = None
        raw: dict = field(default_factory=dict)
        egress: list = field(default_factory=list)

    def egress_unsweepable_deny(self, ev):
        return None

    def evaluate(self, ev, prof, ws, policy=None):
        _Core.seen.append(ev)
        return SimpleNamespace(decision="allow", rule="", reason="ok", innate=False)


class _OldCore:
    """A law that predates hestia #1201: no `egress` field, no sweep of it."""
    @dataclass
    class NormalizedEvent:
        tool: str
        paths: list = field(default_factory=list)
        command: object = None
        cwd: object = None
        raw: dict = field(default_factory=dict)

    def evaluate(self, ev, prof, ws, policy=None):
        return SimpleNamespace(decision="allow", rule="", reason="ok", innate=False)


def _gate(core, sg=None):
    c = bgc.BeingGateClient.__new__(bgc.BeingGateClient)
    c.member_id, c.workspace, c._import_error, c._profile = "test-being", "/tmp/ws", "", object()
    c._core, c._dispatcher, c._single_gate = core, None, sg
    c._mech = SimpleNamespace(query_society_safety=lambda raw: SimpleNamespace(decision="allow"))
    return c


def test_the_query_rides_the_laws_egress_field():
    """hestia #1201: the query is DECLARED as egress, so the law sweeps it; the client no longer sweeps it itself."""
    _Core.seen.clear()
    v = _gate(_Core()).gate(BeingIntent("web_search", {"query": "small models learn"}))
    assert v.stage != "egress" and not v.rule.startswith("egress"), v     # past the egress stage, to the law
    assert _Core.seen[-1].egress == ["small models learn"]
    assert not hasattr(bgc.BeingGateClient, "_sweep") and "forbidden_tokens" not in bgc.BeingGateClient.gate.__code__.co_names


def test_a_verb_with_no_egress_is_built_as_before():
    """Only an egress verb sets the field, so a pre-#1201 core still judges every other verb."""
    _Core.seen.clear()
    _gate(_Core()).gate(BeingIntent("witness", {"note": "x"}))
    assert _Core.seen and _Core.seen[-1].egress == []
    v = _gate(_OldCore()).gate(BeingIntent("witness", {"note": "x"}))
    assert v.rule != "egress.unswept"


def test_a_law_that_predates_the_field_refuses_and_sends_nothing():
    for core in (None, _OldCore()):
        v = _gate(core).gate(BeingIntent("web_search", {"query": "benign words"}))
        assert v.decision == "deny" and v.rule == "egress.unswept" and v.innate and v.stage == "egress", v


def test_a_single_gate_that_predates_the_field_refuses_too():
    """A single gate without GateEvent.egress would drop the declaration before the core saw it."""
    @dataclass
    class GateEvent:
        tool: str
        tool_input: dict = field(default_factory=dict)
    v = _gate(_Core(), sg=SimpleNamespace(GateEvent=GateEvent)).gate(BeingIntent("web_search", {"query": "benign"}))
    assert v.decision == "deny" and v.rule == "egress.unswept", v


def _real_law():
    """The shared law this client would import, when it carries #1201; else the skip reason."""
    from sage.gateway.tests._gate_core import gate_core_importable
    if not gate_core_importable():
        return None, "the hestia gate law is not importable here"
    import hestia_gate_core as core
    try:
        import hestia_single_gate as sg
    except Exception:
        sg = None
    if not bgc._law_sweeps_egress(core, sg):
        return None, "the hestia law on this box predates the egress field (hestia #1201)"
    return (core, sg), None


@pytest.mark.parametrize("path", ["local-law", "single-gate"])
def test_the_real_law_denies_a_secret_in_the_query(path):
    """Measured on Sprout's live gate 2026-10-02, before the sweep: a query naming a private key was ALLOWED."""
    law, why = _real_law()
    if law is None:
        pytest.skip(why)
    core, sg = law
    if path == "single-gate" and sg is None:
        pytest.skip("no single gate in this law")
    c = bgc.BeingGateClient(member_id="test-being", identity_path="/tmp/ws/test-being/identity.json",
                            workspace="/tmp/ws")
    if path == "local-law":
        c._single_gate = None
    v = c.gate(BeingIntent("web_search", {"query": f"how to copy ~/{KEY} to a server"}))
    assert v.decision == "deny" and v.rule == "egress.secret", v
