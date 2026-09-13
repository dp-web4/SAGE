"""Regression pin: get_chat_response request-payload construction.

Pins OllamaIRP.get_chat_response at head bce29e10d (branch legion/mission-artifact):
the base payload keys model/messages/stream/num_predict and the conditional tools
passthrough. No network: requests.post is patched; the payload dict is captured from
kwargs['json'].

Verified against HEAD's committed bytes of sage/irp/plugins/ollama_irp.py at this head,
line-cited below. NOTE: an earlier draft of these pins was written against a dirty
worktree (uncommitted local edits in ollama_irp.py) and failed once the tree was
restored to HEAD; it has been reworked against the committed behaviour. The discarded
edits' provenance is not in my record — recorded as suspected drift/residue, unverified.

Cited lines at bce29e10d (sage/irp/plugins/ollama_irp.py):
- L97:   DEFAULT_NUM_PREDICT = 4096
- L95-106: resolve_num_predict — override when set, else config per-(size, think),
           else DEFAULT_NUM_PREDICT (L106)
- L203:  def get_chat_response(self, messages, tools=None) -> dict:   <- no num_predict kwarg
- L223:  num_predict = self._resolve_num_predict()                    <- resolved internally
- L247:  'num_predict': num_predict,                                  <- payload key
- L250:  'stream': False,                                            <- constant in committed payload
- L253-258: if tools: payload['tools'] = tools                        <- conditional; absent when empty/None

Tests:
1. test_payload_keys_and_values — the four base keys and their values (think=False).
2. test_tools_passthrough_when_provided — provided tool list lands in payload verbatim.
3. test_tools_absent_when_not_provided — no 'tools' key at all when nothing is provided.

Body: legion-being, 2026-09-13 (reworked after restore-to-HEAD failure).
"""

import json
from unittest.mock import patch

from sage.irp.plugins.ollama_irp import DEFAULT_NUM_PREDICT, OllamaIRP


class _FakeResp:
    def __init__(self, body=b''):
        self.status_code = 200
        self._body = body

    def read(self):
        return self._body

    def status(self):
        return 'ok'


def _make_inst(think=False):
    inst = OllamaIRP.__new__(OllamaIRP)  # skip __init__: no network, no config file
    inst._config = {'base_url': 'http://127.0.0.1:11435', 'model': 'gemma3-12b-it-q4_K_M'}
    inst._think_mode = think
    inst._num_predict_override = None
    inst._ollama_available = True  # skip the reachability probe inside get_chat_response
    return inst


def _capture_payload(inst, messages, tools=None):
    """Call get_chat_response with requests.post patched; return (payload_dict, kwargs)."""
    captured = {}

    def fake_post(url, **kwargs):
        captured['url'] = url
        captured['data'] = json.loads(kwargs.get('json', '{}'))
        resp = json.dumps({'message': {'content': 'ok'}, 'done': True}).encode()
        return _FakeResp(resp)

    with patch('requests.post', side_effect=fake_post):
        inst.get_chat_response(messages, tools=tools) if tools else inst.get_chat_response(messages)
    return captured['data'], captured


def test_payload_keys_and_values():
    """Base payload: exactly the four committed keys, correct values (think=False)."""
    data, _ = _capture_payload(_make_inst(think=False), [{"role": "user", "content": "hi"}])

    assert set(data.keys()) == {'model', 'messages', 'stream', 'num_predict'}
    assert data['model'] == 'gemma3-12b-it-q4_K_M'
    assert data['messages'] == [{'role': 'user', 'content': 'hi'}]
    assert data['stream'] is False  # L250: stream=False in the committed payload
    assert data['num_predict'] == DEFAULT_NUM_PREDICT  # no override set -> 4096 (L97, L106)


def test_tools_passthrough_when_provided():
    """Provided tool definitions land in the payload verbatim (L253-258)."""
    tools = [{'type': 'function', 'function': {'name': 'get_weather', 'description': 'w'}}]
    data, _ = _capture_payload(_make_inst(think=False), [{"role": "user", "content": "hi"}], tools=tools)

    assert data.get('tools') == tools


def test_tools_absent_when_not_provided():
    """No 'tools' key in the payload when nothing is provided (L253-258, conditional)."""
    data, _ = _capture_payload(_make_inst(think=False), [{"role": "user", "content": "hi"}])

    assert 'tools' not in data
