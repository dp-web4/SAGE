"""An empty turn's whole thinking is kept where it can be read (being_tool_loop.keep_empty_thinking)."""
import os
import time

from sage.gateway import being_tool_loop as btl


def test_keeps_the_whole_thinking_with_its_counts(tmp_path):
    thinking = "Wait — " + "x" * 30_000          # far past the 200 / 4,000 char views
    rel = btl.keep_empty_thinking(str(tmp_path),
                                  {"done_reason": "length", "prompt_eval_count": 24938,
                                   "eval_count": 7830},
                                  {"thinking": thinking, "content": ""})
    assert rel and rel.startswith(btl.EMPTY_THINKING_DIR + "/")
    body = (tmp_path / rel).read_text(encoding="utf-8")
    assert body.startswith("done_reason=length prompt_eval=24938 eval=7830 chars=30007\n")
    assert body.endswith(thinking)


def test_nothing_to_keep_or_nowhere_to_keep_it(tmp_path):
    assert btl.keep_empty_thinking(None, {}, {"thinking": "t"}) is None
    assert btl.keep_empty_thinking(str(tmp_path), {}, {"thinking": "  "}) is None
    assert not (tmp_path / btl.EMPTY_THINKING_DIR).exists()


def test_old_files_age_out_new_ones_stay(tmp_path):
    d = tmp_path / btl.EMPTY_THINKING_DIR
    d.mkdir(parents=True)
    old, fresh = d / "old.txt", d / "fresh.txt"
    old.write_text("o"); fresh.write_text("f")
    t = time.time() - btl.EMPTY_THINKING_KEEP_S - 60
    os.utime(old, (t, t))
    btl.keep_empty_thinking(str(tmp_path), {}, {"thinking": "new"})
    assert not old.exists() and fresh.exists()


def test_a_failed_write_never_raises(tmp_path):
    blocker = tmp_path / "scratch"
    blocker.write_text("a file where the directory should be")
    assert btl.keep_empty_thinking(str(tmp_path), {}, {"thinking": "t"}) is None


def test_the_loop_calls_it_on_an_empty_turn():
    src = open(btl.__file__, encoding="utf-8").read()
    i = src.index('print(f"[tool-loop] EMPTY turn:')
    assert "keep_empty_thinking(" in src[i:i + 1200]


def test_the_retry_names_where_the_deliberation_was_kept(tmp_path):
    """legion-being 2026-10-05: six of six kept empty turns drafted the code it meant to write,
    18-28k chars, cut before the write; the retry said 'act now' and nothing about the draft."""
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
    from sage.gateway.tests.test_being_tool_loop import _client, OK_DISPATCH
    seen = []
    draft = "def parse_entries(text):\n    ...\n" * 400

    class FakeLLM:
        max_response_tokens = 3000
        num_ctx = 32768
        num_predict_override = None
        think = True

        def get_chat_response(self, messages, tools=None):
            seen.append(str(messages[-1].get("content", "")))
            if len(seen) == 1:
                return {"content": "", "tool_calls": [],
                        "raw": {"done_reason": "length", "prompt_eval_count": 25739,
                                "eval_count": 7029,
                                "message": {"content": "", "thinking": draft}}}
            return {"content": "done", "tool_calls": [],
                    "raw": {"done_reason": "stop", "prompt_eval_count": 14146,
                            "eval_count": 12, "message": {}}}

    client = _client(OK_DISPATCH)
    client.memory_root = str(tmp_path)
    run_ollama_tool_turn(client, FakeLLM(), [{"role": "user", "content": "hi"}])
    assert len(seen) == 2
    kept = sorted((tmp_path / btl.EMPTY_THINKING_DIR).iterdir())
    assert len(kept) == 1 and kept[0].read_text(encoding="utf-8").endswith(draft)
    rel = f"{btl.EMPTY_THINKING_DIR}/{kept[0].name}"
    assert rel in seen[1] and "memory_read" in seen[1], seen[1]
    assert "one tool call" in seen[1]


def test_no_root_no_claim(tmp_path):
    """Without a memory root nothing is kept, and the nudge must not name a file."""
    from sage.gateway.being_tool_loop import run_ollama_tool_turn
    from sage.gateway.tests.test_being_tool_loop import _client, OK_DISPATCH
    seen = []

    class FakeLLM:
        max_response_tokens = 3000
        num_ctx = 32768
        num_predict_override = None
        think = True

        def get_chat_response(self, messages, tools=None):
            seen.append(str(messages[-1].get("content", "")))
            if len(seen) == 1:
                return {"content": "", "tool_calls": [],
                        "raw": {"done_reason": "length", "prompt_eval_count": 25000,
                                "eval_count": 7000,
                                "message": {"content": "", "thinking": "a long draft"}}}
            return {"content": "done", "tool_calls": [], "raw": {"done_reason": "stop", "message": {}}}

    client = _client(OK_DISPATCH)
    client.memory_root = None
    run_ollama_tool_turn(client, FakeLLM(), [{"role": "user", "content": "hi"}])
    assert "saved as" not in seen[1] and "one tool call" in seen[1]
