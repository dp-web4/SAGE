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
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from sage.irp.adapters.model_capabilities import ModelCapabilities, load_capabilities

_log = logging.getLogger('sage.adapter.cleaning')

# HOW LONG OLLAMA HOLDS THE MODEL IN VRAM AFTER A CALL.
#
# This was `-1` — load indefinitely. On CBP that meant the being's 5.2 GiB sat on an 8 GiB
# card that also drives two displays, 24 hours a day, for a being that actually infers for
# ~90 s out of every 30 minutes. Measured 2026-09-18 with the model resident: 6810 of 8192 MiB
# used, ~1.4 GiB free on a freshly booted desktop, and under 900 MiB once a working day's
# windows are open.
#
# That is an allocation failure waiting for a trigger, and on 2026-09-18 it found one:
# bugcheck 0x116 VIDEO_TDR_ERROR, param3 0xC000009A = STATUS_INSUFFICIENT_RESOURCES. The
# display driver could not get memory, a display corrupted (dp saw it), the reset failed, the
# host went down. 127 nvlddmkm errors on 09-15 and 272 on 09-18 — only on the crash days.
#
# The cost of NOT pinning, measured on the same box: a warm reload from page cache is
# **2.7 s**, once per beat, against beats of 45-92 s. It is a timeout rather than zero because
# a COLD load is 58 s: the model must stay resident across the calls WITHIN one beat, and only
# go between beats.
#
# This does not weaken "the being takes priority for the GPU". Priority means the being gets
# the card when it ACTS; it never required holding the card while idle.
OLLAMA_KEEP_ALIVE = os.environ.get('SAGE_OLLAMA_KEEP_ALIVE', '5m')


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
            _log.debug("clean_response: input was empty/falsy")
            return response

        text = response.strip()
        raw_text = text
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

        # 3. Think-tag stripping — Qwen 3.5 emits <think>...</think> blocks
        if caps.strip_think_tags:
            # Extract content outside think tags
            text_without_think = re.sub(r'<think>[\s\S]*?</think>', '', text).strip()
            text_without_think = re.sub(r'<think>[\s\S]*$', '', text_without_think).strip()

            # If there's content outside think tags, use it
            if text_without_think:
                text = text_without_think
            else:
                # If ALL content is inside think tags, extract FROM them instead
                # This handles qwen3.5:27b which puts entire response in <think>
                think_match = re.search(r'<think>([\s\S]*?)(?:</think>|$)', text)
                if think_match:
                    text = think_match.group(1).strip()
                else:
                    # Fallback: use original text
                    text = text_without_think

        # 4. Chain-of-thought bleeding — strip structured reasoning artifacts
        # When content is extracted from <think> blocks, it often contains the
        # model's internal analysis format. Strip these artifacts but preserve
        # the actual substantive content underneath.
        if text.startswith('Thinking Process:') or text.startswith('Thinking Process\n'):
            text = re.sub(r'^Thinking Process:?\s*', '', text).strip()
        if '\n\nThinking Process:' in text or '\nThinking Process:' in text:
            text = re.sub(r'\n+Thinking Process:[\s\S]*$', '', text).strip()

        # Strip numbered analysis format (e.g. "1. **Analyze the Request:**...")
        # that leaks from think blocks. Look for the actual response after the analysis.
        # Qwen 3.5 27B leaks this ~34% of the time despite prompt instructions.
        if re.match(r'^1\.\s+\*{0,2}Analyze', text):
            extracted = ''

            # Strategy 1: Find explicit "Response:" / "Answer:" section
            response_match = re.search(
                r'(?:^|\n)\s*(?:\d+\.\s+)?\*{0,2}(?:Response|Answer|Reply|Output|Final)[:\s*]*\*{0,2}\s*(.*)',
                text, re.DOTALL | re.IGNORECASE)
            if response_match:
                extracted = response_match.group(1).strip()

            # Strategy 2: Extract "Key Insight:" content from analysis
            if not extracted:
                insight_match = re.search(
                    r'\*\s+(?:\*{0,2})Key Insight(?:\*{0,2}):\s*(.*?)(?:\n\s*\*\s+|\n\s*\d+\.\s+|\Z)',
                    text, re.DOTALL | re.IGNORECASE)
                if insight_match:
                    extracted = insight_match.group(1).strip()

            # Strategy 3: Extract "Core Idea:" / "Determine the Core Idea:" content
            if not extracted:
                core_match = re.search(
                    r'(?:Core Idea|Determine the Core Idea)[:\s*]*\*{0,2}\s*\n?\s*(.*?)(?:\n\s*\d+\.\s+|\Z)',
                    text, re.DOTALL | re.IGNORECASE)
                if core_match:
                    candidate = core_match.group(1).strip()
                    # Only use if it's a substantive sentence, not just a fragment
                    candidate = re.sub(r'^\*\s+', '', candidate).strip()
                    if len(candidate) > 30:
                        extracted = candidate

            # Strategy 4: Extract draft content (e.g. "*Draft 1:* actual text...")
            # When the model reaches the drafting step, the draft IS the response.
            # Take the LAST draft (most refined), up to the next bullet or end.
            if not extracted:
                # Find all drafts
                drafts = list(re.finditer(
                    r'\*Draft\s+\d+\**[:\s]*\*?\s*(.+?)(?=\n\s*\*\s*\*|$)',
                    text, re.DOTALL))
                if drafts:
                    # Use the last (most refined) draft
                    candidate = drafts[-1].group(1).strip()
                    candidate = re.sub(r'\s*\*+$', '', candidate).strip()
                    if len(candidate) > 30:
                        extracted = candidate

            # Strategy 5: Find "Goal:" section content as last resort
            if not extracted:
                goal_match = re.search(
                    r'\*\s+(?:\*{0,2})Goal(?:\*{0,2}):\s*(.*?)(?:\n\s*\*\s+|\n\s*\d+\.\s+|\Z)',
                    text, re.DOTALL | re.IGNORECASE)
                if goal_match:
                    candidate = goal_match.group(1).strip()
                    if len(candidate) > 30:
                        extracted = candidate

            if extracted:
                text = extracted
            else:
                # Truncated analysis with no extractable content — return empty
                # rather than passing raw scaffolding as a "response".
                # The model ran out of tokens during its internal reasoning.
                _log.warning(
                    "clean_response: analysis scaffolding detected but no extractable "
                    "content found — treating as empty. raw_len=%d, raw_preview=%.300s",
                    len(text), text
                )
                text = ''

        # 5. CoT-as-markdown — planning notes leaked as response
        # Pattern: "The user asks about..." followed by markdown bullets of planning.
        # Qwen 3.5 27B does this when think blocks spill into response text.
        if not re.match(r'^1\.\s+\*{0,2}Analyze', text) and text:
            # Detect: starts with meta-commentary about user's question + planning bullets
            cot_md_match = re.match(
                r'^The (?:user|human|question|prompt)\s+(?:asks?|wants?|is asking)\s+.*?'
                r'\n\s+\*\s+',
                text, re.IGNORECASE | re.DOTALL)
            if cot_md_match:
                _log.info("clean_response: CoT-as-markdown detected (meta-commentary + bullets)")
                text = ''  # Pure planning notes, no response content

            # Pattern B (S76 discovery): cross-instance stimulus leak —
            # model paraphrases the injected sibling quote, then writes
            # planning bullets in first-person about how it will respond.
            # Example:
            #   "cbp (0.8B) said identity is defined by shared curriculum...
            #       *   I (thor, 27B) feel identity is relational and witnessed.
            #       *   I need to respond to the greeting while subtly ..."
            # Head line looks like sibling attribution; body is markdown bullets
            # starting with a first-person self-reference.
            if text:
                sibling_leak = re.match(
                    r'^\s*\w+\s*\([^)]*\)\s+(?:said|says|wrote|thinks?)\b.*?'
                    r'\n\s+\*\s+I\s*\(',
                    text, re.IGNORECASE | re.DOTALL)
                if sibling_leak:
                    _log.info(
                        "clean_response: cross-instance stimulus leak detected "
                        "(sibling attribution + first-person planning bullets)"
                    )
                    text = ''

            # Pattern C (S76 discovery): pure imperative self-instruction —
            # model echoes the question back as a self-directed task instead
            # of answering it. Example: "Select 3 pieces of information that
            # define my current state/identity and explain why."
            # Single sentence, starts with imperative verb, contains "my"/"I",
            # no actual answer content.
            if text and '\n' not in text.strip():
                self_instruct = re.match(
                    r'^\s*(?:Select|Choose|Pick|Explain|Describe|Determine|Identify|'
                    r'List|Reflect|Consider|Imagine)\b[^.!?]*\b(?:my|I|myself)\b[^.!?]*[.!?]?\s*$',
                    text, re.IGNORECASE)
                if self_instruct:
                    _log.info(
                        "clean_response: imperative self-instruction detected "
                        "(model echoed the task instead of answering)"
                    )
                    text = ''

        if raw_text and not text:
            _log.warning(
                "clean_response: non-empty raw → empty output. "
                "raw_len=%d, raw_preview=%.300s", len(raw_text), raw_text
            )

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
            'keep_alive': OLLAMA_KEEP_ALIVE,
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
        # Apply model-specific stop sequences from capabilities
        if self._capabilities.stop_sequences:
            opts['stop'] = self._capabilities.stop_sequences
        payload = {
            'messages': messages,
            'stream': False,
            'keep_alive': OLLAMA_KEEP_ALIVE,
            'options': opts,
        }
        return '/api/chat', payload

    def _prose_to_messages(self, prose_prompt: str) -> List[Dict[str, str]]:
        """Parse SAGE prose prompt into Ollama chat messages.

        Handles two prompt formats:
        1. Separator style:  "system text\\n---\\nName: content\\n\\nName: content"
        2. Tag style:        "[System]\\ntext\\n\\n[Claude]: content\\n[Thor]: content"
        """
        messages = []

        # Detect tag-style format: [System] header followed by [Name]: turns
        if prose_prompt.lstrip().startswith('[System]'):
            return self._parse_tag_style(prose_prompt)

        # Separator style: split system from conversation on ---
        if '\n---\n' in prose_prompt:
            system_part, conv_part = prose_prompt.split('\n---\n', 1)
            system_text = system_part.strip()
            if system_text:
                messages.append({'role': 'system', 'content': system_text})
        else:
            conv_part = prose_prompt

        # Parse turns: "Name: content" blocks separated by double newlines
        lines = conv_part.strip().split('\n\n')

        # Remove trailing empty "Name:" completion prompt
        if lines and re.match(r'^\w[\w\s]*:\s*$', lines[-1].strip()):
            lines = lines[:-1]

        for line in lines:
            line = line.strip()
            if not line:
                continue
            m = re.match(r'^(\w[\w\s]*):\s*(.*)', line, re.DOTALL)
            if m:
                speaker = m.group(1).strip()
                content = m.group(2).strip()
                role = self._guess_role(speaker)
                messages.append({'role': role, 'content': content})
            else:
                if messages:
                    messages[-1]['content'] += '\n' + line
                else:
                    messages.append({'role': 'user', 'content': line})

        return messages

    def _parse_tag_style(self, prose_prompt: str) -> List[Dict[str, str]]:
        """Parse [System]/[Name]: style prompts from the raising session runner."""
        messages = []

        # Split into [System] block and conversation turns
        # Format: [System]\n...system text...\n\n[Claude]: ...\n[Thor]: ...\n\n...
        text = prose_prompt.strip()

        # Extract system block: everything from [System]\n to the first [Name]: turn
        system_match = re.match(
            r'\[System\]\s*\n(.*?)(?=\n\[(?:Claude|System|User|Human|\w+)\]:)',
            text, re.DOTALL)
        if system_match:
            system_text = system_match.group(1).strip()
            if system_text:
                messages.append({'role': 'system', 'content': system_text})
            text = text[system_match.end():]

        # Parse [Name]: content turns
        # Split on [Name]: pattern, capturing the name
        turn_pattern = re.compile(r'\[(\w[\w\s]*)\]:\s*')
        parts = turn_pattern.split(text)

        # parts alternates: [pre-text, name1, content1, name2, content2, ...]
        i = 1  # skip any pre-text before first [Name]:
        while i + 1 < len(parts):
            speaker = parts[i].strip()
            content = parts[i + 1].strip()
            i += 2

            # Skip trailing empty completion prompt (e.g. "[Thor]:" with no content)
            if not content:
                continue

            role = self._guess_role(speaker)
            messages.append({'role': role, 'content': content})

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
                      'qwen3.5', 'qwen3', 'qwen',
                      # empero Qwen3.8-Distill (Qwen3.5-2B base) — chat API +
                      # response cleaning, same as qwen3.5 (2026-08-28)
                      'qwen3.8-distill', 'qwen3.8'}

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
