"""Hermetic tests for the window profile (window_profile.py; SAGE-at-home step 1, opt-in `window_profile`).

What must hold:
- absent (or false), nothing changes: the prompt and the tools offered are byte-identical and the record has
  no window_profile field;
- every verb stays callable: the most-used keep their specs, the rest sit behind `verb`, and a `verb` call is
  resolved to the verb it names before the gate, but only on a turn that offers `verb`;
- a listable state section over its share keeps its heading, whole lines and one line with the read that shows
  the rest; nothing else in the state is cut;
- the beat records what the profile did, and `delivered` only once the seed reached the model."""
import json
import os
import sys
from collections import Counter
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway import window_profile as wp  # noqa: E402
from sage.gateway.being_gate_client import BeingGateClient, ResultEnvelope  # noqa: E402


def _spec(name, desc="Does a thing. More words here.", params=("a", "b")):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": {p: {"type": "string", "description": "x" * 40} for p in params},
        "required": [params[0]] if params else []}}}


SPECS = [_spec(n) for n in ("describe", "stay_awake", "rest", "memory_write", "say", "run", "game", "camera")]
size = lambda xs: len(json.dumps(xs))


# ---------------------------------------------------------------- mode

@pytest.mark.parametrize("cfg,on", [({}, False), (None, False), ({"window_profile": False}, False),
                                    ({"window_profile": "off"}, False), ({"window_profile": True}, True),
                                    ({"window_profile": "on"}, True)])
def test_the_profile_is_opt_in(cfg, on):
    assert wp.mode(cfg) is on


# ---------------------------------------------------------------- tools

def test_specs_that_fit_their_share_are_offered_unchanged():
    out, rec = wp.fit_tools(SPECS, size(SPECS) + 1, Counter())
    assert out is SPECS and rec["fits"] and rec["routed"] == []


def test_the_most_used_verbs_keep_their_specs_in_order_and_the_rest_are_listed_behind_verb():
    counts = Counter({"memory_write": 50, "say": 30, "run": 10})
    budget = size(SPECS[:3]) + size([SPECS[3], SPECS[4]]) + 700
    out, rec = wp.fit_tools(SPECS, budget, counts)
    names = [s["function"]["name"] for s in out]
    assert names[:3] == ["describe", "stay_awake", "rest"], "how it finds the rest, keeps going and stops"
    assert "memory_write" in names and "say" in names
    assert names[-1] == wp.ROUTER and size(out) <= budget and rec["fits"]
    router = out[-1]["function"]
    routed = router["parameters"]["properties"]["name"]["enum"]
    assert set(routed) == set(rec["routed"]) and "game" in routed and "camera" in routed
    assert set(routed) | set(names[:-1]) == {s["function"]["name"] for s in SPECS}, "every verb is still callable"
    assert "describe <name>" in router["description"]
    for word in ("must", "should", "always", "never", "you need"):
        assert word not in router["description"].lower(), "a listing, not an instruction (paged-context P1)"


def test_a_less_used_verb_never_jumps_a_more_used_one_and_an_unused_verb_never_takes_a_spec():
    counts = Counter({"memory_write": 50, "say": 30})
    out, rec = wp.fit_tools(SPECS, 10_000_000 // 10_000, counts)        # a tiny budget: nothing extra fits
    assert rec["kept"] == ["describe", "stay_awake", "rest"]
    out, rec = wp.fit_tools(SPECS, size(SPECS) - 1, counts)             # nearly everything fits
    assert "game" in rec["routed"] and "camera" in rec["routed"], "unused verbs stay listed"
    assert "memory_write" in rec["kept"] and "say" in rec["kept"]


def test_the_listing_drops_its_one_line_descriptions_before_a_used_verb_loses_its_spec():
    long = [_spec(n, desc="A very long description sentence that keeps going for a while. " * 3)
            for n in ("describe", "stay_awake", "rest", "say")] + \
           [_spec(f"tail{i}", desc="Tail verb number something with a long first sentence here.") for i in range(30)]
    counts = Counter({"say": 5})
    with_lines = wp.router_spec(long[4:], True)
    budget = size(long[:4]) + size([wp.router_spec(long[4:], False)]) + 10
    assert size(long[:4]) + size([with_lines]) > budget
    out, rec = wp.fit_tools(long, budget, counts)
    assert rec["router_lines"] is False and "say" in rec["kept"]


@pytest.mark.parametrize("args,expect", [
    ({"name": "say", "args": {"to": "dp", "text": "hi"}}, ("say", {"to": "dp", "text": "hi"})),
    ({"name": "say", "args": '{"to": "dp"}'}, ("say", {"to": "dp"})),
    ({"name": "say"}, ("say", {})),
    ({"name": "say", "args": "not json"}, ("say", {"_raw": "not json"})),
    ({"name": "", "args": {}}, (wp.ROUTER, {"name": "", "args": {}})),
])
def test_a_verb_call_resolves_to_the_verb_it_names(args, expect):
    assert wp.resolve_router(wp.ROUTER, args) == expect


def test_a_call_to_any_other_name_is_untouched():
    assert wp.resolve_router("say", {"name": "x"}) == ("say", {"name": "x"})


def _client():
    c = BeingGateClient.__new__(BeingGateClient)
    c.member_id, c.workspace, c._import_error, c._profile = "test-being", "/tmp/ws", "", object()
    c._dispatcher = lambda intent, v: ResultEnvelope(ok=True, result=f"result[{intent.effector}]", witness_id="w")
    c._mech = NS(query_society_safety=lambda raw: NS(decision="allow"))
    c._core = NS(NormalizedEvent=lambda **kw: NS(raw=kw.get("raw", {})),
                 evaluate=lambda ev, prof, ws, policy=None: NS(decision="allow", rule="", reason="ok", innate=False))
    return c


def _llm_calling_verb():
    calls = {"n": 0}

    class FakeLLM:
        def get_chat_response(self, messages, tools=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"content": "", "tool_calls": [{"function": {"name": wp.ROUTER, "arguments": {
                    "name": "witness", "args": {"event": "x"}}}}]}
            return {"content": "done", "tool_calls": []}
    return FakeLLM()


def test_on_a_turn_that_offers_verb_the_call_is_gated_and_recorded_as_the_verb_it_names():
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
    tools = [_spec("witness", params=("event",)), wp.router_spec([_spec("game")])]
    r = run_ollama_tool_turn(_client(), _llm_calling_verb(), [{"role": "user", "content": "hi"}], tools=tools)
    intent, env = r.trace[0]
    assert intent.effector == "witness" and intent.args == {"event": "x"} and env.ok


def test_on_a_turn_that_does_not_offer_verb_nothing_is_resolved():
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
    tools = [_spec("witness", params=("event",))]
    r = run_ollama_tool_turn(_client(), _llm_calling_verb(), [{"role": "user", "content": "hi"}], tools=tools)
    assert r.trace[0][0].effector == wp.ROUTER, "an unoffered name stays what it was, for the gate to judge"


# ---------------------------------------------------------------- state

def _state(todo_n=40, notes_n=30, dp_letter=""):
    todo = "\n".join(f"- [ ] item {i} with some words (since 2026-11-26 10:00 UTC)" for i in range(todo_n))
    notes = "\n".join(f"- 2026-11-26-note-{i}.md" for i in range(notes_n))
    return ("# Your own state\n\n## Your body\nwarm, awake\n\n"
            + (f"## From dp, the operator, directly\n{dp_letter}\n\n" if dp_letter else "")
            + f"## todo.md: still open ({todo_n})\n{todo}\n\n"
            + f"## notes/ (newest first; {notes_n} of 99)\n{notes}\n")


def test_a_listable_section_over_its_share_keeps_heading_whole_lines_and_the_read_for_the_rest(tmp_path):
    s = _state()
    text, rec = wp.fit_state(s, 3000, tmp_path)
    assert text.count("## todo.md: still open (40)") == 1
    todo = text.split("## todo.md")[1].split("## notes/")[0]
    assert "- [ ] item 0 with some words" in todo, "the newest are kept, whole"
    assert "memory_read path todo.md" in todo and "more lines not shown here" in todo
    assert len(todo) <= int(3000 * 0.12) + len("## todo.md") + 2
    r = next(x for x in rec["listed"] if x["section"].startswith("todo.md"))
    assert r["lines_shown"] + r["lines_hidden"] == 40 and r["handle"] == "memory_read path todo.md"
    assert "memory_read path notes" in text
    for word in ("must", "should", "you need to"):
        assert word not in text.split("## todo.md")[1].lower(), "material and a read, no instruction"


def test_sections_the_profile_does_not_manage_are_never_cut(tmp_path):
    letter = "words from dp " * 400
    text, rec = wp.fit_state(_state(dp_letter=letter), 1000, tmp_path)
    assert letter in text and "warm, awake" in text
    assert rec["over_budget_by"] > 0, "it says when what it may not cut is over the share"


def test_a_state_that_fits_is_returned_unchanged(tmp_path):
    s = _state(todo_n=2, notes_n=2)
    text, rec = wp.fit_state(s, 100_000, tmp_path)
    assert text == s and rec["listed"] == []


def test_the_journal_tail_keeps_its_newest_lines_and_names_the_hidden_lines_by_number(tmp_path):
    lines = [f"entry {i}: something happened" for i in range(1, 101)]
    (tmp_path / "journal.md").write_text("\n".join(lines) + "\n")
    s = "## journal.md (tail)\n" + "\n".join(lines[-40:]) + "\n"
    text, rec = wp.fit_state(s, 3000, tmp_path)
    assert "entry 100: something happened" in text and "entry 61:" not in text
    r = rec["listed"][0]
    end = 100 - r["lines_shown"]
    assert f"memory_read path journal.md start_line {end - r['lines_hidden'] + 1} end_line {end}" in text
    assert f"entry {end}:" not in text and f"entry {end + 1}:" in text


def test_the_run_box_todo_duplicate_folds_into_the_todo_lines_it_repeats(tmp_path):
    s = ("## todo.md: still open (2)\n- [ ] install numpy for the xor test (since 2026-11-26 10:00 UTC)\n"
         "- [ ] write the summary\n\n"
         "## Your open todo items, beside your run box's measurement (you close them; nothing here edits your todo)\n"
         "- \"install numpy for the xor test\": measured, numpy is already importable.\n")
    text, rec = wp.fit_state(s, 100_000, tmp_path)
    assert rec["todo_folded"] == 1
    assert "install numpy for the xor test (since 2026-11-26 10:00 UTC) (run box measured, numpy is already importable.)" in text
    assert "beside your run box's measurement" not in text and text.count("install numpy") == 1


# ---------------------------------------------------------------- through heartbeat.main

@pytest.fixture
def beat(tmp_path, monkeypatch):
    from sage.gateway import conversations as conv, heartbeat as hb
    from sage.gateway.being_tool_loop import ToolTurnResult
    inst = tmp_path / "inst"
    inst.mkdir()
    (inst / "identity.json").write_text(json.dumps({"identity": {"name": "t", "machine": "testbox"}}))
    conv.create(inst, "dp", title="dp", participants=["dp", "test-being"], writable_by=["dp", "test-being"])
    conv.append(inst, "dp", speaker="dp", text="hello there")
    (inst / "todo.md").write_text("open:\n" + "\n".join(f"- [ ] item {i} " + "w" * 60 for i in range(80)) + "\n")
    forum = tmp_path / "forum"
    forum.mkdir()
    from sage.gateway import governed_turn, being_tool_loop, egress_drain, arousal

    class _Disp:
        endpoint = membot_endpoint = "http://127.0.0.1:9/mcp"

        def drain_inbox(self, peek=False):
            return ResultEnvelope(ok=True, result={"notices": []})

    llm = NS(num_ctx=8192, max_response_tokens=1500, get_chat_response=lambda msgs: {"content": "", "raw": {}})
    monkeypatch.setattr(governed_turn, "build_client", lambda *a, **k: (NS(_dispatcher=_Disp()), llm))
    sent = []

    def fake_turn(client, llm_, messages, *a, **kw):
        sent.append(("\n".join(str(m.get("content") or "") for m in messages), json.dumps(kw.get("tools"))))
        return ToolTurnResult(reply="I'm here.", trace=[], steps=1, seed_measured=(1000, 3000))
    monkeypatch.setattr(being_tool_loop, "run_ollama_tool_turn", fake_turn)
    monkeypatch.setattr(hb, "fleet_digest", lambda *a, **k: "(no digest)")
    monkeypatch.setattr(egress_drain, "drain_once", lambda **k: {"drained": 0})
    monkeypatch.setattr(arousal, "claim_pending", lambda *a, **k: [])
    monkeypatch.setattr(arousal, "peek_pending", lambda *a, **k: [])

    def run(**cfg):
        (inst / "instance.json").write_text(json.dumps({"machine": "testbox", **cfg}))
        sent.clear()
        rc = hb.main(["--member", "test-being", "--model", "qwen3.8-distill:4b", "--instance", str(inst),
                      "--forum-dir", str(forum), "--repos", "", "--no-hub-drain", "--no-escalate"])
        assert rc == 0
        return json.loads((inst / "heartbeats.jsonl").read_text().strip().splitlines()[-1]), list(sent)
    return run



@pytest.mark.parametrize("cfg", [{}, {"window_profile": False}])
def test_absent_the_profile_never_runs_through_main(beat, monkeypatch, cfg):
    """Byte-identity by construction: with the key absent or false, no profile function is entered, so the
    specs and the state are exactly what they were; every other change in this PR is behind that guard."""
    def boom(*a, **k):
        raise AssertionError("the profile ran with window_profile absent or false")
    for fn in ("fit_tools", "fit_state", "call_counts", "share_chars"):
        monkeypatch.setattr(wp, fn, boom)
    rec, sent = beat(**cfg)
    assert "window_profile" not in rec
    assert sent and f'"name": "{wp.ROUTER}"' not in sent[0][1]


def test_on_the_profile_offers_verb_lists_the_todo_and_records_delivery(beat):
    rec, sent = beat(window_profile=True)
    wpr = rec["window_profile"]
    assert wpr["num_ctx"] == 8192 and wpr["tools"]["before"] > wpr["tools"]["after"]
    assert wpr["tools"]["after"] <= wpr["tools"]["budget"]
    assert f'"name": "{wp.ROUTER}"' in sent[0][1], "the long tail is behind `verb`"
    assert wpr["state"] and any(x["section"].startswith("todo.md") for x in wpr["state"]["listed"])
    assert "memory_read path todo.md" in sent[0][0]
    assert wpr["delivered"] is True, "the seed was counted whole by the server (seed_measured)"
    assert wpr["not_managed"]["posture"] > 0
