"""Capture through the real HTTP adapter, with a fake transport and synthetic data."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from sage.gateway.being_tool_loop import run_ollama_tool_turn
from sage.gateway.tests.test_being_tool_loop import OK_DISPATCH, _client


def _adapter(monkeypatch, payload):
    # Match the file-path loading used by the pool; do not instantiate a model
    # or let the adapter probe a real server.
    path = Path(__file__).resolve().parents[2] / "irp/plugins/ollama_irp.py"
    spec = importlib.util.spec_from_file_location("synthetic_capture_ollama", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return payload

    sent = []

    def fake_open(request, timeout):
        sent.append(json.loads(request.data))
        return FakeResponse()

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_open)
    model = module.OllamaIRP.__new__(module.OllamaIRP)
    model._ollama_available = True
    model.model_name = "synthetic-model"
    model.ollama_host = "http://synthetic.invalid"
    model.max_response_tokens = 64
    model.num_predict_override = None
    model.temperature = 0.0
    model.num_ctx = None
    model.timeout_seconds = 1
    model.think = False
    model.tools_on_last_user_only = False
    model._adapter = SimpleNamespace(capabilities=SimpleNamespace(
        resolve_num_predict=lambda *args: 64,
    ))
    return model, sent


@pytest.mark.parametrize("thinking", ["synthetic thought", None])
def test_decoded_provider_shape_is_captured_without_real_transport(tmp_path, monkeypatch, thinking):
    raw = {"message": {"content": "done", "role": "assistant", "tool_calls": [],
                       "thinking": thinking}, "done_reason": "stop",
           "prompt_eval_count": 12, "eval_count": 3}
    model, sent = _adapter(monkeypatch, json.dumps(raw).encode())
    (tmp_path / "instance.json").write_text(json.dumps({"params": {"turn_capture": "on"}}))
    client = _client(OK_DISPATCH)
    client.memory_root = str(tmp_path)

    result = run_ollama_tool_turn(client, model, [{"role": "user", "content": "synthetic"}], tools=[])
    assert result.reply == "done"
    assert result.capture_stats == {"attempted": 1, "written": 1, "failed": 0}
    row = json.loads((tmp_path / "turn_capture.jsonl").read_text())
    assert row["reply"] == {"content": "done", "tool_calls": [], "thinking": thinking}
    assert row["attempt"]["prompt_eval_count"] == 12
    assert len(sent) == 1 and sent[0]["messages"] == row["messages"]


def test_provider_nonfinite_metadata_is_not_silently_coerced(tmp_path, monkeypatch):
    # Python's JSON decoder accepts this non-standard token; capture deliberately
    # refuses it even though the adapter returns the response to the turn.
    payload = b'{"message":{"content":"done","thinking":NaN},"done_reason":"stop"}'
    model, _ = _adapter(monkeypatch, payload)
    (tmp_path / "instance.json").write_text(json.dumps({"params": {"turn_capture": "on"}}))
    client = _client(OK_DISPATCH)
    client.memory_root = str(tmp_path)

    result = run_ollama_tool_turn(client, model, [{"role": "user", "content": "synthetic"}], tools=[])
    assert result.reply == "done"
    assert result.capture_stats == {"attempted": 1, "written": 0, "failed": 1}
    assert not (tmp_path / "turn_capture.jsonl").exists()
