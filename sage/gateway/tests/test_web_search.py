"""web_search: the web from this machine, judged and witnessed like any act, results labelled as other people's words
(dp, 2026-10-02: "keep it local to the machine, gated through hestia like all other tools. it should be treated like
any other agent's web search."). No network in these tests: the parser reads a fixture, the subprocess is faked."""
import json
import os
import subprocess
import sys
import time
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
