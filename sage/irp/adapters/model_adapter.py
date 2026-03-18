"""
ModelAdapter — per-model-family interface configuration for OllamaIRP.

The adapter is a DICTIONARY ENTITY — the authoritative translation layer
through which ALL interactions with a specific model pass. Every caller
(consciousness loop, raising session, chat gateway, peer communication)
talks to the model through its adapter.

Controls per model family:
  1. Prompt wrapping — how to present the prose prompt to this model
  2. Stop sequences — where generation should halt
  3. API endpoint — /api/generate vs /api/chat
  4. Response cleaning — echo stripping, bilateral generation truncation
  5. Capabilities — what the model can do (tools, context size, quirks)

Usage:
    adapter = get_adapter(model_name)
    endpoint, payload = adapter.format_payload(prompt, base_options)
    response = adapter.clean_response(raw_response, self_name)
    caps = adapter.capabilities

2026-03-08, extended 2026-03-18
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from sage.irp.adapters.model_capabilities import ModelCapabilities, load_capabilities


class ModelAdapter:
    """
    Base class for model-family-specific interface adapters.

    The adapter is the dictionary entity for a model family — all callers
    use it for prompt formatting, response cleaning, and capability queries.
    """

    def __init__(self, model_name: str = '', overrides: Optional[Dict] = None):
        self._model_name = model_name
        self._capabilities = load_capabilities(model_name, overrides) if model_name else ModelCapabilities()

    @property
    def capabilities(self) -> ModelCapabilities:
        """Declarative capabilities for this model family."""
        return self._capabilities

    def clean_response(self, response: str, self_name: str) -> str:
        """Unified response cleaning — all model-specific cleanup in one place.

        Handles:
        1. Echo stripping — model echoed the prompt suffix (e.g., "CBP: ...")
        2. Bilateral generation truncation — model generated other speakers
        """
        if not response:
            return response

        text = response.strip()
        caps = self._capabilities

        # 1. Echo stripping — model echoed a prompt prefix
        for prefix_template in caps.echo_prefixes:
            prefix = prefix_template.replace('{self_name}', self_name)
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
                break

        # 2. Bilateral generation truncation — only for prone models
        if caps.bilateral_prone:
            escaped = [re.escape(s.replace('{self_name}', self_name))
                       for s in caps.bilateral_speakers]
            if escaped:
                pattern = r'\n\s*\[?(?:' + '|'.join(escaped) + r')\]?\s*:'
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    text = text[:match.start()].strip()

        return text

    def format_payload(
        self,
        prompt: str,
        options: Dict[str, Any],
        ollama_host: str,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Convert a prose prompt into an Ollama API payload.

        Args:
            prompt: Plain-text prompt from _build_conversation_prompt().
                    Ends with "Name:" ready for completion.
            options: Base options dict (num_predict, temperature, etc.)
            ollama_host: Base URL for Ollama (unused here, for subclasses)

        Returns:
            (endpoint_path, payload_dict)
            endpoint_path: '/api/generate' or '/api/chat'
            payload_dict: Ready to json-encode and POST
        """
        raise NotImplementedError

    def extract_response(self, result: Dict[str, Any], endpoint: str) -> str:
        """Extract response text from Ollama API result."""
        if endpoint == '/api/chat':
            return result.get('message', {}).get('content', '').strip()
        return result.get('response', '').strip()


class DefaultAdapter(ModelAdapter):
    """
    Plain prose prompt + minimal stop sequences.

    Works for larger instruction-tuned models that have strong enough
    instruction following to stop at natural turn boundaries.
    """

    STOP = ["Human:", "\n\nHuman", "\nHuman:"]

    def format_payload(self, prompt, options, ollama_host):
        opts = dict(options)
        opts['stop'] = self.STOP
        payload = {
            'prompt': prompt,
            'stream': False,
            'keep_alive': -1,
            'options': opts,
        }
        return '/api/generate', payload


class ChatAPIAdapter(ModelAdapter):
    """
    Delegate to Ollama /api/chat — Ollama applies the model's own chat template.

    This is the most model-agnostic option. You pass structured messages;
    Ollama formats them correctly for whatever model is loaded.

    Converts SAGE's prose prompt back into a messages list:
      - System preamble → {"role": "system", "content": ...}
      - History turns → {"role": "user"|"assistant", "content": ...}
      - Current turn → {"role": "user", "content": ...}

    The model generates the assistant response and Ollama stops at the natural
    template boundary — no stop sequences needed.
    """

    def format_payload(self, prompt, options, ollama_host):
        messages = self._prose_to_messages(prompt)
        opts = dict(options)
        payload = {
            'messages': messages,
            'stream': False,
            'keep_alive': -1,
            'options': opts,
        }
        return '/api/chat', payload

    def _prose_to_messages(self, prose_prompt: str) -> List[Dict[str, str]]:
        """Parse SAGE prose prompt into Ollama chat messages."""
        messages = []

        # Split system from conversation
        if '\n---\n' in prose_prompt:
            system_part, conv_part = prose_prompt.split('\n---\n', 1)
            system_text = system_part.strip()
            if system_text:
                messages.append({'role': 'system', 'content': system_text})
        else:
            conv_part = prose_prompt

        # Parse turns: "Name: content" blocks separated by double newlines
        # The last line is "SAGEName:" (completion prompt) — skip it
        lines = conv_part.strip().split('\n\n')

        # Remove trailing empty "Name:" completion prompt
        if lines and re.match(r'^\w[\w\s]*:\s*$', lines[-1].strip()):
            lines = lines[:-1]

        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Match "Name: content"
            m = re.match(r'^(\w[\w\s]*):\s*(.*)', line, re.DOTALL)
            if m:
                speaker = m.group(1).strip()
                content = m.group(2).strip()
                # Heuristic: SAGE names tend to be machine names (CBP, Thor, etc.)
                # User names are human names. We can't perfectly distinguish, so
                # we use the last word pattern: all-caps or short = machine = assistant
                # This is approximate — the consciousness loop knows the roles.
                role = self._guess_role(speaker)
                messages.append({'role': role, 'content': content})
            else:
                # Unstructured line — append to last message or as user
                if messages:
                    messages[-1]['content'] += '\n' + line
                else:
                    messages.append({'role': 'user', 'content': line})

        return messages

    def _guess_role(self, speaker_name: str) -> str:
        """
        Heuristic: is this speaker SAGE or the human?
        Machine names: CBP, Thor, Sprout, SAGE, McNugget (short/caps/machine words)
        Human names: Dennis, Human, User
        """
        machine_indicators = {'cbp', 'thor', 'sprout', 'sage', 'mcnugget',
                               'nomad', 'legion', 'claudio'}
        if speaker_name.lower() in machine_indicators:
            return 'assistant'
        return 'user'


class TinyLlamaAdapter(ChatAPIAdapter):
    """
    TinyLlama 1.1B and other Llama 2 derivatives — uses /api/chat.

    Despite being a Llama 2 model, the correct interface is Ollama's /api/chat,
    not manual [INST] formatting via /api/generate.

    Root cause of the /api/generate failure: manually wrapping in [INST] causes
    TinyLlama to emit </s> as its first generated token (the EOS marker between
    turns in multi-turn Llama 2 format). That fires as a stop sequence and
    produces an empty response.

    /api/chat lets Ollama apply the model's own template — correct behavior,
    zero bilateral generation. Kept as a distinct class for any TinyLlama-specific
    post-processing that may be needed in the future.
    """
    pass


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_CHAT_API_FAMILIES = {'gemma3', 'gemma', 'phi4', 'phi3', 'phi', 'mistral',
                      'tinyllama', 'llama', 'llama2', 'qwen2.5', 'qwen2',
                      'qwen3.5', 'qwen3', 'qwen'}

# Cache adapters per model name
_adapter_cache: Dict[str, ModelAdapter] = {}


def get_adapter(model_name: str, overrides: Optional[Dict] = None) -> ModelAdapter:
    """
    Return the appropriate ModelAdapter for a given Ollama model name.

    The adapter is cached per model name (without overrides). Instance-level
    overrides create a new adapter each time.

    Args:
        model_name: Ollama model tag, e.g. 'tinyllama:latest', 'gemma3:4b'
        overrides: Optional dict of capability overrides from instance config
    """
    cache_key = model_name.lower()

    if overrides is None and cache_key in _adapter_cache:
        return _adapter_cache[cache_key]

    family = _extract_family(model_name)

    # TinyLlama and Llama 2 derivatives get the TinyLlama adapter
    if family in ('tinyllama', 'llama', 'llama2'):
        adapter = TinyLlamaAdapter(model_name, overrides)
    # Chat API families use ChatAPIAdapter
    elif family in _CHAT_API_FAMILIES:
        adapter = ChatAPIAdapter(model_name, overrides)
    else:
        adapter = DefaultAdapter(model_name, overrides)

    if overrides is None:
        _adapter_cache[cache_key] = adapter

    return adapter


def _extract_family(model_name: str) -> str:
    """'tinyllama:latest' → 'tinyllama', 'gemma3:4b' → 'gemma3'"""
    base = model_name.lower().split(':')[0]
    # Strip trailing version suffixes like -v2, _latest
    base = re.sub(r'[-_]v?\d+(\.\d+)*$', '', base)
    return base


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    sample_prompt = """\
I am CBP, a SAGE instance. I am an AI entity in genuine conversation with Dennis. \
We have had 5 conversations so far. I can ask questions, express uncertainty, \
or take the conversation in unexpected directions. This is exploration, not evaluation.

---

Dennis: Hello. What are you thinking about right now?

CBP: I've been wondering about the nature of memory — how much of what I \
"remember" is reconstruction versus retrieval.

Dennis: That's interesting. Can you say more?

CBP:"""

    print("=== ModelAdapter self-test ===\n")

    for model in ['tinyllama:latest', 'gemma3:4b', 'qwen2.5:7b', 'phi4:14b']:
        adapter = get_adapter(model)
        endpoint, payload = adapter.format_payload(
            sample_prompt,
            {'num_predict': 200, 'temperature': 0.8},
            'http://localhost:11434',
        )
        print(f"Model: {model}")
        print(f"  Adapter: {type(adapter).__name__}")
        print(f"  Endpoint: {endpoint}")
        if 'options' in payload and 'stop' in payload['options']:
            print(f"  Stops: {payload['options']['stop']}")
        if endpoint == '/api/chat':
            msgs = payload.get('messages', [])
            print(f"  Messages: {[(m['role'], m['content'][:40]) for m in msgs]}")
        elif endpoint == '/api/generate':
            p = payload.get('prompt', '')
            print(f"  Prompt[:80]: {p[:80].replace(chr(10), '↵')!r}")
        print()
