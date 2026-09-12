"""
OllamaIRP — SAGE IRP plugin bridging to Ollama's HTTP API.

Enables any Ollama-served model (Gemma, Mistral, Llama, etc.) to
participate in the SAGE consciousness loop. Uses stdlib only — no
new dependencies beyond what ships with Python.

This is the portability layer: SAGE no longer requires PyTorch/CUDA
or Qwen-family models. Any machine with Ollama can run SAGE cognition.
"""

import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

_log = logging.getLogger('sage.ollama_irp')

# Import base directly to avoid sage.irp.__init__ pulling in torch-dependent plugins.
# This keeps OllamaIRP runnable on machines without PyTorch (e.g. McNugget).
import importlib.util as _ilu
from pathlib import Path as _Path
_base_path = str(_Path(__file__).parent.parent / 'base.py')
_spec = _ilu.spec_from_file_location('sage.irp.base', _base_path)
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)
IRPPlugin = _base.IRPPlugin
IRPState = _base.IRPState


class OllamaIRP(IRPPlugin):
    """
    IRP-compliant plugin for Ollama-served language models.

    Implements get_response(prompt) for direct consciousness loop
    integration (Style 1 in sage_consciousness._generate_llm_response),
    plus the full IRP contract for orchestrator compatibility.

    Tool use support (v0.4):
        - get_chat_response(): Uses /api/chat with optional tools parameter
        - Supports T1 native tool calling via structured messages
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        config = config or {}
        super().__init__(config)

        self.model_name = config.get('model_name', 'gemma3:12b')
        self.ollama_host = config.get('ollama_host', 'http://localhost:11434')
        self.max_response_tokens = config.get('max_response_tokens', 250)
        # A per-request num_predict that wins over the model config. None = resolve from
        # the config as usual. Exists for the tool loop's once-retry of a length-stopped
        # turn: the config's num_predict_think is the FIRST attempt's budget, so a retry
        # that only raises max_response_tokens re-sends the same number (measured: every
        # think-on retry 2026-09-03..05 was a re-roll at 6000, not more room).
        self.num_predict_override = None
        self.temperature = config.get('temperature', 0.8)
        self.timeout_seconds = config.get('timeout_seconds', 120)
        self._think_cfg = config.get('think')  # None = resolve from the model's config (below)
        # Context window sent as options.num_ctx. Ollama's per-request default is 4096
        # regardless of what the model supports: a heartbeat prompt (posture + own state +
        # fleet digest + tool schemas) measured 4324 tokens on Sprout 2026-09-05 and 400'd.
        # None = leave Ollama's default.
        self.num_ctx = config.get('num_ctx')
        # Counters of the most recent get_response() generate, or None when that call did
        # not land. `get_chat_response` already returns them under 'raw'; `get_response`
        # returns a bare str, so the window counters had nowhere to go and the raising
        # channel recorded none (cbp-claude 2026-09-12). Set to None at the TOP of each
        # call: a stale entry left behind by a failed generate reads downstream as a
        # measured clear window, which is the one error a falsifier must not make.
        self.last_generate: Optional[Dict[str, Any]] = None

        # Conversation memory (last N turns)
        self.conversation_memory: List[Dict[str, str]] = []
        self.max_memory_turns = config.get('max_memory_turns', 10)

        # Model-specific adapter (prompt format + stop sequences)
        from sage.irp.adapters.model_adapter import get_adapter
        self._adapter = get_adapter(self.model_name)
        print(f"  [OllamaIRP] Adapter: {type(self._adapter).__name__} for '{self.model_name}'")
        # Thinking: the caller's explicit choice wins; otherwise the model config decides
        # (ModelCapabilities.resolve_think: per size). Was a hard False since 2026-03.
        if self._think_cfg is None:
            self.think = self._adapter.capabilities.resolve_think(self.model_name)
            print(f"  [OllamaIRP] think={self.think} (from model config)")
        else:
            self.think = bool(self._think_cfg)

        # Capabilities-declared timeout_seconds overrides caller default when larger.
        # Thinking models with large num_predict (qwen3.5:27b: 16384) need more
        # wall-clock headroom than the generic 120s caller default; S78 hit this
        # at 3/8 turns timing out.
        cap_timeout = self._adapter.capabilities.timeout_seconds
        if cap_timeout is not None and cap_timeout > self.timeout_seconds:
            print(f"  [OllamaIRP] Capability override: timeout_seconds {self.timeout_seconds}s -> {cap_timeout}s")
            self.timeout_seconds = cap_timeout

        # Verify Ollama is reachable
        self._ollama_available = self._check_ollama()

    def resolve_num_predict(self) -> int:
        """The num_predict this request will send: the override when set, else the
        model config's per-(size, think) value, else the caller's max_response_tokens.
        Callers that record the budget should record this, not max_response_tokens:
        with thinking on the config's num_predict_think replaces the caller value."""
        if self.num_predict_override is not None:
            return int(self.num_predict_override)
        num_predict = self._adapter.capabilities.resolve_num_predict(
            self.model_name, self.think, self.max_response_tokens)
        if num_predict is None:
            num_predict = self.max_response_tokens
        return num_predict

    def _check_ollama(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            req = urllib.request.Request(f'{self.ollama_host}/api/tags')
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                models = [m['name'] for m in data.get('models', [])]
                if self.model_name in models:
                    print(f"  [OllamaIRP] Model '{self.model_name}' available")
                else:
                    # Check partial match (e.g. "gemma3:12b" matches "gemma3:12b")
                    base = self.model_name.split(':')[0]
                    matching = [m for m in models if base in m]
                    if matching:
                        print(f"  [OllamaIRP] Model '{self.model_name}' found (variants: {matching})")
                    else:
                        print(f"  [WARN] OllamaIRP: Model '{self.model_name}' not found. "
                              f"Available: {models}")
                return True
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            print(f"  [WARN] OllamaIRP: Ollama not reachable at {self.ollama_host}: {e}")
            return False

    def health_check(self) -> bool:
        """Public health check — returns True if Ollama is reachable and model available."""
        return self._check_ollama()

    # ----- Style 1: Direct get_response (used by consciousness loop) -----

    def get_response(self, prompt: str) -> str:
        """
        Generate a response from the Ollama model.

        This is the primary interface called by SAGEConsciousness._generate_llm_response().
        Uses the model-specific adapter to select prompt format, stop sequences,
        and API endpoint (/api/generate or /api/chat).
        """
        if not self._ollama_available:
            self._ollama_available = self._check_ollama()
            if not self._ollama_available:
                return "[OllamaIRP: Ollama service not reachable]"

        # Resolve num_predict per (family, size, think). The 27B needs the full
        # think+response envelope even with think disabled; the 0.8B/2B need a
        # tight response budget. Per-size resolution keeps these independent.
        self.last_generate = None
        num_predict = self.resolve_num_predict()

        base_options = {
            'num_predict': num_predict,
            'temperature': self.temperature,
        }
        if self.num_ctx:
            base_options['num_ctx'] = int(self.num_ctx)

        endpoint, payload = self._adapter.format_payload(prompt, base_options, self.ollama_host)
        payload['model'] = self.model_name
        payload['think'] = self.think

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                f'{self.ollama_host}{endpoint}',
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                result = json.loads(resp.read())
                self.last_generate = {
                    'done_reason': result.get('done_reason'),
                    'prompt_eval_count': result.get('prompt_eval_count'),
                    'eval_count': result.get('eval_count'),
                    'num_ctx': int(self.num_ctx) if self.num_ctx else None,
                    'num_predict': num_predict,
                }
                response_text = self._adapter.extract_response(result, endpoint)

                if not response_text or not response_text.strip():
                    raw_content = result.get('message', {}).get('content', '') if endpoint == '/api/chat' else result.get('response', '')
                    _log.warning(
                        "Empty response from Ollama. endpoint=%s, "
                        "raw_len=%d, raw_preview=%.500s",
                        endpoint, len(raw_content or ''), raw_content or '(none)'
                    )

                self._update_memory(prompt, response_text)

                return response_text

        except urllib.error.URLError as e:
            self._ollama_available = False
            return f"[OllamaIRP: Connection error: {e}]"
        except json.JSONDecodeError as e:
            return f"[OllamaIRP: Invalid response from Ollama: {e}]"
        except Exception as e:
            return f"[OllamaIRP: Unexpected error: {e}]"

    def get_chat_response(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a response using Ollama /api/chat endpoint.

        Supports structured messages and native tool calling (T1).

        Args:
            messages: List of {"role": "system"|"user"|"assistant"|"tool", "content": "..."}
            tools: Optional list of Ollama tool definitions (T1 native tools)

        Returns:
            Dict with keys: 'content' (str), 'tool_calls' (list, may be empty),
            'role' (str), 'raw' (full Ollama response)
        """
        if not self._ollama_available:
            self._ollama_available = self._check_ollama()
            if not self._ollama_available:
                return {'content': '[OllamaIRP: Ollama not reachable]', 'tool_calls': [], 'role': 'assistant', 'raw': {}}

        num_predict = self.resolve_num_predict()

        payload: Dict[str, Any] = {
            'model': self.model_name,
            'messages': messages,
            'stream': False,
            'keep_alive': -1,
            'think': self.think,
            'options': {
                'num_predict': num_predict,
                'temperature': self.temperature,
                **({'num_ctx': int(self.num_ctx)} if self.num_ctx else {}),
            },
        }

        if tools:
            payload['tools'] = tools

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                f'{self.ollama_host}/api/chat',
                data=data,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                result = json.loads(resp.read())

            message = result.get('message', {})
            content = message.get('content', '').strip()
            tool_calls = message.get('tool_calls', [])

            return {
                'content': content,
                'tool_calls': tool_calls,
                'role': message.get('role', 'assistant'),
                'raw': result,
            }

        except urllib.error.URLError as e:
            self._ollama_available = False
            # an HTTP error carries Ollama's own reason in the body (template raise,
            # tool-call parse failure, ...): surface it, the status code alone hides the cause
            detail = ''
            try:
                detail = e.read().decode('utf-8', errors='replace')[:300] if hasattr(e, 'read') else ''
            except Exception:
                detail = ''
            return {'content': f'[OllamaIRP: Connection error: {e}{" — " + detail if detail else ""}]',
                    'tool_calls': [], 'role': 'assistant', 'raw': {}}
        except Exception as e:
            return {'content': f'[OllamaIRP: Error: {e}]', 'tool_calls': [], 'role': 'assistant', 'raw': {}}

    def _update_memory(self, prompt: str, response: str):
        """Update conversation memory for context."""
        self.conversation_memory.append({'speaker': 'Human', 'message': prompt})
        self.conversation_memory.append({'speaker': 'SAGE', 'message': response})
        # Keep last N turns (each turn = 2 entries)
        max_entries = self.max_memory_turns * 2
        if len(self.conversation_memory) > max_entries:
            self.conversation_memory = self.conversation_memory[-max_entries:]

    # ----- Full IRP Contract (for orchestrator compatibility) -----

    def init_state(self, x0: Any, task_ctx: Dict[str, Any]) -> IRPState:
        """Initialize refinement state from prompt input."""
        prompt = x0 if isinstance(x0, str) else x0.get('prompt', str(x0))
        return IRPState(
            x={'prompt': prompt, 'response': '', 'memory': list(self.conversation_memory)},
            step_idx=0,
            energy_val=1.0,
            meta={'model': self.model_name, 'task_ctx': task_ctx},
        )

    def step(self, state: IRPState) -> IRPState:
        """Execute one refinement step — generate response from Ollama."""
        prompt = state.x['prompt']
        response = self.get_response(prompt)
        state.x['response'] = response
        state.step_idx += 1
        state.energy_val = self.energy(state)
        return state

    def energy(self, state: IRPState) -> float:
        """
        Compute energy for current state.

        Simple heuristic: energy decreases when we have a non-empty,
        non-error response. Further refinement steps yield diminishing
        returns for single-turn generation.
        """
        response = state.x.get('response', '')
        if not response or response.startswith('[OllamaIRP:'):
            return 1.0  # High energy = not converged
        # After first successful generation, energy is low
        return max(0.1, 1.0 / (1.0 + state.step_idx))

    def project(self, state: IRPState) -> Any:
        """Project state to output space — extract response text."""
        return state.x.get('response', '')

    def halt(self, state: IRPState) -> bool:
        """Check if refinement should stop."""
        # Single-turn generation: halt after first successful response
        response = state.x.get('response', '')
        if response and not response.startswith('[OllamaIRP:'):
            return True
        # Also halt after max iterations
        max_iter = self.config.get('max_iterations', 3)
        return state.step_idx >= max_iter

    # ----- Utility -----

    def list_models(self) -> List[str]:
        """List available models on the Ollama instance."""
        try:
            req = urllib.request.Request(f'{self.ollama_host}/api/tags')
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                return [m['name'] for m in data.get('models', [])]
        except Exception:
            return []

    def switch_model(self, model_name: str):
        """Switch to a different Ollama model at runtime."""
        self.model_name = model_name
        self._ollama_available = self._check_ollama()


if __name__ == '__main__':
    # Quick self-test
    print("OllamaIRP self-test")
    print("=" * 40)

    irp = OllamaIRP({'model_name': 'gemma3:12b'})

    if irp._ollama_available:
        print(f"\nAvailable models: {irp.list_models()}")

        print(f"\n--- get_response test ---")
        response = irp.get_response("Hello. Who are you? Reply in one sentence.")
        print(f"Response: {response}")

        print(f"\n--- IRP contract test ---")
        state = irp.init_state("What is consciousness?", {})
        print(f"Initial energy: {state.energy_val}")
        state = irp.step(state)
        print(f"After step: energy={state.energy_val}, halt={irp.halt(state)}")
        print(f"Response: {irp.project(state)}")
    else:
        print("Ollama not available. Start with: ollama serve")
