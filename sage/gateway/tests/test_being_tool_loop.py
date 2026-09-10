"""Hermetic tests for the being tool-use loop. No live gate/model: the gate client
uses an injected fake law + mock dispatcher (F1a stand-in), and `generate` is scripted.
Runnable under pytest or directly."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import BeingGateClient, BeingIntent, ResultEnvelope  # noqa: E402
from sage.gateway.being_tool_loop import run_tool_turn  # noqa: E402


def _client(dispatcher):
    """Client whose local law + society both ALLOW, with an injected F1a dispatcher."""
    c = BeingGateClient.__new__(BeingGateClient)
    c.member_id = "test-being"
    c.workspace = "/tmp/ws"
    c._import_error = ""
    c._profile = object()
    c._dispatcher = dispatcher
    c._mech = SimpleNamespace(query_society_safety=lambda raw: SimpleNamespace(decision="allow"))
    c._core = SimpleNamespace(
        NormalizedEvent=lambda **kw: SimpleNamespace(raw=kw.get("raw", {})),
        evaluate=lambda ev, prof, ws, policy=None: SimpleNamespace(
            decision="allow", rule="", reason="ok", innate=False),
    )
    return c


def _scripted(*outs):
    """A generate() that returns each scripted output in turn, recording what it saw."""
    calls = {"seen": []}
    seq = list(outs)

    def generate(messages):
        calls["seen"].append(list(messages))
        return seq.pop(0) if seq else {"content": "(nothing more)", "intents": []}
    return generate, calls


OK_DISPATCH = lambda intent, v: ResultEnvelope(ok=True, result=f"result[{intent.effector}]", witness_id="w1")


def test_dispatches_then_speaks():
    gen, calls = _scripted(
        {"content": "let me check", "intents": [BeingIntent("witness", {"event": "x"})]},
        {"content": "done — here is my reply", "intents": []},
    )
    r = run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "hi"}])
    assert r.reply == "done — here is my reply", r
    assert r.steps == 1 and not r.capped
    assert len(r.trace) == 1 and r.trace[0][1].ok and r.acted


def test_result_is_reinjected_before_second_generate():
    gen, calls = _scripted(
        {"content": "checking", "intents": [BeingIntent("witness", {})]},
        {"content": "final", "intents": []},
    )
    run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "hi"}])
    # the 2nd generate must have seen a tool message carrying the dispatched result
    second_call_msgs = calls["seen"][1]
    assert any(m.get("role") == "tool" and "result[witness]" in m.get("content", "")
               for m in second_call_msgs), second_call_msgs


def test_cap_forces_a_spoken_close():
    # a being that never stops reaching for tools must still end its turn in language
    gen, _ = _scripted(
        {"content": "t1", "intents": [BeingIntent("witness", {})]},
        {"content": "t2", "intents": [BeingIntent("witness", {})]},
        {"content": "forced close", "intents": [BeingIntent("witness", {})]},
    )
    r = run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "hi"}], max_steps=2)
    assert r.capped and r.steps == 2
    assert r.reply == "forced close"


def test_refused_intent_recorded_and_loop_continues():
    # an out-of-registry effector is refused BEFORE the gate; the loop keeps going
    gen, _ = _scripted(
        {"content": "trying shell", "intents": [BeingIntent("shell", {"command": "rm -rf /"})]},
        {"content": "ok, i cannot do that — here's words instead", "intents": []},
    )
    r = run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "hi"}])
    assert len(r.refused) == 1 and r.refused[0][1].refused
    assert r.reply.startswith("ok, i cannot")
    assert not r.acted  # nothing actually executed


def test_pending_f1a_when_no_dispatcher():
    # with no F1a dispatcher, an allowed intent comes back pending — never fabricated
    gen, _ = _scripted(
        {"content": "checking", "intents": [BeingIntent("witness", {})]},
        {"content": "done", "intents": []},
    )
    r = run_tool_turn(_client(None), gen, [{"role": "user", "content": "hi"}])
    assert r.trace[0][1].pending and not r.trace[0][1].ok
    assert "not yet executed" in r.trace[0][1].to_tool_message()


def test_run_ollama_tool_turn_with_fake_llm():
    from sage.gateway.being_gate_client import ollama_tools
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
    # exactly the bounded registry, nothing more: §7.2's 5 verbs + memory split r/w (6),
    # + pr_review (2026-09-03, Legion: the being reviews a PR; the seat posts, gated as
    # the `gh` command it runs), + recall / remember (membot long-term memory) + request_scope
    # (the sanctioned answer to a deny) for the heartbeat (2026-09-03, dp: "it needs a reason
    # to look for things to do"). Widening this number is a registry decision, not a typo.
    # + check (M0, 2026-09-07): the being RUNS a test in its own worktree and reads the
    # result. Argued from measurement, not taste — given only a diff this being asserted
    # a compile error that did not exist; given the same diff plus a real test result it
    # made zero false claims (PRD_BEINGS_IMPROVE_THEIR_HARNESS §2).
    assert len(ollama_tools()) == 17   # + check (M0), git_read, say, pr_open (M1),
                                       # pr_amend + git_restore (both from #63's blockers)

    calls = {"n": 0}

    class FakeLLM:
        def get_chat_response(self, messages, tools=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"content": "checking",
                        "tool_calls": [{"function": {"name": "witness", "arguments": {"event": "x"}}}],
                        "raw": {"message": {"thinking": "I should witness this."}}}
            return {"content": "done", "tool_calls": []}

    r = run_ollama_tool_turn(_client(OK_DISPATCH), FakeLLM(), [{"role": "user", "content": "hi"}])
    assert r.reply == "done"
    assert r.trace and r.trace[0][0].effector == "witness" and r.trace[0][1].ok
    # the think block rides along, one entry per generate (empty when the model had none)
    assert r.thinking == ["I should witness this.", ""]
    # so do Ollama's counters, one entry per generate, None when the fake had none
    assert len(r.generates) == 2 and r.generates[0]["retried"] == 0
    assert r.generates[0]["done_reason"] is None and r.generates[0]["prompt_eval_count"] is None


def test_generate_stats_record_the_window_wall_and_the_retry():
    """Beat 46 on Legion (2026-09-05): every empty turn had prompt_eval + eval == 8192 and
    done_reason length; that lived only on stderr. Now it is on the result, per generate."""
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
    calls = {"n": 0}

    class FakeLLM:
        max_response_tokens = 1024

        def get_chat_response(self, messages, tools=None):
            calls["n"] += 1
            if calls["n"] == 1:   # the wall: nothing said, budget gone in the think block
                return {"content": "", "tool_calls": [],
                        "raw": {"done_reason": "length", "prompt_eval_count": 5000, "eval_count": 3192,
                                "message": {"thinking": "Let me consider"}}}
            return {"content": "done", "tool_calls": [],
                    "raw": {"done_reason": "stop", "prompt_eval_count": 5000, "eval_count": 40, "message": {}}}

    r = run_ollama_tool_turn(_client(OK_DISPATCH), FakeLLM(), [{"role": "user", "content": "hi"}])
    # one generate as the loop sees it: the empty turn was retried once and the retry stood
    assert r.reply == "done" and calls["n"] == 2
    # num_predict: the retry's budget (no window declared -> the 6000 floor), not the first 1024
    assert r.generates == [{"done_reason": "stop", "prompt_eval_count": 5000, "eval_count": 40, "retried": 1,
                            "num_predict": 6000, "nudged": True}]


def test_length_retry_gets_the_room_the_window_has_left_via_the_override():
    """The once-retry must be MORE room than the first attempt, not the same budget again:
    with thinking on OllamaIRP already sends num_predict_think first, and its resolver
    ignores max_response_tokens, so raising that was a re-roll (Legion 18:43Z 2026-09-05).
    The retry sends num_ctx - prompt_eval_count - margin as num_predict_override, and
    puts the override back afterwards so the next generate is a normal first attempt."""
    from sage.gateway.being_tool_loop import run_ollama_tool_turn, RETRY_MARGIN
    seen = []

    class FakeLLM:
        max_response_tokens = 3000
        num_ctx = 16384
        num_predict_override = None

        def get_chat_response(self, messages, tools=None):
            seen.append(self.num_predict_override)
            if len(seen) == 1:   # the heretic's real prompt: 6721 in, the whole 6000 gone thinking, nothing said
                return {"content": "", "tool_calls": [],
                        "raw": {"done_reason": "length", "prompt_eval_count": 6721, "eval_count": 6000,
                                "message": {"thinking": "Let me think about this beat carefully."}}}
            return {"content": "done", "tool_calls": [],
                    "raw": {"done_reason": "stop", "prompt_eval_count": 6721, "eval_count": 700, "message": {}}}

    llm = FakeLLM()
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "hi"}])
    assert r.reply == "done"
    assert seen == [None, 16384 - 6721 - RETRY_MARGIN]      # first attempt: config budget; retry: the window's room
    assert llm.num_predict_override is None                  # restored
    assert llm.max_response_tokens == 3000                   # untouched: it is not the lever
    assert r.generates == [{"done_reason": "stop", "prompt_eval_count": 6721, "eval_count": 700, "retried": 1,
                            "num_predict": 16384 - 6721 - RETRY_MARGIN, "nudged": True}]


def test_length_retry_without_a_window_falls_back_to_the_think_budget():
    """An llm that declares no num_ctx (or no prompt count in the reply) gets the model's
    think budget, never less; and an llm without the override attribute still gets its
    max_response_tokens raised, as before."""
    from sage.gateway.being_tool_loop import _retry_budget, run_ollama_tool_turn
    assert _retry_budget(SimpleNamespace(), {"prompt_eval_count": 6721}) == 6000
    assert _retry_budget(SimpleNamespace(num_ctx=16384), {}) == 6000
    assert _retry_budget(SimpleNamespace(num_ctx=8192), {"prompt_eval_count": 7602}) == 6000   # room 462 < floor
    seen = []

    class OldLLM:                       # no num_predict_override attribute
        max_response_tokens = 1024

        def get_chat_response(self, messages, tools=None):
            seen.append(self.max_response_tokens)
            if len(seen) == 1:
                return {"content": "", "tool_calls": [],
                        "raw": {"done_reason": "length", "prompt_eval_count": 500, "eval_count": 1024, "message": {}}}
            return {"content": "ok", "tool_calls": [], "raw": {"done_reason": "stop", "message": {}}}

    llm = OldLLM()
    r = run_ollama_tool_turn(_client(OK_DISPATCH), llm, [{"role": "user", "content": "hi"}])
    assert r.reply == "ok" and seen == [1024, 6000] and llm.max_response_tokens == 1024


def test_generates_carry_the_budget_sent_and_on_generate_sees_each_entry_as_it_lands():
    """Sprout's #45 sends the window's room on the retry; the record has to SAY what each
    reply's budget was, or "did the retry have more room" is back on stderr. And a caller
    gets each entry as it lands, so a killed beat still leaves its trace."""
    from sage.gateway.being_tool_loop import run_ollama_tool_turn, RETRY_MARGIN
    n = {"i": 0}

    class FakeLLM:                      # OllamaIRP-shaped: resolves 8000 from the config
        max_response_tokens = 3000
        num_ctx = 16384
        num_predict_override = None

        def resolve_num_predict(self):
            return self.num_predict_override if self.num_predict_override is not None else 8000

        def get_chat_response(self, messages, tools=None):
            n["i"] += 1
            if n["i"] == 1:
                return {"content": "", "tool_calls": [],
                        "raw": {"done_reason": "length", "prompt_eval_count": 6767, "eval_count": 8000, "message": {}}}
            if n["i"] == 2:
                return {"content": "", "tool_calls": [{"function": {"name": "witness", "arguments": {"event": "x"}}}],
                        "raw": {"done_reason": "stop", "prompt_eval_count": 6767, "eval_count": 900, "message": {}}}
            return {"content": "done", "tool_calls": [],
                    "raw": {"done_reason": "stop", "prompt_eval_count": 7700, "eval_count": 300, "message": {}}}

    landed = []
    r = run_ollama_tool_turn(_client(OK_DISPATCH), FakeLLM(), [{"role": "user", "content": "hi"}],
                             on_generate=landed.append)
    assert r.reply == "done"
    assert [g["num_predict"] for g in r.generates] == [16384 - 6767 - RETRY_MARGIN, 8000]
    assert [g["retried"] for g in r.generates] == [1, 0]
    assert landed == r.generates and landed[0] is not r.generates[0]   # same content, own copy


def test_on_generate_failure_does_not_take_the_turn_down(capsys):
    from sage.gateway.being_tool_loop import run_ollama_tool_turn

    class FakeLLM:
        def get_chat_response(self, messages, tools=None):
            return {"content": "ok", "tool_calls": [], "raw": {"done_reason": "stop", "message": {}}}

    def boom(entry):
        raise OSError("disk full")

    r = run_ollama_tool_turn(_client(OK_DISPATCH), FakeLLM(), [{"role": "user", "content": "hi"}], on_generate=boom)
    assert r.reply == "ok" and r.generates[0]["num_predict"] is None
    assert "on_generate failed: OSError" in capsys.readouterr().err


def test_retry_room_leaves_no_attribute_behind_on_an_llm_that_had_none():
    from sage.gateway.being_tool_loop import _retry_room
    llm = SimpleNamespace()
    with _retry_room(llm, 6000) as b:
        assert b == 6000 and llm.max_response_tokens == 6000
    assert not hasattr(llm, "max_response_tokens")


def test_salvage_lifts_well_formed_calls_from_the_text_channel_only_for_offered_names():
    from sage.gateway.being_gate_client import ollama_tools
    from sage.gateway.being_tool_loop import salvage_tool_calls
    names = ollama_tools(["recall", "memory_write", "witness"])
    # qwen3.8-distill:2b, Sprout beat 6 explore: fenced JSON object, then prose
    r = salvage_tool_calls('```json\n{"name": "recall", "arguments": {"query": "q", "top_k": 3}}\n```\n\nBrief written response.', names)
    assert [(c["function"]["name"], c["_salvaged"]) for c in r] == [("recall", "json")]
    assert r[0]["function"]["arguments"] == {"query": "q", "top_k": 3}
    # beat 6 reflect: fenced JSON array
    r = salvage_tool_calls('```json\n[{"name": "memory_write", "arguments": {"path": "journal.md", "content": "x"}},'
                           ' {"name": "memory_write", "arguments": {"path": "todo.md", "content": "y"}}]\n```', names)
    assert [c["function"]["arguments"]["path"] for c in r] == ["journal.md", "todo.md"]
    # qwen2.5:1.5b, Legion condition C: bare JSON after a line of prose
    r = salvage_tool_calls('recalling my recent activity\n\n{"name": "recall", "arguments": {"query": "recent actions"}}', names)
    assert len(r) == 1 and r[0]["function"]["name"] == "recall"
    # beat 7: fenced Python with literal kwargs, imported name
    r = salvage_tool_calls('```python\nfrom tools import recall\n\nresult = recall(query="what does it mean to be awake", top_k=3)\nprint(result)\n```', names)
    assert [(c["function"]["name"], c["_salvaged"]) for c in r] == [("recall", "python")]
    assert r[0]["function"]["arguments"] == {"query": "what does it mean to be awake", "top_k": 3}
    # beat 5 reflect: Python with the body assigned to a variable first
    r = salvage_tool_calls('```python\njournal_entry = """[date] what I did"""\n\nmemory_write(path="journal.md", content=journal_entry)\n```', names)
    assert r and r[0]["function"]["arguments"] == {"path": "journal.md", "content": "[date] what I did"}
    # beat 7 reflect: positional arguments, mapped in schema order (path, content)
    r = salvage_tool_calls('```python\nj = """entry"""\nmemory_write("journal.md", j)\nmemory_write("todo.md", "delta")\n```', names)
    assert [c["function"]["arguments"] for c in r] == [{"path": "journal.md", "content": "entry"},
                                                       {"path": "todo.md", "content": "delta"}]
    # not offered this turn, too many positionals, a computed argument, a stub definition
    # (beat 8: `def recall(...)` with a call on an f-string), prose that names a tool
    assert salvage_tool_calls('{"name": "peer_ask", "arguments": {"to": "x"}}', names) == []
    assert salvage_tool_calls('```python\nrecall("q", 3, "x")\n```', names) == []
    assert salvage_tool_calls('```python\nrecall(query=f"{x}")\n```', names) == []
    assert salvage_tool_calls('```python\ndef recall(query, top_k=5):\n    return []\nrecall(query=input())\n```', names) == []
    assert salvage_tool_calls("I could call recall or memory_write here, but I will not.", names) == []
    assert salvage_tool_calls("", names) == []


def test_run_ollama_tool_turn_gates_a_salvaged_call_and_records_it():
    from sage.gateway.being_gate_client import ollama_tools
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
    calls = {"n": 0}

    class FakeLLM:
        def get_chat_response(self, messages, tools=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"content": '```json\n{"name": "witness", "arguments": {"event": "x"}}\n```', "tool_calls": []}
            return {"content": "done", "tool_calls": []}

    r = run_ollama_tool_turn(_client(OK_DISPATCH), FakeLLM(), [{"role": "user", "content": "hi"}],
                             tools=ollama_tools(["witness", "recall"]))
    assert r.trace and r.trace[0][0].effector == "witness" and r.trace[0][1].ok and r.acted
    assert r.salvaged == [{"step": 0, "effector": "witness", "form": "json"}]
    assert r.reply == "done" and r.steps == 1


def test_salvage_accepts_the_other_name_keys_and_flat_arguments():
    """Beat 29 on Sprout (2026-09-05): three turns, three shapes, none lifted."""
    from sage.gateway.being_gate_client import ollama_tools
    from sage.gateway.being_tool_loop import salvage_tool_calls
    names = ollama_tools(["peer_ask", "memory_write", "recall"])
    r = salvage_tool_calls('```json\n{"action": "peer_ask", "to": "legion", "body": "a question"}\n```', names)
    assert [(c["function"]["name"], c["function"]["arguments"]) for c in r] == [("peer_ask", {"to": "legion", "body": "a question"})]
    r = salvage_tool_calls('```json\n[{"tool": "memory_write", "path": "journal.md", "content": "x"},'
                           ' {"tool": "memory_write", "path": "todo.md", "content": "y"}]\n```', names)
    assert [c["function"]["arguments"]["path"] for c in r] == ["journal.md", "todo.md"]
    # stray keys beside a flat call are not arguments; an unknown action is not a call
    r = salvage_tool_calls('{"action": "recall", "query": "q", "timestamp": "now", "status": "final"}', names)
    assert r and r[0]["function"]["arguments"] == {"query": "q"}
    assert salvage_tool_calls('{"action": "complete_beat", "timestamp": "t", "status": "final"}', names) == []
    r = salvage_tool_calls('{"function": "recall", "args": {"query": "q"}}', names)
    assert r and r[0]["function"]["arguments"] == {"query": "q"}
    # beat 30: the tool named inside the arguments
    r = salvage_tool_calls('```json\n{"name": "tool", "arguments": {"type": "recall", "query": "q", "top_k": 3}}\n```', names)
    assert [(c["function"]["name"], c["function"]["arguments"]) for c in r] == [("recall", {"query": "q", "top_k": 3})]


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); n += 1; print(f"PASS {name}")
    print(f"\n{n} passed")


def test_compaction_leaves_room_for_the_answer_and_never_touches_the_beings_own_frame():
    """THE SEED FITTING IS NOT ENOUGH (Legion, 2026-09-07). heartbeat.fit_to_window sizes
    the FIRST prompt; the loop then grows it with every tool result. Measured with that
    guard already live: seed 11,887 tokens, 13,803 on the next step, and 13,803 + 2,581 ==
    16,384 exactly, done_reason "length" — the answer cut off mid-sentence. Across 506
    generates every length-stop satisfies prompt + eval == num_ctx.

    Only tool RESULT bodies are elided, oldest first, with a marker the being can read. The
    system prompt, the first user turn (its state, posture, entrustment), assistant turns
    and the two most recent tool results are never touched: those are what it reasons WITH,
    and an elision it could not see would be worse than the truncation it replaces."""
    from sage.gateway.being_tool_loop import compact_convo

    class _LLM:
        num_ctx = 16384

    # Sized so that eliding the three older results is exactly enough (budget = (16384-6144)
    # tokens * 3.4 - 4000 uncounted chars = 30,816): 43,600 before, 34,600 after two, ~30,400
    # after three. The case where even that is not enough — the newest then yields too —
    # is pinned in test_added_chars_are_counted_dense_and_the_newest_result_yields_last.
    msgs = ([{"role": "system", "content": "S" * 6600},
             {"role": "user", "content": "U" * 15000}]
            + [m for _ in range(4) for m in
               ({"role": "assistant", "content": "A" * 500}, {"role": "tool", "content": "T" * 5000})])
    out, elided = compact_convo(msgs, _LLM())

    assert len(elided) == 3, "every tool result but the most recent"
    assert [e["index"] for e in elided] == [3, 5, 7]
    assert sum(len(m["content"]) for m in out) < sum(len(m["content"]) for m in msgs)
    assert out[0]["content"] == msgs[0]["content"], "system prompt untouched"
    assert out[1]["content"] == msgs[1]["content"], "the being's own frame untouched"
    assert out[9]["content"] == "T" * 5000, "the most recent is kept whole"
    assert "to leave room for your answer" in out[7]["content"], "the one before it is not protected"
    for i in (2, 4, 6, 8):
        assert out[i]["content"] == "A" * 500, "assistant turns untouched"
    assert "elided from the middle to leave room for your answer" in out[3]["content"], "the being is told"
    assert "read the source again" in out[3]["content"], "and told what to do about it"

    # a conversation that already fits is returned untouched, with nothing reported
    small = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    assert compact_convo(small, _LLM()) == (small, [])
    # an unknown window is not a licence to elide
    class _NoCtx:
        num_ctx = None
    assert compact_convo(msgs, _NoCtx()) == (msgs, [])


def test_compaction_reports_exactly_what_it_removed():
    """GPT review of #56, point 5: kept body[:400] but reported len-160 — every elision
    overstated by 240 chars in the record and in the marker the being reads. Pin the
    accounting identity: original == kept + elided, and the marker says the same number."""
    from sage.gateway.being_tool_loop import compact_convo, COMPACT_KEEP_CHARS
    import re

    class _LLM:
        num_ctx = 16384
    body = "T" * 9000
    msgs = ([{"role": "system", "content": "S" * 6600}, {"role": "user", "content": "U" * 30000}]
            + [{"role": "assistant", "content": "A"}, {"role": "tool", "content": body},
               {"role": "assistant", "content": "A"}, {"role": "tool", "content": "last" * 10}])
    out, elided = compact_convo(msgs, _LLM())
    assert len(elided) == 1
    e = elided[0]
    assert e["kept"] == COMPACT_KEEP_CHARS
    assert e["kept"] + e["chars"] == len(body), "original == kept + elided"
    marker = re.search(r"\[… (\d+) characters elided", out[3]["content"])
    assert marker and int(marker.group(1)) == e["chars"], "the marker and the record agree"
    assert out[3]["content"].startswith(body[:COMPACT_KEEP_CHARS // 2])          # head half
    assert out[3]["content"].endswith(body[-(COMPACT_KEEP_CHARS - COMPACT_KEEP_CHARS // 2):])  # tail half



def test_length_retry_changes_the_prompt_it_resends():
    """Legion 2026-09-08, five beats: first attempt cut at the wall mid-deliberation
    (20812 + 3764 == num_ctx), retry with the IDENTICAL prompt produced the IDENTICAL
    3764 tokens. A deterministic model given the same input twice is a loop, not a retry.
    The retry appends a harness turn naming what happened and asking for one tool call."""
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
    seen = []

    class FakeLLM:
        max_response_tokens = 3000
        num_ctx = 24576
        num_predict_override = None

        def get_chat_response(self, messages, tools=None):
            seen.append([dict(m) for m in messages])
            if len(seen) == 1:
                return {"content": "", "tool_calls": [],
                        "raw": {"done_reason": "length", "prompt_eval_count": 20812, "eval_count": 3764,
                                "message": {"thinking": "Actually wait — let me reconsider"}}}
            return {"content": "acted", "tool_calls": [],
                    "raw": {"done_reason": "stop", "prompt_eval_count": 20900, "eval_count": 60, "message": {}}}

    r = run_ollama_tool_turn(_client(OK_DISPATCH), FakeLLM(), [{"role": "user", "content": "beat"}])
    assert r.reply == "acted" and len(seen) == 2
    assert seen[0] == [{"role": "user", "content": "beat"}]
    assert seen[1][:1] == seen[0] and len(seen[1]) == 2                 # same prompt PLUS the nudge
    nudge = seen[1][-1]
    assert nudge["role"] == "user" and nudge["content"].startswith("[harness]")
    assert "3764 tokens" in nudge["content"] and "one tool call" in nudge["content"]
    assert r.generates[-1]["nudged"] is True and r.generates[-1]["retried"] == 1



def test_compaction_is_anchored_on_the_measured_prompt():
    """Legion 20:01Z 2026-09-08: the loop's chars/3.4 estimate said ~19k while the server
    had counted 22,720; the next memory_write body was cut mid-JSON. With a measurement
    the estimate starts from the server's number and only the delta rides the guess."""
    from sage.gateway.being_tool_loop import compact_convo, _est_tokens, _ANSWER_RESERVE

    class LLM:
        num_ctx = 24576
    body = "r" * 12_000
    msgs = [{"role": "system", "content": "s" * 1000}, {"role": "user", "content": "u" * 30_000},
            {"role": "assistant", "content": ""}, {"role": "tool", "content": body},
            {"role": "assistant", "content": ""}, {"role": "tool", "content": body},
            {"role": "assistant", "content": ""}, {"role": "tool", "content": body}]
    chars = sum(len(m["content"]) for m in msgs)                     # 67,000
    # unmeasured: (67000 + 4000) / 3.4 = 20.9k + 6144 > 24576 -> compacts
    out, el = compact_convo(msgs, LLM())
    assert el, "unmeasured estimate must still guard"
    # measured: the server counted 13,000 tokens for a 55,000-char prompt one step ago;
    # 12,000 new chars at the dense ratio -> 13,000 + 4,800 = 17.8k + 6144 < 24576 -> nothing to do
    out, el = compact_convo(msgs, LLM(), measured=(13_000, 55_000))
    assert el == [] and out is msgs
    # measured HIGH (code reads tokenize dense): 21,000 for 55,000 -> 24.5k -> compacts
    out, el = compact_convo(msgs, LLM(), measured=(21_000, 55_000))
    assert len(el) == 2 and out[3]["content"].startswith("r" * 200) and out[3]["content"].endswith("r" * 200)
    assert out[7]["content"] == body
    assert _est_tokens(sum(len(m["content"]) for m in out), (21_000, 55_000)) <= 24576 - _ANSWER_RESERVE


def test_loop_feeds_the_previous_prompt_count_into_compaction():
    from sage.gateway import being_tool_loop as L
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
    seen = []
    orig = L.compact_convo

    def spy(msgs, llm, reserve=L._ANSWER_RESERVE, measured=None):
        seen.append(measured)
        return orig(msgs, llm, reserve, measured)
    L.compact_convo = spy
    try:
        class FakeLLM:
            num_ctx = 24576

            def get_chat_response(self, messages, tools=None):
                if len(seen) == 1:
                    return {"content": "", "tool_calls": [{"function": {"name": "recall", "arguments": {"query": "x"}}}],
                            "raw": {"done_reason": "stop", "prompt_eval_count": 17_541, "eval_count": 100, "message": {}}}
                return {"content": "done", "tool_calls": [],
                        "raw": {"done_reason": "stop", "prompt_eval_count": 18_000, "eval_count": 10, "message": {}}}
        r = run_ollama_tool_turn(_client(OK_DISPATCH), FakeLLM(), [{"role": "user", "content": "beat"}])
    finally:
        L.compact_convo = orig
    assert r.reply == "done"
    assert seen[0] is None                                   # nothing measured before the first generate
    assert seen[1][0] == 17_541 and seen[1][1] == len("beat")  # the server's count for the prompt as sent



def test_compaction_keeps_the_tail_where_a_verdict_lives():
    """legion-being 20:41Z 2026-09-08: `check` FAILed at step 1; by the time it spoke the
    result had been elided to its head and the FAILED line was gone from its view."""
    from sage.gateway.being_tool_loop import compact_convo, COMPACT_KEEP_CHARS

    class LLM:
        num_ctx = 4000
    check_out = "x" * 6000 + "\nFAILED tests/test_a.py::test_b\n1 failed, 182 passed"
    msgs = [{"role": "user", "content": "u" * 3000},
            {"role": "assistant", "content": ""}, {"role": "tool", "content": check_out},
            {"role": "assistant", "content": ""}, {"role": "tool", "content": "y" * 3000}]
    out, el = compact_convo(msgs, LLM())
    c = out[2]["content"]
    assert "FAILED tests/test_a.py::test_b" in c and "1 failed, 182 passed" in c
    assert c.startswith("x" * (COMPACT_KEEP_CHARS // 2)) and "elided from the middle" in c
    assert el[0]["chars"] == len(check_out) - COMPACT_KEEP_CHARS   # accounting: kept + elided == original



def test_transport_error_retry_asks_for_a_shorter_body():
    """20:33Z 2026-09-08 reflect: journal body cut mid-JSON (Ollama 500 "unexpected end of
    JSON input"), retried with the identical prompt, cut identically, nothing recorded."""
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
    seen = []

    class FakeLLM:
        max_response_tokens = 3000
        num_ctx = 24576
        num_predict_override = None

        def get_chat_response(self, messages, tools=None):
            seen.append([dict(m) for m in messages])
            if len(seen) == 1:
                return {"content": "[OllamaIRP: Connection error: HTTP Error 500: Internal Server Error — "
                                   "{\"error\":\"llama-server returned invalid tool call arguments for "
                                   "\\\"memory_write\\\": unexpected end of JSON input\"}]",
                        "tool_calls": [], "raw": {}}
            return {"content": "shorter entry written", "tool_calls": [],
                    "raw": {"done_reason": "stop", "prompt_eval_count": 21000, "eval_count": 300, "message": {}}}

    r = run_ollama_tool_turn(_client(OK_DISPATCH), FakeLLM(), [{"role": "user", "content": "reflect"}])
    assert r.reply == "shorter entry written" and len(seen) == 2
    nudge = seen[1][-1]
    assert nudge["role"] == "user" and nudge["content"].startswith("[harness]") and "third of the length" in nudge["content"]
    assert r.generates[-1]["nudged"] is True and r.generates[-1]["retried"] == 1



def test_added_chars_are_counted_dense_and_the_newest_result_yields_last():
    """03:27Z 2026-09-09: a 12,116-char JSON read took the prompt 19,620 -> 24,466 (2.5
    chars/token); the estimate at 3.4 said ~21k, the older results were already stubs, the
    newest was protected, and the generate was cut at the wall with nothing said."""
    from sage.gateway.being_tool_loop import compact_convo, _est_tokens, _CPT_ADDED, COMPACT_KEEP_CHARS

    assert _est_tokens(55_000 + 12_116, (19_620, 55_000)) == 19_620 + 12_116 / _CPT_ADDED
    assert _est_tokens(55_000 - 3_400, (19_620, 55_000)) == 19_620 - 1_000       # removals counted light

    class LLM:
        num_ctx = 24576
    big = "{" + "j" * 12_000 + "}"
    msgs = [{"role": "user", "content": "u" * 50_000},
            {"role": "assistant", "content": ""}, {"role": "tool", "content": "old" * 300},
            {"role": "assistant", "content": ""}, {"role": "tool", "content": big}]
    # the server counted 19,620 for the prompt before `big` was appended
    chars_before = sum(len(m["content"]) for m in msgs[:-1])
    out, el = compact_convo(msgs, LLM(), measured=(19_620, chars_before))
    newest = out[-1]["content"]
    assert newest != big and "NEWEST result" in newest
    assert newest.startswith("{" + "j" * (COMPACT_KEEP_CHARS * 2 - 1)) and newest.endswith("j" * (COMPACT_KEEP_CHARS * 2 - 1) + "}")
    assert el[-1]["newest"] is True and el[-1]["kept"] == COMPACT_KEEP_CHARS * 4
    assert el[-1]["chars"] + el[-1]["kept"] == len(big)                          # accounting holds



def test_deadline_stops_issuing_steps_and_closes_in_words():
    """04:30Z 2026-09-09: eight steps of long thinking took 36 min, reflect began, the
    unit's 45-min timeout killed the beat. A deadline ends explore in time, in words."""
    import time
    from sage.gateway.being_tool_loop import run_tool_turn
    calls = []

    def gen(convo):
        calls.append([m.get("content", "")[:20] for m in convo])
        if any("[harness] The time budget" in (m.get("content") or "") for m in convo):
            return {"content": "closing: did one thing, want two next beat", "intents": []}
        return {"content": "", "intents": [BeingIntent("witness", {"event": "x"})]}

    r = run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "beat"}],
                      max_steps=8, deadline=time.time() - 1)          # already past: one step, then close
    assert r.steps == 1 and r.capped and r.deadline_hit
    assert len(r.trace) == 1 and r.reply.startswith("closing")
    assert "[harness] The time budget" in calls[-1][-1] or any("[harness]" in c for c in calls[-1])
    r2 = run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "beat"}],
                       max_steps=3, deadline=time.time() + 3600)      # far away: normal cap
    assert r2.steps == 3 and r2.capped and not r2.deadline_hit



# -- the metabolic beat: work while there is work, and hear the world while working -----
#
# dp, 2026-09-09: "1. a message from you or me wakes it immediately to respond 2. it should
# be able to continue as long as it wishes 3. activity resets the beat timer 4. if timer
# reaches the beat interval, we wake it. so basically it works while there's something to
# do, beat wakes it after set period of inactivity."
def test_an_uncapped_turn_runs_until_the_being_stops_asking():
    """A step count was never a statement about the work — it was a guess at how much work
    there would be, applied as a limit. max_steps=0 removes the guess."""
    from sage.gateway.being_tool_loop import run_tool_turn
    import time
    calls = {"n": 0}

    def gen(convo):
        calls["n"] += 1
        if calls["n"] <= 20:
            return {"content": "", "intents": [BeingIntent("witness", {"event": f"step{calls['n']}"})]}
        return {"content": "done after twenty", "intents": []}

    r = run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "go"}],
                      max_steps=0, deadline=time.time() + 3600)
    assert r.reply == "done after twenty" and not r.capped
    assert r.steps == 20 and len(r.trace) == 20      # far past the old cap of 8


def test_an_uncapped_turn_without_a_clock_gets_a_safety_ceiling():
    """"As long as it wishes" is bounded by a resource, not by nothing."""
    from sage.gateway.being_tool_loop import run_tool_turn, _UNCAPPED_SAFETY_CEILING

    def gen(convo):
        return {"content": "", "intents": [BeingIntent("witness", {"event": "x"})]}

    r = run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "go"}], max_steps=0)
    assert r.capped and r.steps == _UNCAPPED_SAFETY_CEILING
    assert any("safety ceiling" in str(i.get("note", "")) for i in r.interjected)


def test_a_message_arriving_mid_turn_reaches_the_being_between_steps():
    """The conversation block is composed at beat start, so before this a turn arriving
    while the being worked waited for the next beat — which under a two-hour beat is the
    opposite of waking it immediately."""
    from sage.gateway.being_tool_loop import run_tool_turn
    import time
    mail = ["", "dp: are you there?", "", ""]
    seen = []

    def interject():
        return mail.pop(0) if mail else ""

    def gen(convo):
        seen.append([m.get("content", "") for m in convo])
        if len(seen) <= 3:
            return {"content": "", "intents": [BeingIntent("witness", {"event": "w"})]}
        return {"content": "ok", "intents": []}

    r = run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "beat"}],
                      max_steps=0, deadline=time.time() + 3600, interject=interject)
    assert r.reply == "ok"
    delivered = [c for c in seen[-1] if "a message arrived while you were working" in c]
    assert len(delivered) == 1 and "dp: are you there?" in delivered[0]
    # it was NOT delivered before the first generate: the seed already carried the state
    assert not any("a message arrived" in c for c in seen[0])
    assert r.interjected and r.interjected[0]["chars"] == len("dp: are you there?")


def test_a_broken_mailbox_does_not_end_the_beat():
    from sage.gateway.being_tool_loop import run_tool_turn
    import time

    def interject():
        raise RuntimeError("conversation store is locked")

    def gen(convo):
        return {"content": "", "intents": [BeingIntent("witness", {"event": "w"})]} \
            if len(convo) < 6 else {"content": "still fine", "intents": []}

    r = run_tool_turn(_client(OK_DISPATCH), gen, [{"role": "user", "content": "beat"}],
                      max_steps=0, deadline=time.time() + 3600, interject=interject)
    assert r.reply == "still fine"
    assert any("RuntimeError" in str(i.get("error", "")) for i in r.interjected)
