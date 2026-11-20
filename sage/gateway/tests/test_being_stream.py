"""The being's output as it is produced (being_stream), and the streamed call that feeds it.

dp, 2026-11-20: the agent's stream is a key feature and liveness indicator in every major CLI harness, and SAGE had
none: a beat called the model with stream off, so nothing it produced showed until each call returned."""
import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from sage.gateway import being_stream as bs

CHUNKS = [
    {"message": {"role": "assistant", "content": "", "thinking": "The kettle "}, "done": False},
    {"message": {"role": "assistant", "content": "", "thinking": "is cold."}, "done": False},
    {"message": {"role": "assistant", "content": "I will "}, "done": False},
    {"message": {"role": "assistant", "content": "look."}, "done": False},
    {"message": {"role": "assistant", "content": "",
                 "tool_calls": [{"function": {"name": "camera", "arguments": {"why": "see the room"}}}]},
     "done": False},
    {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop",
     "prompt_eval_count": 1200, "eval_count": 42, "total_duration": 5},
]
JOINED = {"role": "assistant", "content": "I will look.", "thinking": "The kettle is cold.",
          "tool_calls": [{"function": {"name": "camera", "arguments": {"why": "see the room"}}}]}


def _events(home):
    return [json.loads(l) for l in (Path(home) / bs.STREAM_FILE).read_text().splitlines()]


@pytest.fixture(autouse=True)
def _no_current_beat():
    bs._current = None
    yield
    bs._current = None


def test_a_beat_writes_its_calls_thinking_words_tools_and_ending(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "FLUSH_S", 3600)            # gathered until the kind changes
    s = bs.start(tmp_path, "heartbeat-abc", member="test-being", model="m")
    bs.set_turn("explore")
    s.begin_call("tools")
    for c in CHUNKS:
        s.chunk(c["message"])
    s.end_call(CHUNKS[-1], "I will look.")
    bs.stop()
    ev = _events(tmp_path)
    kinds = [(e["k"], e.get("s") or e.get("name") or e.get("turn") or "") for e in ev]
    assert kinds == [("beat", ""), ("call", "explore"), ("think", "The kettle is cold."), ("text", "I will look."),
                     ("tool", "camera"), ("done", ""), ("end", "")], kinds
    assert all(e["beat"] == "heartbeat-abc" for e in ev)
    assert ev[4]["args"] == '{"why": "see the room"}'
    assert ev[5]["reason"] == "stop" and ev[5]["eval_count"] == 42
    assert bs.current() is None


def test_text_is_written_as_it_comes_not_only_at_the_end(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "FLUSH_S", 0)
    s = bs.start(tmp_path, "b")
    s.begin_call("tools")
    s.chunk({"content": "first "})
    assert _events(tmp_path)[-1] == {**_events(tmp_path)[-1], "k": "text", "s": "first "}, "on disk before the call ends"


def test_a_failed_call_is_written_as_an_error(tmp_path):
    s = bs.start(tmp_path, "b")
    s.begin_call("tools")
    s.end_call({}, "[OllamaIRP: Connection error: refused]")
    assert _events(tmp_path)[-1]["k"] == "error" and "refused" in _events(tmp_path)[-1]["s"]


def test_a_sink_that_cannot_write_never_raises_into_the_beat(tmp_path):
    missing = tmp_path / "gone"                          # no such directory
    s = bs.Stream(missing, "b")
    s.begin_beat(); s.begin_call("tools"); s.chunk({"content": "x"}); s.end_call({"done_reason": "stop"}); s.end_beat()
    assert s._dead and not missing.exists()


def test_the_file_is_kept_bounded_with_one_older_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(bs, "MAX_BYTES", 200)
    (tmp_path / bs.STREAM_FILE).write_text("x" * 300 + "\n")
    bs.start(tmp_path, "b2")
    assert (tmp_path / (bs.STREAM_FILE + ".1")).read_text().startswith("x" * 300)
    assert [e["k"] for e in _events(tmp_path)] == ["beat"]


def test_read_tail_drops_a_line_cut_by_its_window(tmp_path):
    p = tmp_path / bs.STREAM_FILE
    p.write_text("".join(json.dumps({"k": "text", "s": "y" * 50, "n": i}) + "\n" for i in range(20)))
    ev = bs.read_tail(p, max_bytes=300)
    assert ev and ev[-1]["n"] == 19 and all(isinstance(e, dict) for e in ev)


# -- the streamed call ---------------------------------------------------------------------------------------

def test_a_streamed_reply_is_joined_into_the_unstreamed_shape():
    from sage.irp.plugins.ollama_irp import _read_stream
    seen = []
    lines = [json.dumps(c).encode() + b"\n" for c in CHUNKS]
    raw = _read_stream(iter(lines), seen.append, 60)
    assert raw["message"] == JOINED
    assert raw["done_reason"] == "stop" and raw["eval_count"] == 42 and raw["prompt_eval_count"] == 1200
    assert len(seen) == len(CHUNKS), "each piece reached the sink as it came"


def test_a_failing_sink_does_not_change_the_reply():
    from sage.irp.plugins.ollama_irp import _read_stream

    def boom(_):
        raise OSError("disk full")
    raw = _read_stream(iter([json.dumps(c).encode() for c in CHUNKS]), boom, 60)
    assert raw["message"] == JOINED


@pytest.mark.parametrize("lines, says", [
    ([{"error": "model failed to load"}], "model failed to load"),
    (CHUNKS[:3], "ended before its last chunk"),
])
def test_a_stream_that_fails_or_is_cut_is_an_error_not_a_half_reply(lines, says):
    from sage.irp.plugins.ollama_irp import _read_stream
    with pytest.raises(Exception) as e:
        _read_stream(iter([json.dumps(c).encode() for c in lines]), lambda m: None, 60)
    assert says in str(e.value)


class _Ollama(BaseHTTPRequestHandler):
    """/api/chat that answers streamed or not, as the request asks, with the same reply."""
    bodies = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Ollama.bodies.append(body)
        self.send_response(200)
        self.end_headers()
        if body.get("stream"):
            for c in CHUNKS:
                self.wfile.write(json.dumps(c).encode() + b"\n")
                self.wfile.flush()
        else:
            final = dict(CHUNKS[-1]); final["message"] = JOINED
            self.wfile.write(json.dumps(final).encode())

    def log_message(self, *a):
        pass


def _adapter(port):
    from sage.irp.plugins.ollama_irp import OllamaIRP
    llm = OllamaIRP.__new__(OllamaIRP)
    llm.ollama_host, llm.model_name, llm.think, llm.temperature, llm.num_ctx = f"http://127.0.0.1:{port}", "m", True, 0.7, 4096
    llm.timeout_seconds, llm._ollama_available = 30, True
    llm.resolve_num_predict = lambda: 100
    return llm


def test_get_chat_response_streamed_and_unstreamed_return_the_same(tmp_path):
    srv = HTTPServer(("127.0.0.1", 0), _Ollama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        llm = _adapter(srv.server_address[1])
        plain = llm.get_chat_response([{"role": "user", "content": "hi"}])
        got = []
        streamed = llm.get_chat_response([{"role": "user", "content": "hi"}], on_chunk=got.append)
    finally:
        srv.shutdown()
    assert [b.get("stream") for b in _Ollama.bodies[-2:]] == [False, True]
    for k in ("content", "tool_calls", "role"):
        assert streamed[k] == plain[k], k
    assert streamed["raw"]["message"] == plain["raw"]["message"]
    assert streamed["raw"]["done_reason"] == plain["raw"]["done_reason"] and len(got) == len(CHUNKS)


def test_a_beat_streams_through_generate_with_evidence_and_a_plain_adapter_is_untouched(tmp_path):
    from sage.gateway.being_tool_loop import generate_with_evidence

    class Streams:
        def get_chat_response(self, messages, tools=None, fmt=None, on_chunk=None):
            for c in CHUNKS:
                on_chunk(c["message"])
            final = dict(CHUNKS[-1]); final["message"] = JOINED
            return {"content": "I will look.", "tool_calls": JOINED["tool_calls"], "raw": final}

    class Plain:
        def get_chat_response(self, messages, **kw):
            assert "on_chunk" not in kw
            return {"content": "ok", "tool_calls": [], "raw": {"done_reason": "stop"}}

    bs.start(tmp_path, "b")
    bs.set_turn("reflect")
    r, attempt = generate_with_evidence(Streams(), [], phase="tools")
    assert r["content"] == "I will look." and attempt["eval_count"] == 42
    generate_with_evidence(Plain(), [], phase="tools")
    bs.stop()
    ev = _events(tmp_path)
    assert [e["k"] for e in ev if e["k"] in ("call", "done")] == ["call", "done"], "the plain adapter wrote nothing"
    assert ev[1]["turn"] == "reflect" and ev[1]["phase"] == "tools"
    assert "I will look." in "".join(e.get("s", "") for e in ev if e["k"] == "text")


def test_no_beat_means_no_stream_and_no_file(tmp_path):
    from sage.gateway.being_tool_loop import generate_with_evidence

    class Streams:
        def get_chat_response(self, messages, tools=None, fmt=None, on_chunk=None):
            assert on_chunk is None, "outside a beat nothing streams"
            return {"content": "ok", "tool_calls": [], "raw": {}}
    generate_with_evidence(Streams(), [], phase="tools")
    assert not (tmp_path / bs.STREAM_FILE).exists()


def test_the_being_cannot_write_its_output_stream():
    from sage.gateway.tests.test_home_is_reachable import _being
    r, home = _being(Path(tempfile.mkdtemp()))
    (home / bs.STREAM_FILE).write_text("")
    for name in (bs.STREAM_FILE, bs.STREAM_FILE + ".1"):
        with pytest.raises(ValueError) as e:
            r._safe_path(name, writing=True)
        assert "the harness writes into it" in str(e.value)
    assert r._safe_path(bs.STREAM_FILE, writing=False) == (home / bs.STREAM_FILE).resolve()


def test_read_tail_keeps_a_line_its_window_starts_exactly_on(tmp_path):
    p = tmp_path / bs.STREAM_FILE
    lines = [json.dumps({"k": "text", "n": i}) + "\n" for i in range(5)]
    p.write_text("".join(lines))
    tail = len(lines[-1]) + len(lines[-2])
    assert [e["n"] for e in bs.read_tail(p, max_bytes=tail)] == [3, 4]
    assert [e["n"] for e in bs.read_tail(p, max_bytes=tail - 1)] == [4]


def test_stop_is_idempotent_so_atexit_can_close_a_beat_that_raised(tmp_path):
    bs.start(tmp_path, "b")
    bs.stop()
    bs.stop()                                            # what atexit runs after the normal stop: nothing more
    assert [e["k"] for e in _events(tmp_path)] == ["beat", "end"]
