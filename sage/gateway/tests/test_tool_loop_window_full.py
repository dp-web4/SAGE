"""A prompt the window cannot hold is never sent, and a server cut is not a measurement.

Sprout, 2026-09-06..10-15: about 16 explore beats got an HTTP 400 instead of a reply. Compaction
cannot touch the system prompt or the first user turn (~14k tokens there, against a 10,240 target
at num_ctx 16,384), so the loop grew past the window; Ollama dropped messages off the front, the
only user turn with them, and the qwen template raised "No user query found in messages". The 400
text became the beat's reply. Hermetic: a fake LLM and a recording client, no model, no gate."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
from sage.gateway.being_gate_client import ResultEnvelope  # noqa: E402
from sage.gateway.being_tool_loop import (run_ollama_tool_turn, WINDOW_SEND_MARGIN,  # noqa: E402
                                          SERVER_CUT_RATIO, PREFLIGHT_CPT, _UNCOUNTED_CHARS)

NO_USER_400 = ("[OllamaIRP: Connection error: HTTP Error 400: Bad Request — {\"error\":\"Unable to generate "
               "parser for this template. ... raise_exception('No user query found in messages.') ...\"}]")


class _Client:
    """Dispatches every call and returns a fixed-size result (under the elision floor, so
    compaction cannot free room and the window arithmetic in each test is exact)."""
    def __init__(self, result_chars=480):
        self.calls = []
        self.result = "x" * result_chars

    def dispatch(self, intent):
        self.calls.append(intent.effector)
        return ResultEnvelope(ok=True, result=self.result)


def _call(n):
    return [{"function": {"name": "witness", "arguments": {"event": f"step {n}"}}}]


class _LLM:
    """Scripted replies; records every list it was actually sent."""
    num_ctx = 16384

    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []

    def get_chat_response(self, messages, tools=None, **kw):
        self.sent.append(list(messages))
        return self.replies.pop(0)


def test_a_prompt_over_the_window_is_not_sent_and_the_turn_ends_with_no_words():
    # step 1 measures 16,100 of 16,384; the next step adds a tool result, which puts the
    # anchored estimate past num_ctx - WINDOW_SEND_MARGIN, so step 2 is never sent.
    llm = _LLM([{"content": "", "tool_calls": _call(1), "raw": {"prompt_eval_count": 16100, "eval_count": 20}}])
    r = run_ollama_tool_turn(_Client(), llm, [{"role": "user", "content": "go"}], max_steps=4)
    assert len(llm.sent) == 1, "the over-window prompt must not reach the server"
    assert r.window_full and r.window_full["cause"] == "over_window"
    assert r.window_full["estimated_prompt"] > llm.num_ctx - WINDOW_SEND_MARGIN
    assert r.reply == "", "nothing is said in the being's name"
    assert r.generates[-1]["window_full"] == "over_window"
    assert len(r.thinking) == len(r.generates), "one thinking entry per generate, as before"


def test_an_oversized_first_step_is_refused_on_the_preflight_estimate():
    # No server count yet. A 60,000-char seed at num_ctx 16,384 is ~25k tokens on the preflight
    # estimate: sent, Ollama would cut the front and the only user turn with it. It is not sent.
    llm = _LLM([{"content": "should not be reached", "tool_calls": []}])
    seed = [{"role": "system", "content": "s" * 60000}, {"role": "user", "content": "go"}]
    r = run_ollama_tool_turn(_Client(), llm, seed, max_steps=2, tools=[])
    assert llm.sent == [], "the oversized first prompt must not reach the server"
    assert r.window_full and r.window_full["cause"] == "preflight" and r.window_full["step"] == 0
    assert r.window_full["estimated_prompt"] > llm.num_ctx - WINDOW_SEND_MARGIN
    assert r.reply == ""


def test_a_seed_the_size_of_a_real_fitted_one_is_still_sent():
    # Sprout's real step-1 prompts measured up to 14,306 tokens at num_ctx 16,384: at the ~3.14
    # chars/token measured on its seeds that is ~45k chars, ~32k of them in messages. The
    # preflight puts that at ~15.5k, under the line, so a beat the heartbeat fitter accepted runs.
    llm = _LLM([{"content": "done", "tool_calls": [], "raw": {"prompt_eval_count": 14306, "eval_count": 5}}])
    seed = [{"role": "system", "content": "s" * 31950}, {"role": "user", "content": "go"}]
    est = (sum(len(m["content"]) for m in seed) + _UNCOUNTED_CHARS) / PREFLIGHT_CPT
    assert est < llm.num_ctx - WINDOW_SEND_MARGIN
    r = run_ollama_tool_turn(_Client(), llm, seed, max_steps=2, tools=[])
    assert len(llm.sent) == 1 and r.reply == "done" and r.window_full is None


def test_the_preflight_errs_high_against_every_ratio_measured_on_this_being():
    # 3.026..3.152 chars/token over 60 beats: an estimate at PREFLIGHT_CPT over-counts them all.
    assert PREFLIGHT_CPT < 3.026


def test_no_user_query_400_is_not_retried_and_never_becomes_the_reply():
    llm = _LLM([{"content": "", "tool_calls": _call(1), "raw": {"prompt_eval_count": 9000, "eval_count": 20}},
                {"content": NO_USER_400, "tool_calls": []}])
    r = run_ollama_tool_turn(_Client(), llm, [{"role": "user", "content": "go"}], max_steps=4)
    assert len(llm.sent) == 2, "the same list cannot succeed again: no transport retry"
    assert r.reply == "" and "OllamaIRP" not in r.reply
    assert r.window_full and r.window_full["cause"] == "server_cut"


def test_other_transport_errors_are_still_retried_once():
    llm = _LLM([{"content": "[OllamaIRP: Connection error: HTTP Error 500: invalid tool call arguments]",
                 "tool_calls": []},
                {"content": "done", "tool_calls": [], "raw": {"prompt_eval_count": 100, "eval_count": 5}}])
    r = run_ollama_tool_turn(_Client(), llm, [{"role": "user", "content": "go"}], max_steps=2, tools=[])
    assert len(llm.sent) == 2 and r.reply == "done" and r.window_full is None


def test_a_count_far_below_what_was_sent_is_not_stored_and_its_reply_is_not_acted_on():
    # Step 2's count (8,172) is what survived a server cut of a ~16k list. It is not stored as
    # the measurement, and the reply the model gave to the cut prompt is not the being's act:
    # its call is not run and the phase ends as a full window (it used to run, CBP 2026-10-21).
    client = _Client()
    llm = _LLM([{"content": "", "tool_calls": _call(1), "raw": {"prompt_eval_count": 15800, "eval_count": 20}},
                {"content": "", "tool_calls": _call(2), "raw": {"prompt_eval_count": 8172, "eval_count": 20}},
                {"content": "should not be reached", "tool_calls": [], "raw": {"prompt_eval_count": 8400}}])
    r = run_ollama_tool_turn(client, llm, [{"role": "user", "content": "go"}], max_steps=5)
    cut = r.generates[1].get("server_cut")
    assert cut and cut["counted"] == 8172 and cut["counted"] < SERVER_CUT_RATIO * cut["expected"]
    assert r.generates[1].get("window_full") == "server_cut"
    assert len(llm.sent) == 2
    assert client.calls == ["witness"], "step 1's call ran; the cut step's call did not"
    assert r.window_full and r.window_full["cause"] == "server_cut" and r.reply == ""
    assert r.seed_measured[0] == 15800, "the cut count is never the anchor handed on"


def _seed(chars):
    return [{"role": "system", "content": "s" * chars}, {"role": "user", "content": "go"}]


def test_a_phase_anchored_on_the_previous_count_refuses_step_one_the_preflight_would_send():
    # Explore counted the seed at 15,900 tokens. Posture's prompt is that seed plus ~1,000 chars
    # (the record and the posture turn): anchored, ~16.3k, over the line, not sent. The preflight
    # guess on the same list would have said ~15.6k and sent it.
    seed = _seed(31950)
    seed_chars = sum(len(m["content"]) for m in seed)
    convo = seed + [{"role": "user", "content": "r" * 1000}]
    pre = (sum(len(m["content"]) for m in convo) + _UNCOUNTED_CHARS) / PREFLIGHT_CPT
    assert pre < 16384 - WINDOW_SEND_MARGIN, "the unanchored guess would have sent this"
    llm = _LLM([{"content": "should not be reached", "tool_calls": []}])
    r = run_ollama_tool_turn(_Client(), llm, convo, max_steps=2, tools=[], anchor=(15900, seed_chars))
    assert llm.sent == []
    assert r.window_full and r.window_full["cause"] == "over_window" and r.window_full["step"] == 0


def test_an_anchored_step_one_counted_at_half_is_a_cut_and_its_calls_are_not_run():
    # The CBP posture shape: a ~14.6k seed, a step-1 count of 8,260. Unanchored this read as a
    # good reply and its say/peer_ask went out; anchored it is a cut, and nothing is run.
    seed = _seed(31950)
    seed_chars = sum(len(m["content"]) for m in seed)
    client = _Client()
    llm = _LLM([{"content": "", "tool_calls": _call(1), "raw": {"prompt_eval_count": 8260, "eval_count": 20}}])
    r = run_ollama_tool_turn(client, llm, seed + [{"role": "user", "content": "posture"}],
                             max_steps=2, anchor=(14600, seed_chars))
    assert len(llm.sent) == 1 and client.calls == []
    assert r.window_full and r.window_full["cause"] == "server_cut"
    assert r.generates[0]["server_cut"]["counted"] == 8260
    assert r.seed_measured is None, "a phase whose only count was cut hands on no anchor"


def test_a_phase_hands_on_its_first_whole_count_as_the_next_phases_anchor():
    llm = _LLM([{"content": "", "tool_calls": _call(1), "raw": {"prompt_eval_count": 9000, "eval_count": 20}},
                {"content": "done", "tool_calls": [], "raw": {"prompt_eval_count": 9300, "eval_count": 5}}])
    seed = [{"role": "user", "content": "go"}]
    r = run_ollama_tool_turn(_Client(), llm, seed, max_steps=3)
    assert r.seed_measured == (9000, sum(len(m["content"]) for m in llm.sent[0]))


def test_the_heartbeat_hands_explores_seed_count_to_posture():
    import inspect
    from sage.gateway import heartbeat as H
    src = inspect.getsource(H)
    assert 'anchor=getattr(explore, "seed_measured", None)' in src


def test_the_beat_record_says_the_window_filled_and_that_nothing_the_being_did_caused_it():
    from types import SimpleNamespace
    from sage.gateway import heartbeat as H
    res = SimpleNamespace(trace=[], reply="", window_full={"cause": "over_window"})
    text = H._beat_record_text(res)
    assert "context window filled" in text and "Nothing you did caused it" in text
    assert H._beat_record_text(SimpleNamespace(trace=[], reply="", window_full=None)) == \
        "You called no tools this beat."
    carried = H._carry([], res)
    assert carried[-1]["role"] == "assistant" and "context window filled" in carried[-1]["content"]


class _LlamaLLM(_LLM):
    """Ollama's llama3.1 template: the tool schemas ride only on a prompt whose last message is a
    user turn, so a step after a tool result counts thousands of tokens fewer (pub, 2026-10-21)."""
    num_ctx = 12288
    tools_on_last_user_only = True


def test_a_template_that_drops_the_tools_after_a_tool_turn_is_not_read_as_a_cut():
    # pub-being's shape: step 1 counted 10,006 with the schemas, step 2 5,580 without them. Judged
    # against step 1 that is a "cut", and every explore from 2026-10-21 08:13Z ended after one act.
    client = _Client()
    llm = _LlamaLLM([{"content": "", "tool_calls": _call(1), "raw": {"prompt_eval_count": 10006, "eval_count": 18}},
                     {"content": "", "tool_calls": _call(2), "raw": {"prompt_eval_count": 5580, "eval_count": 17}},
                     {"content": "done", "tool_calls": [], "raw": {"prompt_eval_count": 5760, "eval_count": 5}}])
    r = run_ollama_tool_turn(client, llm, [{"role": "user", "content": "go"}], max_steps=5)
    assert not any(g.get("server_cut") for g in r.generates)
    assert client.calls == ["witness", "witness"], "step 2's call runs"
    assert r.window_full is None and r.reply == "done"
    assert r.seed_measured[0] == 10006, "the anchor handed on is the count WITH the schemas"


def test_on_that_template_a_real_cut_is_still_caught_against_its_own_kind():
    client = _Client()
    llm = _LlamaLLM([{"content": "", "tool_calls": _call(1), "raw": {"prompt_eval_count": 10006, "eval_count": 18}},
                     {"content": "", "tool_calls": _call(2), "raw": {"prompt_eval_count": 5580, "eval_count": 17}},
                     {"content": "", "tool_calls": _call(3), "raw": {"prompt_eval_count": 2500, "eval_count": 17}}])
    r = run_ollama_tool_turn(client, llm, [{"role": "user", "content": "go"}], max_steps=5)
    assert r.generates[2]["server_cut"]["counted"] == 2500
    assert client.calls == ["witness", "witness"], "the cut step's call does not run"
    assert r.window_full and r.window_full["cause"] == "server_cut"


def test_on_that_template_an_anchored_step_one_is_still_judged():
    # posture after explore: its prompt ends in a user turn, the same kind as explore's seed count
    seed = _seed(31950)
    client = _Client()
    llm = _LlamaLLM([{"content": "", "tool_calls": _call(1), "raw": {"prompt_eval_count": 5000, "eval_count": 20}}])
    r = run_ollama_tool_turn(client, llm, seed + [{"role": "user", "content": "posture"}], max_steps=2,
                             anchor=(10006, sum(len(m["content"]) for m in seed)))
    assert client.calls == [] and r.window_full and r.window_full["cause"] == "server_cut"


def test_the_llama31_config_declares_it_and_others_do_not():
    from sage.irp.adapters.model_capabilities import load_capabilities
    assert load_capabilities("llama3.1:8b").tools_on_last_user_only is True
    assert load_capabilities("qwen3.5:27b").tools_on_last_user_only is False
