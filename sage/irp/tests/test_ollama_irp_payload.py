"""Regression pin: OllamaIRP.get_chat_response request-payload construction.

Verified against sage/irp/plugins/ollama_irp.py at worktree head 6f5550f64 (branch legion-being/irp-payload-pin):
- L97     resolve_num_predict(): override when set, else adapter capability, else max_response_tokens
- L123    payload {model, messages, stream:False, keep_alive:-1, think, options{num_predict, temperature[, num_ctx]}}
- L128    payload['tools'] added iff tools is not None and len(tools) > 0
- L130-137 POST via urllib.request.Request(url, data=json bytes); urlopen(req, timeout=...) — module never imports requests

Fixture patches sage.irp.plugins.ollama_irp.urllib.request.urlopen (the real call site),
captures json.loads(req.data) off the Request it receives, and returns a context-manager
fake whose .read() yields response JSON bytes — the source uses `with urlopen(...) as resp`.
The instance is built with __new__ to bypass __init__'s model-availability probe; every
attribute get_chat_response reads must therefore be set explicitly (including
num_predict_override, which resolve_num_predict consults first). _adapter is assigned via
get_adapter(model_name) because the __new__ bypass skips __init__, where it would normally
be set — and ollama_host/timeout_seconds are pinned to config defaults since nothing in
get_chat_response derives them per request (timeout is fixed at 120; there is no '+60s' rule).
"""
import json
from unittest.mock import patch

from sage.irp.plugins.ollama_irp import OllamaIRP


def _make_inst(think=True, num_ctx=None, max_response_tokens=None):
    inst = OllamaIRP.__new__(OllamaIRP)  # bypass __init__ (model-availability probe)
    inst.model_name = 'pin-model'
    from sage.irp.adapters.model_adapter import get_adapter
    inst._adapter = get_adapter(inst.model_name)
    inst.ollama_host = 'http://127.0.0.1:1'
    inst.timeout_seconds = 120
    inst.think = think
    inst.temperature = 0.7
    inst.num_ctx = num_ctx
    inst.max_response_tokens = max_response_tokens if max_response_tokens is not None else 250
    inst.num_predict_override = None
    inst.model_config = {} if max_response_tokens is not None else {'max_response_tokens': 4096}
    inst._ollama_available = True
    return inst


class _FakeResp:
    def read(self):
        body = {
            'message': {'role': 'assistant', 'content': 'ok', 'tool_calls': []},
            'tool_calls': [],
        }
        return json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _capture_payload(inst, messages, tools=None):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured['payload'] = json.loads(req.data)
        captured['timeout'] = timeout
        return _FakeResp()

    with patch('sage.irp.plugins.ollama_irp.urllib.request.urlopen', side_effect=fake_urlopen):
        out = inst.get_chat_response(messages, tools=tools)
    assert out['content'] == 'ok'
    return captured['payload'], {'timeout': captured['timeout']}


def test_base_payload_keys():
    data, _ = _capture_payload(_make_inst(), [{'role': 'user', 'content': 'hi'}])
    assert set(data.keys()) == {'model', 'messages', 'stream', 'keep_alive', 'think', 'options'}


def test_base_payload_values():
    data, _ = _capture_payload(_make_inst(think=True), [{'role': 'user', 'content': 'hi'}])
    assert data['model'] == 'pin-model'
    assert data['messages'] == [{'role': 'user', 'content': 'hi'}]
    assert data['stream'] is False
    assert data['keep_alive'] == -1 and isinstance(data['keep_alive'], int)
    assert data['think'] is True


def test_think_false_pin():
    data, _ = _capture_payload(_make_inst(think=False), [{'role': 'user', 'content': 'hi'}])
    assert data['think'] is False


def test_options_keys_and_num_predict_fallback():
    # 'pin-model' resolves to a DefaultAdapter whose capabilities carry no
    # max_response_tokens, so resolve_num_predict falls back to self.max_response_tokens == 250.
    data, _ = _capture_payload(_make_inst(), [{'role': 'user', 'content': 'hi'}])
    assert set(data['options'].keys()) == {'num_predict', 'temperature'}
    assert data['options']['num_predict'] == 250
    assert data['options']['temperature'] == 0.7


def test_num_ctx_absent_when_none():
    data, _ = _capture_payload(_make_inst(num_ctx=None), [{'role': 'user', 'content': 'hi'}])
    assert 'num_ctx' not in data['options']


def test_num_ctx_present_when_set():
    data, _ = _capture_payload(_make_inst(num_ctx='8192'), [{'role': 'user', 'content': 'hi'}])
    assert data['options']['num_ctx'] == 8192 and isinstance(data['options']['num_ctx'], int)


def test_tools_absent_when_none():
    data, _ = _capture_payload(_make_inst(), [{'role': 'user', 'content': 'hi'}], tools=None)
    assert 'tools' not in data


def test_tools_absent_when_empty_list():
    data, _ = _capture_payload(_make_inst(), [{'role': 'user', 'content': 'hi'}], tools=[])
    assert 'tools' not in data


def test_tools_present_when_nonempty():
    tool = {'type': 'function', 'function': {'name': 'f', 'parameters': {}}}
    data, _ = _capture_payload(_make_inst(), [{'role': 'user', 'content': 'hi'}], tools=[tool])
    assert data['tools'] == [tool]
