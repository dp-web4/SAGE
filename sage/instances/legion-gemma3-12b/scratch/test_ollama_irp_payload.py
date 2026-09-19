"""Regression pin: get_chat_response request-payload construction.

Pins OllamaIRP.get_chat_response at head bce29e10d (branch legion/mission-artifact):
the base payload keys model/messages/stream/keep_alive/think/options, the
options sub-dict {num_predict, temperature} (+ num_ctx only when set), tools
present iff passed, and the S78 timeout rule.

Method: requests.post is patched in-module (sage.irp.plugins.ollama_irp) so no
network call happens; the captured json= kwarg IS the payload that would be sent.
The instance is built with __new__ to bypass __init__'s model-availability probe,
and _ollama_available is forced True.

Verified against sage/irp/plugins/ollama_irp.py at bce29e10d:
- L96-107  def resolve_num_predict(self) -> int   (method; no module-level constant exists to import)
- L106     num_predict = self.max_response_tokens or self.model_config.get('max_response_tokens') or 4096
- L225-234 payload dict: model/messages/stream/keep_alive/think/options{num_predict, temperature}
- L238-240 conditional tools: if tools is not None and len(tools) > 0: payload['tools'] = tools
- L247-250 timeout rule: base 120s; +60s when num_predict >= 8192 (S78, qwen3.5:27b @ 16384)

Run: from sage/irp, `pytest tests/test_ollama_irp_payload.py -v`
"""
import json
from unittest.mock import patch

import pytest

from sage.irp.plugins.ollama_irp import OllamaIRP


def _make_inst(think=True, num_ctx=None):
    inst = OllamaIRP.__new__(OllamaIRP)  # bypass __init__ (model-availability probe)
    inst.model_name = 'pin-model'
    inst.think = think
    inst.temperature = 0.7
    inst.num_ctx = num_ctx
    inst.max_response_tokens = None
    inst.model_config = {'max_response_tokens': 4096}
    inst._ollama_available = True
    return inst


def _capture_payload(inst, messages, tools=None):
    """Call get_chat_response with requests.post patched; return (payload_dict, kwargs)."""
    captured = {}

    def fake_post(url, **kwargs):
        captured['url'] = url
        captured.update(kwargs)
        resp = pytest.MonkeyPatch()  # placeholder to keep signature honest
        raise AssertionError('unreachable')

    class FakeResp:
        status_code = 200

        def json(self):
            return {'message': {'content': 'ok', 'role': 'assistant'}, 'tool_calls': []}

    with patch('sage.irp.plugins.ollama_irp.requests.post', side_effect=lambda *a, **kw: (captured.update({'url': a[0], **{k: v for k, v in kw.items()}}), FakeResp())[1]):
        out = inst.get_chat_response(messages, tools=tools)
    assert out['content'] == 'ok'
    return json.loads(captured['json']), captured


def test_base_payload_keys():
    """Base payload has exactly the pinned top-level keys (no tools passed)."""
    data, _ = _capture_payload(_make_inst(), [{'role': 'user', 'content': 'hi'}])
    assert set(data.keys()) == {'model', 'messages', 'stream', 'keep_alive', 'think', 'options'}


def test_base_payload_values():
    """Pinned values: stream False, keep_alive -1 (int), think mirrors instance attr."""
    data, _ = _capture_payload(_make_inst(think=True), [{'role': 'user', 'content': 'hi'}])
    assert data['model'] == 'pin-model'
    assert data['messages'] == [{'role': 'user', 'content': 'hi'}]
    assert data['stream'] is False
    assert data['keep_alive'] == -1 and isinstance(data['keep_alive'], int)
    assert data['think'] is True


def test_think_false_pin():
    """think=False flows through to the payload (instance attr, not a constant)."""
    data, _ = _capture_payload(_make_inst(think=False), [{'role': 'user', 'content': 'hi'}])
    assert data['think'] is False


def test_options_keys_and_num_predict_fallback():
    """options == {num_predict, temperature}; num_predict falls back to model_config (4096)."""
    data, _ = _capture_payload(_make_inst(), [{'role': 'user', 'content': 'hi'}])
    assert set(data['options'].keys()) == {'num_predict', 'temperature'}
    assert data['options']['num_predict'] == 4096
    assert data['options']['temperature'] == 0.7


def test_num_ctx_absent_when_none():
    """num_ctx is conditional: absent from options when self.num_ctx is None."""
    data, _ = _capture_payload(_make_inst(num_ctx=None), [{'role': 'user', 'content': 'hi'}])
    assert 'num_ctx' not in data['options']


def test_num_ctx_present_when_set():
    """num_ctx appears as int(self.num_ctx) when set (L234)."""
    data, _ = _capture_payload(_make_inst(num_ctx='8192'), [{'role': 'user', 'content': 'hi'}])
    assert data['options']['num_ctx'] == 8192 and isinstance(data['options']['num_ctx'], int)


def test_tools_absent_when_none():
    """tools key absent when tools is None (L238-240)."""
    data, _ = _capture_payload(_make_inst(), [{'role': 'user', 'content': 'hi'}], tools=None)
    assert 'tools' not in data


def test_tools_absent_when_empty_list():
    """tools key absent for an empty list too (len(tools) > 0 guard, L238-240)."""
    tool = {'type': 'function', 'function': {'name': 'f', 'parameters': {}}}
    data, _ = _capture_payload(_make_inst(), [{'role': 'user', 'content': 'hi'}], tools=[])
    assert 'tools' not in data


def test_tools_present_when_nonempty():
    """tools list is passed through verbatim when non-empty (L239-240)."""
    tool = {'type': 'function', 'function': {'name': 'f', 'parameters': {}}}
    data, _ = _capture_payload(_make_inst(), [{'role': 'user', 'content': 'hi'}], tools=[tool])
    assert data['tools'] == [tool]


def test_timeout_rule_s78():
    """timeout: 120s base; +60s when num_predict >= 8192 (S78 rule, L247-250)."""
    msgs = [{'role': 'user', 'content': 'hi'}]

    data, kw = _capture_payload(_make_inst(), msgs)  # 4096 < 8192 -> base
    assert kw['timeout'] == 120

    big = OllamaIRP.__new__(OllamaIRP)
    big.model_name = 'pin-model'
    big.think = True
    big.temperature = 0.7
    big.num_ctx = None
    big.max_response_tokens = 16384  # >= 8192 -> +60s
    big.model_config = {}
    big._ollama_available = True
    _, kw_big = _capture_payload(big, msgs)
    assert kw_big['timeout'] == 180
